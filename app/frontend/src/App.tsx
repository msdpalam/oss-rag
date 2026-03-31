import { useCallback, useEffect, useState } from 'react';
import { listSessions } from './api/client';
import AuthPage from './components/AuthPage';
import CitationPanel from './components/CitationPanel';
import DocumentManager from './components/DocumentManager';
import PortfolioView from './components/PortfolioView';
import ChatView from './components/ChatView';
import SessionSidebar from './components/SessionSidebar';
import SettingsPage from './components/SettingsPage';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import type { CitedChunk, Session } from './types';

type View = 'chat' | 'documents' | 'portfolio';

function AppShell() {
  const [view, setView] = useState<View>('chat');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [citations, setCitations] = useState<CitedChunk[]>([]);
  const [citationPanelOpen, setCitationPanelOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const { isLoading, user } = useAuth();

  // Load sessions on mount and whenever a session is created/deleted
  const refreshSessions = useCallback(async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch {
      // swallow — backend may not be up yet
    }
  }, []);

  useEffect(() => {
    if (user) void refreshSessions();
  }, [refreshSessions, user]);

  const handleNewChat = () => {
    setActiveSessionId(null);
    setCitations([]);
    setCitationPanelOpen(false);
    setView('chat');
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    setCitations([]);
    setCitationPanelOpen(false);
    setView('chat');
  };

  const handleSessionCreated = useCallback(
    (sessionId: string) => {
      setActiveSessionId(sessionId);
      void refreshSessions();
    },
    [refreshSessions],
  );

  const handleSessionDeleted = useCallback(
    (sessionId: string) => {
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setCitations([]);
        setCitationPanelOpen(false);
      }
      void refreshSessions();
    },
    [activeSessionId, refreshSessions],
  );

  const handleCitationsUpdate = useCallback((chunks: CitedChunk[]) => {
    setCitations(chunks);
    setCitationPanelOpen(chunks.length > 0);
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <AuthPage />;

  return (
    <div className="flex h-full bg-white overflow-hidden">
      {/* ── Left sidebar ─────────────────────────────────────────────────── */}
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        activeView={view}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleSessionDeleted}
        onNavigateDocuments={() => setView('documents')}
        onNavigatePortfolio={() => setView('portfolio')}
        onOpenSettings={() => setShowSettings(true)}
      />

      {showSettings && <SettingsPage onClose={() => setShowSettings(false)} />}

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {view === 'chat' ? (
          <ChatView
            sessionId={activeSessionId}
            onSessionCreated={handleSessionCreated}
            onCitationsUpdate={handleCitationsUpdate}
          />
        ) : view === 'portfolio' ? (
          <PortfolioView />
        ) : (
          <DocumentManager />
        )}
      </main>

      {/* ── Right citation panel ──────────────────────────────────────────── */}
      {view === 'chat' && (
        <CitationPanel
          chunks={citations}
          isOpen={citationPanelOpen}
          onToggle={() => setCitationPanelOpen((o) => !o)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
