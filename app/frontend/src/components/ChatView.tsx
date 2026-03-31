import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, BookLock, FlaskConical, HelpCircle, Wrench } from 'lucide-react';
import { getMessages, streamChat } from '../api/client';
import ChatInput from './ChatInput';
import HelpModal from './HelpModal';
import MessageBubble, { type StreamingMessage } from './MessageBubble';
import type { AgentId, ChatMode, CitedChunk, Message } from '../types';

const TOOL_LABELS: Record<string, string> = {
  get_stock_price:           'Fetching price data',
  get_fundamentals:          'Fetching fundamentals',
  technical_analysis:        'Calculating indicators',
  search_documents:          'Searching documents',
  get_stock_news:            'Fetching news headlines',
  recall_past_analyses:      'Checking memory',
  get_options_chain:         'Fetching options chain',
  get_earnings_history:      'Fetching earnings history',
  get_insider_transactions:  'Checking insider activity',
  get_institutional_holdings:'Checking institutional holders',
  get_sector_performance:    'Analysing sector rotation',
  screen_stocks:             'Screening stocks',
  get_market_breadth:        'Reading market breadth',
  get_analyst_upgrades:      'Fetching analyst ratings',
  calculate_dcf:             'Running DCF valuation',
  compare_stocks:            'Comparing peer stocks',
  get_economic_indicators:   'Checking macro indicators',
  get_crypto_data:           'Fetching crypto prices',
  get_portfolio_summary:     'Analysing portfolio',
  calculate_retirement:      'Running retirement projections',
};

interface Props {
  sessionId: string | null;
  onSessionCreated: (id: string) => void;
  onCitationsUpdate: (chunks: CitedChunk[]) => void;
}

type DisplayMessage = Message | StreamingMessage;

function isStreamingMsg(m: DisplayMessage): m is StreamingMessage {
  return (m as StreamingMessage).isStreaming === true;
}

export default function ChatView({
  sessionId,
  onSessionCreated,
  onCitationsUpdate,
}: Props) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [mode, setMode] = useState<ChatMode>('expert_context');
  const [selectedAgent, setSelectedAgent] = useState<AgentId>('auto');
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(() => !localStorage.getItem('hasSeenHelp'));

  // Track the current session ID locally so we can send it in follow-up messages
  const currentSessionRef = useRef<string | null>(sessionId);
  const isStreamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // When the parent changes sessionId (user selected different session), reload messages.
  // Skip if we're streaming — onSessionCreated fires mid-stream for new chats, and the
  // DB hasn't persisted the reply yet, so fetching now would wipe the streaming placeholder.
  useEffect(() => {
    currentSessionRef.current = sessionId;
    setError(null);

    if (!sessionId) {
      setMessages([]);
      return;
    }

    if (isStreamingRef.current) return;

    let cancelled = false;
    setLoadingHistory(true);
    getMessages(sessionId)
      .then((msgs) => {
        if (!cancelled) setMessages(msgs);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Scroll to bottom only when the user is already near the bottom (within 150px).
  // This prevents hijacking scroll position when the user scrolls up to read history.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 150) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const stopStreaming = () => {
    abortRef.current?.abort();
  };

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;

    setInputValue('');
    setError(null);
    setRetryMessage(null);

    // Optimistically add the user message
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      session_id: currentSessionRef.current ?? '',
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Add placeholder for the streaming response
    const streamingPlaceholder: StreamingMessage = {
      id: 'streaming',
      role: 'assistant',
      content: '',
      isStreaming: true,
    };
    setMessages((prev) => [...prev, streamingPlaceholder]);
    isStreamingRef.current = true;
    setIsStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const accText = { current: '' };
    let finalSessionId: string | null = currentSessionRef.current;
    let finalMessageId: string | null = null;
    let finalChunks: CitedChunk[] = [];
    let finalAgentId: string | undefined;
    let finalAgentCharacter: string | undefined;
    let finalAgentTitle: string | undefined;

    try {
      for await (const event of streamChat(
        {
          message: text,
          session_id: currentSessionRef.current ?? undefined,
          rewrite_query: true,
          mode,
          agent_id: selectedAgent,
        },
        ctrl.signal,
      )) {
        if (event.type === 'session') {
          finalSessionId = event.session_id;
          finalMessageId = event.message_id;
          finalAgentId = event.agent_id;
          const focusLabel = FOCUS_AREA_LABELS[event.agent_id as AgentId] ?? event.agent_character;
          finalAgentCharacter = focusLabel;
          finalAgentTitle = undefined;
          // Update the streaming placeholder with the focus area label
          setMessages((prev) =>
            prev.map((m) =>
              (m as { isStreaming?: boolean }).isStreaming
                ? { ...m, agent_character: focusLabel, agent_title: undefined }
                : m,
            ),
          );
          if (!currentSessionRef.current) {
            currentSessionRef.current = event.session_id;
            onSessionCreated(event.session_id);
          }
        } else if (event.type === 'tool_call') {
          setActiveTool(TOOL_LABELS[event.tool] ?? event.tool);
        } else if (event.type === 'tool_result') {
          setActiveTool(null);
        } else if (event.type === 'delta') {
          accText.current += event.text;
          setMessages((prev) =>
            prev.map((m) =>
              isStreamingMsg(m) ? { ...m, content: accText.current } : m,
            ),
          );
        } else if (event.type === 'done') {
          finalChunks = event.chunks;
          finalAgentId = event.agent_id;
          finalAgentCharacter = FOCUS_AREA_LABELS[event.agent_id as AgentId] ?? event.agent_character;
          finalAgentTitle = undefined;
          onCitationsUpdate(event.chunks);
          const finalMsg: Message = {
            id: finalMessageId ?? `assistant-${Date.now()}`,
            session_id: finalSessionId ?? '',
            role: 'assistant',
            content: accText.current,
            created_at: new Date().toISOString(),
            retrieved_chunks: finalChunks,
            latency_ms: event.latency_ms,
            agent_id: finalAgentId,
            agent_character: finalAgentCharacter,
            agent_title: finalAgentTitle,
          };
          setMessages((prev) =>
            prev.map((m) => (isStreamingMsg(m) ? finalMsg : m)),
          );
          setActiveTool(null);
        } else if (event.type === 'error') {
          throw new Error(event.message);
        }
      }
    } catch (err: unknown) {
      const aborted = err instanceof Error && err.name === 'AbortError';
      if (aborted) {
        // Replace streaming message with whatever we collected
        const partial: Message = {
          id: `assistant-${Date.now()}`,
          session_id: finalSessionId ?? '',
          role: 'assistant',
          content: accText.current || '_(generation stopped)_',
          created_at: new Date().toISOString(),
          retrieved_chunks: finalChunks,
        };
        setMessages((prev) =>
          prev.map((m) => (isStreamingMsg(m) ? partial : m)),
        );
      } else {
        setError(err instanceof Error ? err.message : String(err));
        setRetryMessage(text);
        // Remove streaming placeholder
        setMessages((prev) => prev.filter((m) => !isStreamingMsg(m)));
      }
    } finally {
      isStreamingRef.current = false;
      setIsStreaming(false);
      setActiveTool(null);
      abortRef.current = null;
    }
  }, [inputValue, isStreaming, onCitationsUpdate, onSessionCreated]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full bg-white">
      <HelpModal
        open={showHelp}
        onClose={() => {
          setShowHelp(false);
          localStorage.setItem('hasSeenHelp', '1');
        }}
      />

      {/* Header bar — Focus Area + Mode */}
      <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-gray-100 bg-gray-50">
        <button
          onClick={() => setShowHelp(true)}
          title="Help & getting started"
          className="flex items-center gap-1 px-2 py-1 text-gray-400 hover:text-indigo-600 transition-colors rounded-lg hover:bg-indigo-50"
        >
          <HelpCircle className="w-4 h-4" />
          <span className="text-xs">Help</span>
        </button>
        <span className="w-px h-4 bg-gray-200" />
        <label htmlFor="focus-area-select" className="text-xs text-gray-500 whitespace-nowrap">
          Focus Area:
        </label>
        <select
          id="focus-area-select"
          value={selectedAgent}
          onChange={(e) => setSelectedAgent(e.target.value as AgentId)}
          className="text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 cursor-pointer"
        >
          {FOCUS_AREAS.map(({ id, label }) => (
            <option key={id} value={id}>{label}</option>
          ))}
        </select>
        <span className="w-px h-4 bg-gray-200" />
        <span className="text-xs text-gray-500">Mode:</span>
        <button
          onClick={() => setMode('expert_context')}
          title="Expert + Context: full LLM knowledge grounded by your documents"
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            mode === 'expert_context'
              ? 'bg-indigo-600 text-white'
              : 'bg-white text-gray-500 border border-gray-200 hover:border-indigo-300'
          }`}
        >
          <FlaskConical className="w-3 h-3" />
          Expert + Context
        </button>
        <button
          onClick={() => setMode('strict_rag')}
          title="Strict RAG: answers only from your indexed documents"
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            mode === 'strict_rag'
              ? 'bg-amber-500 text-white'
              : 'bg-white text-gray-500 border border-gray-200 hover:border-amber-300'
          }`}
        >
          <BookLock className="w-3 h-3" />
          Strict RAG
        </button>
      </div>

      {/* Messages area */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto py-4 scrollbar-thin">
        {loadingHistory ? (
          <SkeletonHistory />
        ) : isEmpty && !isStreaming ? (
          <EmptyState mode={mode} />
        ) : (
          <div className="max-w-3xl mx-auto">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {error && (
              <div className="mx-4 my-2 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 flex items-center justify-between gap-3">
                <span>{error}</span>
                {retryMessage && (
                  <button
                    onClick={() => {
                      setInputValue(retryMessage);
                      setError(null);
                      setRetryMessage(null);
                    }}
                    className="flex-shrink-0 px-3 py-1 rounded-lg bg-red-100 hover:bg-red-200 text-red-700 text-xs font-medium transition-colors"
                  >
                    Retry
                  </button>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Tool activity indicator */}
      {activeTool && (
        <div className="flex items-center gap-2 px-6 py-2 text-xs text-indigo-600 bg-indigo-50 border-t border-indigo-100">
          <Wrench className="w-3 h-3 animate-pulse" />
          <span>{activeTool}…</span>
        </div>
      )}

      {/* Input */}
      <ChatInput
        value={inputValue}
        onChange={setInputValue}
        onSubmit={() => void sendMessage()}
        onStop={stopStreaming}
        isStreaming={isStreaming}
      />
    </div>
  );
}

function SkeletonHistory() {
  return (
    <div className="max-w-3xl mx-auto space-y-4 px-4 py-2 animate-pulse">
      {[72, 48, 96, 56].map((w, i) => (
        <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'justify-end' : ''}`}>
          {i % 2 !== 0 && <div className="w-8 h-8 rounded-full bg-gray-200 flex-shrink-0" />}
          <div className={`rounded-2xl h-10 bg-gray-200 ${i % 2 === 0 ? 'rounded-tr-sm' : 'rounded-tl-sm'}`}
               style={{ width: `${w}%` }} />
          {i % 2 === 0 && <div className="w-8 h-8 rounded-full bg-gray-200 flex-shrink-0" />}
        </div>
      ))}
    </div>
  );
}

// ── Focus area (agent) selector ───────────────────────────────────────────────

const FOCUS_AREAS: { id: AgentId; label: string }[] = [
  { id: 'auto',                 label: 'All Areas'              },
  { id: 'equity_analyst',       label: 'Equity Research'        },
  { id: 'technical_trader',     label: 'Technical Analysis'     },
  { id: 'macro_strategist',     label: 'Macro & Economics'      },
  { id: 'retirement_planner',   label: 'Retirement Planning'    },
  { id: 'crypto_analyst',       label: 'Crypto & Digital Assets'},
  { id: 'portfolio_strategist', label: 'Portfolio Strategy'     },
];

const FOCUS_AREA_LABELS: Record<AgentId, string> = Object.fromEntries(
  FOCUS_AREAS.map(({ id, label }) => [id, label]),
) as Record<AgentId, string>;

function EmptyState({ mode }: { mode: ChatMode }) {
  const isExpert = mode === 'expert_context';
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 ${isExpert ? 'bg-indigo-50' : 'bg-amber-50'}`}>
        <Bot className={`w-7 h-7 ${isExpert ? 'text-indigo-600' : 'text-amber-600'}`} />
      </div>
      <h2 className="text-xl font-semibold text-gray-800 mb-2">
        {isExpert ? 'Expert assistant with document context' : 'Ask about your documents'}
      </h2>
      <p className="text-sm text-gray-500 max-w-sm">
        {isExpert
          ? 'Ask anything — data science, analysis, code. Upload documents to ground answers in your specific data.'
          : 'Answers are strictly from your indexed documents. Upload documents in the Documents tab.'}
      </p>
    </div>
  );
}
