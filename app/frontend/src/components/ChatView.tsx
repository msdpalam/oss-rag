import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, FlaskConical, BookLock, Wrench } from 'lucide-react';
import { getMessages, streamChat } from '../api/client';
import ChatInput from './ChatInput';
import MessageBubble, { type StreamingMessage } from './MessageBubble';
import type { ChatMode, CitedChunk, Message } from '../types';

const TOOL_LABELS: Record<string, string> = {
  get_stock_price:      'Fetching price data',
  get_fundamentals:     'Fetching fundamentals',
  technical_analysis:   'Calculating indicators',
  search_documents:     'Searching documents',
  get_stock_news:       'Fetching news headlines',
  recall_past_analyses: 'Checking memory',
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
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<ChatMode>('expert_context');
  const [activeTool, setActiveTool] = useState<string | null>(null);

  // Track the current session ID locally so we can send it in follow-up messages
  const currentSessionRef = useRef<string | null>(sessionId);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // When the parent changes sessionId (user selected different session), reload messages
  useEffect(() => {
    currentSessionRef.current = sessionId;
    setError(null);

    if (!sessionId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    getMessages(sessionId)
      .then((msgs) => {
        if (!cancelled) setMessages(msgs);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const stopStreaming = () => {
    abortRef.current?.abort();
  };

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;

    setInputValue('');
    setError(null);

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
    setIsStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const accText = { current: '' };
    let finalSessionId: string | null = currentSessionRef.current;
    let finalMessageId: string | null = null;
    let finalChunks: CitedChunk[] = [];

    try {
      for await (const event of streamChat(
        {
          message: text,
          session_id: currentSessionRef.current ?? undefined,
          rewrite_query: true,
          mode,
        },
        ctrl.signal,
      )) {
        if (event.type === 'session') {
          finalSessionId = event.session_id;
          finalMessageId = event.message_id;
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
          onCitationsUpdate(event.chunks);
          const finalMsg: Message = {
            id: finalMessageId ?? `assistant-${Date.now()}`,
            session_id: finalSessionId ?? '',
            role: 'assistant',
            content: accText.current,
            created_at: new Date().toISOString(),
            retrieved_chunks: finalChunks,
            latency_ms: event.latency_ms,
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
        // Remove streaming placeholder
        setMessages((prev) => prev.filter((m) => !isStreamingMsg(m)));
      }
    } finally {
      setIsStreaming(false);
      setActiveTool(null);
      abortRef.current = null;
    }
  }, [inputValue, isStreaming, onCitationsUpdate, onSessionCreated]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Mode toggle header */}
      <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-gray-100 bg-gray-50">
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
      <div className="flex-1 overflow-y-auto py-4 scrollbar-thin">
        {isEmpty && !isStreaming ? (
          <EmptyState mode={mode} />
        ) : (
          <div className="max-w-3xl mx-auto">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {error && (
              <div className="mx-4 my-2 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">
                {error}
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
