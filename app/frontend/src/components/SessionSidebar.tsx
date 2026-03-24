import { useState } from 'react';
import {
  FileText,
  MessageSquare,
  Plus,
  Trash2,
} from 'lucide-react';
import { deleteSession } from '../api/client';
import type { Session } from '../types';

interface Props {
  sessions: Session[];
  activeSessionId: string | null;
  activeView: 'chat' | 'documents';
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNavigateDocuments: () => void;
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function SessionSidebar({
  sessions,
  activeSessionId,
  activeView,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onNavigateDocuments,
}: Props) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    setDeletingId(id);
    try {
      await deleteSession(id);
      onDeleteSession(id);
    } catch (err) {
      console.error('Failed to delete session:', err);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <aside className="w-64 flex flex-col bg-gray-900 text-gray-100 flex-shrink-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-4 border-b border-gray-700/50">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center flex-shrink-0">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-sm text-white">OSS RAG Chat</span>
        </div>

        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                     bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
        >
          <Plus className="w-4 h-4" />
          New conversation
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        {sessions.length === 0 ? (
          <p className="px-4 py-3 text-xs text-gray-500">
            No conversations yet. Start one above.
          </p>
        ) : (
          <ul className="space-y-0.5 px-2">
            {sessions.map((s) => {
              const isActive = s.id === activeSessionId;
              const isDeleting = deletingId === s.id;
              return (
                <li key={s.id}>
                  <button
                    onClick={() => onSelectSession(s.id)}
                    disabled={isDeleting}
                    className={`group w-full text-left px-3 py-2.5 rounded-lg text-sm
                                transition-colors flex items-start gap-2
                                ${isActive
                                  ? 'bg-gray-700 text-white'
                                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                                }
                                ${isDeleting ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <MessageSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-400" />
                    <div className="flex-1 min-w-0">
                      <p className="truncate leading-snug">
                        {s.title ?? 'New conversation'}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {formatRelativeTime(s.last_message_at ?? s.updated_at)}
                        {s.message_count > 0 && (
                          <span className="ml-1.5 text-gray-600">
                            · {s.message_count} msg{s.message_count !== 1 ? 's' : ''}
                          </span>
                        )}
                      </p>
                    </div>
                    <button
                      onClick={(e) => void handleDelete(e, s.id)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 rounded
                                 hover:text-red-400 transition-opacity flex-shrink-0"
                      title="Delete conversation"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* Bottom nav */}
      <div className="border-t border-gray-700/50 p-2">
        <button
          onClick={onNavigateDocuments}
          className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm
                      transition-colors
                      ${activeView === 'documents'
                        ? 'bg-gray-700 text-white'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                      }`}
        >
          <FileText className="w-4 h-4" />
          Documents
        </button>
      </div>
    </aside>
  );
}
