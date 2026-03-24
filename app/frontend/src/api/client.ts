/**
 * Typed API client for the OSS RAG backend.
 *
 * REST calls use fetch. File uploads use XHR for progress events.
 * SSE streaming uses fetch + ReadableStream (works for POST, unlike EventSource).
 */
import type { ChatRequest, CitedChunk, Document, Message, Session, StreamEvent } from '../types';

const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? '';
// Empty string → relative URLs → Vite proxy handles routing in dev,
// and nginx proxy handles it in production.

// ── Internal helper ───────────────────────────────────────────────────────────

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse error
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export const listSessions = (): Promise<Session[]> =>
  request<Session[]>('/sessions');

export const deleteSession = (id: string): Promise<void> =>
  request<void>(`/sessions/${id}`, { method: 'DELETE' });

export const getMessages = (sessionId: string): Promise<Message[]> =>
  request<Message[]>(`/sessions/${sessionId}/messages`);

// ── Chat streaming ────────────────────────────────────────────────────────────

/**
 * Opens a streaming SSE connection to POST /chat/stream.
 * Yields typed StreamEvent objects as they arrive.
 *
 * Usage:
 *   for await (const event of streamChat({ message: '...' })) {
 *     if (event.type === 'delta') appendText(event.text);
 *   }
 */
export async function* streamChat(
  req: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            yield JSON.parse(raw) as StreamEvent;
          } catch {
            // skip malformed lines
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Documents ─────────────────────────────────────────────────────────────────

export const listDocuments = (): Promise<Document[]> =>
  request<Document[]>('/documents');

export const getDocument = (id: string): Promise<Document> =>
  request<Document>(`/documents/${id}`);

export const deleteDocument = (id: string): Promise<void> =>
  request<void>(`/documents/${id}`, { method: 'DELETE' });

export const reindexDocument = (id: string): Promise<Document> =>
  request<Document>(`/documents/${id}/reindex`, { method: 'POST' });

/**
 * Upload a file with XHR so we get real upload-progress events.
 * @param onProgress  Called with 0–100 as bytes are sent.
 */
export function uploadDocument(
  file: File,
  onProgress: (pct: number) => void,
): Promise<Document> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Document);
        } catch {
          reject(new Error('Failed to parse upload response'));
        }
      } else {
        let detail = xhr.statusText;
        try {
          detail = (JSON.parse(xhr.responseText) as { detail?: string }).detail ?? detail;
        } catch {
          // ignore
        }
        reject(new Error(`Upload failed ${xhr.status}: ${detail}`));
      }
    });

    xhr.addEventListener('error', () =>
      reject(new Error('Network error during upload')),
    );
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.open('POST', `${API_BASE}/documents`);
    xhr.send(formData);
  });
}
