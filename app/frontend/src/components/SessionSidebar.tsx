import { useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  LogOut,
  MessageSquare,
  Plus,
  Settings,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import { deleteSession } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { Session } from '../types';

interface Props {
  sessions: Session[];
  activeSessionId: string | null;
  activeView: 'chat' | 'documents' | 'portfolio';
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNavigateDocuments: () => void;
  onNavigatePortfolio: () => void;
  onOpenSettings: () => void;
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
  onNavigatePortfolio,
  onOpenSettings,
}: Props) {
  const { user, logout } = useAuth();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

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
    <aside
      className={`flex flex-col bg-gray-900 text-gray-100 flex-shrink-0 overflow-hidden transition-all duration-300
                  ${collapsed ? 'w-14' : 'w-64'}`}
    >
      {/* Header */}
      <div className={`px-2 py-4 border-b border-gray-700/50 ${collapsed ? '' : 'px-4'}`}>
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center flex-shrink-0">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          {!collapsed && <span className="font-semibold text-sm text-white truncate">Stock Analyst</span>}
          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="ml-auto p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors flex-shrink-0"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        <button
          onClick={onNewChat}
          title="New conversation"
          className={`flex items-center gap-2 rounded-lg text-sm
                      bg-indigo-600 hover:bg-indigo-500 text-white transition-colors
                      ${collapsed ? 'w-9 h-9 justify-center p-0' : 'w-full px-3 py-2'}`}
        >
          <Plus className="w-4 h-4 flex-shrink-0" />
          {!collapsed && 'New conversation'}
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        {!collapsed && sessions.length === 0 && (
          <p className="px-4 py-3 text-xs text-gray-500">
            No conversations yet. Start one above.
          </p>
        )}
        <ul className="space-y-0.5 px-2">
          {sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            const isDeleting = deletingId === s.id;
            return (
              <li key={s.id}>
                <button
                  onClick={() => onSelectSession(s.id)}
                  disabled={isDeleting}
                  title={collapsed ? (s.title ?? 'New conversation') : undefined}
                  className={`group w-full text-left rounded-lg text-sm transition-colors flex items-start gap-2
                              ${collapsed ? 'justify-center p-2' : 'px-3 py-2.5'}
                              ${isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}
                              ${isDeleting ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <MessageSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-400" />
                  {!collapsed && (
                    <>
                      <div className="flex-1 min-w-0">
                        <p className="truncate leading-snug">{s.title ?? 'New conversation'}</p>
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
                        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-red-400 transition-opacity flex-shrink-0"
                        title="Delete conversation"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom nav */}
      <div className="border-t border-gray-700/50 p-2 space-y-1">
        <button
          onClick={onNavigateDocuments}
          title="Documents"
          className={`flex items-center gap-2 rounded-lg text-sm transition-colors
                      ${collapsed ? 'w-full justify-center p-2' : 'w-full px-3 py-2.5'}
                      ${activeView === 'documents' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
        >
          <FileText className="w-4 h-4" />
          {!collapsed && 'Documents'}
        </button>

        <button
          onClick={onNavigatePortfolio}
          title="Portfolio"
          className={`flex items-center gap-2 rounded-lg text-sm transition-colors
                      ${collapsed ? 'w-full justify-center p-2' : 'w-full px-3 py-2.5'}
                      ${activeView === 'portfolio' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
        >
          <TrendingUp className="w-4 h-4" />
          {!collapsed && 'Portfolio'}
        </button>

        <button
          onClick={onOpenSettings}
          title="Investor Profile"
          className={`flex items-center gap-2 rounded-lg text-sm transition-colors text-gray-400 hover:bg-gray-800 hover:text-white
                      ${collapsed ? 'w-full justify-center p-2' : 'w-full px-3 py-2.5'}`}
        >
          <Settings className="w-4 h-4" />
          {!collapsed && 'Investor Profile'}
        </button>

        {/* User info + logout */}
        <div className={`flex items-center gap-2 px-2 py-2 ${collapsed ? 'justify-center' : ''}`}>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-400 truncate">
                {user?.display_name ?? user?.email ?? ''}
              </p>
            </div>
          )}
          <button
            onClick={logout}
            title="Sign out"
            className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors flex-shrink-0"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
