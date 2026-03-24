import { Bot, User } from 'lucide-react';
import type { Message } from '../types';

interface Props {
  message: Message | StreamingMessage;
}

export interface StreamingMessage {
  id: 'streaming';
  role: 'assistant';
  content: string;
  isStreaming: true;
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

  return (
    <div className="flex gap-3 px-4 py-3">
      <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-4 h-4 text-gray-600" />
      </div>
      <div className="max-w-[75%] flex-1">
        <div
          className={`bg-white border border-gray-200 rounded-2xl rounded-tl-sm
                      px-4 py-2.5 text-sm leading-relaxed text-gray-800 shadow-sm
                      whitespace-pre-wrap break-words
                      ${streaming ? 'streaming-cursor' : ''}`}
        >
          {message.content || (streaming ? '' : <em className="text-gray-400">Empty response</em>)}
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
      </div>
    </div>
  );
}
