import { Bot, ThumbsDown, ThumbsUp, User } from 'lucide-react';
import { useState } from 'react';
import { submitFeedback } from '../api/client';
import type { Message } from '../types';
import MarkdownContent from './MarkdownContent';

interface Props {
  message: Message | StreamingMessage;
}

export interface StreamingMessage {
  id: 'streaming';
  role: 'assistant';
  content: string;
  isStreaming: true;
  agent_character?: string;
  agent_title?: string;
}

function isStreaming(m: Message | StreamingMessage): m is StreamingMessage {
  return (m as StreamingMessage).isStreaming === true;
}

function formatMs(ms: number | undefined): string | null {
  if (!ms) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const streaming = !isUser && isStreaming(message);
  const [activeFeedback, setActiveFeedback] = useState<'up' | 'down' | null>(
    !isUser && !isStreaming(message) ? ((message as Message).feedback ?? null) : null,
  );

  const handleFeedback = async (value: 'up' | 'down') => {
    if (isUser || isStreaming(message)) return;
    const msgId = (message as Message).id;
    if (!msgId || msgId === 'streaming') return;
    setActiveFeedback(value);
    try {
      await submitFeedback(msgId, value);
    } catch {
      // revert on failure
      setActiveFeedback(activeFeedback);
    }
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-3 px-4 py-3">
        <div className="max-w-[75%]">
          <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
            {message.content}
          </div>
        </div>
        <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0 mt-0.5">
          <User className="w-4 h-4 text-indigo-600" />
        </div>
      </div>
    );
  }

  // Assistant message
  const msg = message as Message;
  const latency = !streaming ? formatMs((msg as Message).latency_ms) : null;
  const chunkCount = !streaming && msg.retrieved_chunks ? msg.retrieved_chunks.length : null;
  const agentCharacter = (message as StreamingMessage).agent_character ?? (msg as Message).agent_character;
  const agentTitle = (message as StreamingMessage).agent_title ?? (msg as Message).agent_title;
  const agentInitial = agentCharacter ? agentCharacter[0] : null;

  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold text-indigo-700">
        {agentInitial ?? <Bot className="w-4 h-4 text-gray-600" />}
      </div>
      <div className="max-w-[75%] flex-1">
        {(agentCharacter || streaming) && (
          <p className="text-xs font-medium text-indigo-600 mb-1">
            {agentCharacter ?? '…'}
            {agentTitle && <span className="text-gray-400 font-normal"> — {agentTitle}</span>}
          </p>
        )}
        <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm text-gray-800 shadow-sm overflow-hidden">
          {streaming && !message.content ? (
            // Thinking pulse — shown during tool calls before any text arrives
            <div className="flex items-center gap-1.5 py-1">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.3s]" />
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.15s]" />
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" />
            </div>
          ) : message.content ? (
            <MarkdownContent content={message.content} streaming={streaming} />
          ) : (
            <em className="text-gray-400">Empty response</em>
          )}
        </div>

        {/* Metadata row */}
        {!streaming && (latency || chunkCount) && (
          <div className="flex gap-3 mt-1.5 px-1">
            {chunkCount != null && chunkCount > 0 && (
              <span className="text-xs text-gray-400">
                {chunkCount} source{chunkCount !== 1 ? 's' : ''} cited
              </span>
            )}
            {msg.search_query && (
              <span className="text-xs text-gray-400 truncate max-w-[200px]" title={msg.search_query}>
                query: <em>{msg.search_query}</em>
              </span>
            )}
            {latency && (
              <span className="text-xs text-gray-400 ml-auto">{latency}</span>
            )}
          </div>
        )}

        {/* Feedback buttons */}
        {!streaming && (
          <div className="flex gap-1 mt-1.5 px-1">
            <button
              onClick={() => void handleFeedback('up')}
              title="Helpful"
              className={`p-1 rounded transition-colors ${
                activeFeedback === 'up'
                  ? 'text-indigo-600'
                  : 'text-gray-300 hover:text-indigo-400'
              }`}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => void handleFeedback('down')}
              title="Not helpful"
              className={`p-1 rounded transition-colors ${
                activeFeedback === 'down'
                  ? 'text-red-500'
                  : 'text-gray-300 hover:text-red-400'
              }`}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
