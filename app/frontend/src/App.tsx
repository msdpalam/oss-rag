import { useCallback, useEffect, useState } from 'react';
import { listSessions } from './api/client';
import CitationPanel from './components/CitationPanel';
import DocumentManager from './components/DocumentManager';
import ChatView from './components/ChatView';
import SessionSidebar from './components/SessionSidebar';
import type { CitedChunk, Session } from './types';

type View = 'chat' | 'documents';

export default function App() {
  const [view, setView] = useState<View>('chat');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [citations, setCitations] = useState<CitedChunk[]>([]);
  const [citationPanelOpen, setCitationPanelOpen] = useState(false);

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
    void refreshSessions();
  }, [refreshSessions]);

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
      />

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {view === 'chat' ? (
          <ChatView
            sessionId={activeSessionId}
            onSessionCreated={handleSessionCreated}
            onCitationsUpdate={handleCitationsUpdate}
          />
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
