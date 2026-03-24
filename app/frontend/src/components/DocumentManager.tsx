import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Image,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  deleteDocument,
  listDocuments,
  reindexDocument,
  uploadDocument,
} from '../api/client';
import type { Document } from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number | undefined): string {
  if (!bytes) return '–';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

const STATUS_CONFIG: Record<
  Document['status'],
  { label: string; icon: React.ReactNode; className: string }
> = {
  uploaded: {
    label: 'Queued',
    icon: <Clock className="w-3.5 h-3.5" />,
    className: 'bg-gray-100 text-gray-600',
  },
  processing: {
    label: 'Processing',
    icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    className: 'bg-blue-100 text-blue-600',
  },
  indexed: {
    label: 'Indexed',
    icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    className: 'bg-emerald-100 text-emerald-600',
  },
  failed: {
    label: 'Failed',
    icon: <XCircle className="w-3.5 h-3.5" />,
    className: 'bg-red-100 text-red-600',
  },
};

// ── Upload item ───────────────────────────────────────────────────────────────

interface UploadItem {
  file: File;
  progress: number; // 0–100
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DocumentManager() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploads, setUploads] = useState<Map<string, UploadItem>>(new Map());
  const [isDragOver, setIsDragOver] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load & poll documents ──────────────────────────────────────────────────

  const loadDocs = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      setLoadError(null);
    } catch (err) {
      setLoadError(String(err));
    }
  }, []);

  useEffect(() => {
    void loadDocs();
  }, [loadDocs]);

  // Poll while any document is still processing
  useEffect(() => {
    const hasInFlight = documents.some(
      (d) => d.status === 'uploaded' || d.status === 'processing',
    );

    if (hasInFlight && !pollRef.current) {
      pollRef.current = setInterval(() => void loadDocs(), 2500);
    } else if (!hasInFlight && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, loadDocs]);

  // ── Upload ────────────────────────────────────────────────────────────────

  const startUpload = useCallback(
    (file: File) => {
      const key = `${file.name}-${Date.now()}`;
      setUploads((prev) => {
        const next = new Map(prev);
        next.set(key, { file, progress: 0, status: 'uploading' });
        return next;
      });

      uploadDocument(file, (pct) => {
        setUploads((prev) => {
          const next = new Map(prev);
          const item = next.get(key);
          if (item) next.set(key, { ...item, progress: pct });
          return next;
        });
      })
        .then(() => {
          setUploads((prev) => {
            const next = new Map(prev);
            const item = next.get(key);
            if (item) next.set(key, { ...item, status: 'done', progress: 100 });
            return next;
          });
          void loadDocs();
          // Remove the upload item after a short delay
          setTimeout(() => {
            setUploads((prev) => {
              const next = new Map(prev);
              next.delete(key);
              return next;
            });
          }, 2000);
        })
        .catch((err: Error) => {
          setUploads((prev) => {
            const next = new Map(prev);
            const item = next.get(key);
            if (item)
              next.set(key, {
                ...item,
                status: 'error',
                error: err.message,
              });
            return next;
          });
        });
    },
    [loadDocs],
  );

  const handleFiles = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      startUpload(file);
    }
  };

  // ── Delete ────────────────────────────────────────────────────────────────

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}" and all its indexed chunks?`)) return;
    setDeletingId(id);
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      alert(`Delete failed: ${err}`);
    } finally {
      setDeletingId(null);
    }
  };

  // ── Reindex ───────────────────────────────────────────────────────────────

  const handleReindex = async (id: string) => {
    setReindexingId(id);
    try {
      const updated = await reindexDocument(id);
      setDocuments((prev) =>
        prev.map((d) => (d.id === id ? updated : d)),
      );
    } catch (err) {
      alert(`Reindex failed: ${err}`);
    } finally {
      setReindexingId(null);
    }
  };

  // ── Drag & drop ───────────────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  };

  const uploadItems = Array.from(uploads.values());

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto">
      <div className="max-w-4xl mx-auto w-full px-6 py-6">
        {/* Page header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-gray-800">Documents</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Upload files to index them for RAG retrieval
            </p>
          </div>
          <button
            onClick={() => void loadDocs()}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer
                       transition-colors mb-6
                       ${isDragOver
                         ? 'border-indigo-400 bg-indigo-50'
                         : 'border-gray-300 hover:border-indigo-300 hover:bg-gray-50'
                       }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.txt,.md,.html,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.webp"
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
          <Upload
            className={`w-8 h-8 mx-auto mb-3 ${isDragOver ? 'text-indigo-500' : 'text-gray-400'}`}
          />
          <p className="text-sm font-medium text-gray-700 mb-1">
            Drop files here or click to upload
          </p>
          <p className="text-xs text-gray-400">
            PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, PNG, JPG, WEBP
          </p>
        </div>

        {/* Active uploads with progress bars */}
        {uploadItems.length > 0 && (
          <div className="mb-6 space-y-2">
            {uploadItems.map((item, i) => (
              <UploadProgressRow key={i} item={item} />
            ))}
          </div>
        )}

        {/* Error */}
        {loadError && (
          <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {loadError}
          </div>
        )}

        {/* Document list */}
        {documents.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <FileText className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">No documents yet. Upload one above.</p>
          </div>
        ) : (
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    File
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Size
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Chunks
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Uploaded
                  </th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {documents.map((doc) => {
                  const cfg = STATUS_CONFIG[doc.status];
                  const isDeleting = deletingId === doc.id;
                  const isReindexing = reindexingId === doc.id;

                  return (
                    <tr
                      key={doc.id}
                      className={`hover:bg-gray-50 transition-colors ${isDeleting ? 'opacity-50' : ''}`}
                    >
                      {/* Filename */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <DocIcon contentType={doc.content_type} />
                          <div className="min-w-0">
                            <p className="font-medium text-gray-800 truncate max-w-[200px]">
                              {doc.original_name}
                            </p>
                            {doc.page_count != null && (
                              <p className="text-xs text-gray-400">
                                {doc.page_count} page{doc.page_count !== 1 ? 's' : ''}
                                {doc.has_images ? ' · images' : ''}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${cfg.className}`}
                        >
                          {cfg.icon}
                          {cfg.label}
                        </span>
                        {doc.status === 'failed' && doc.error_message && (
                          <p className="text-xs text-red-500 mt-1 max-w-[200px] truncate" title={doc.error_message}>
                            {doc.error_message}
                          </p>
                        )}
                      </td>

                      {/* Size */}
                      <td className="px-4 py-3 text-gray-500">
                        {formatBytes(doc.size_bytes)}
                      </td>

                      {/* Chunks */}
                      <td className="px-4 py-3 text-gray-500">
                        {doc.chunk_count ?? '–'}
                      </td>

                      {/* Date */}
                      <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                        {formatDate(doc.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 justify-end">
                          {doc.status === 'failed' && (
                            <button
                              onClick={() => void handleReindex(doc.id)}
                              disabled={isReindexing}
                              title="Retry indexing"
                              className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600
                                         hover:bg-indigo-50 transition-colors disabled:opacity-50"
                            >
                              <RefreshCw
                                className={`w-4 h-4 ${isReindexing ? 'animate-spin' : ''}`}
                              />
                            </button>
                          )}
                          <button
                            onClick={() => void handleDelete(doc.id, doc.original_name)}
                            disabled={isDeleting}
                            title="Delete document"
                            className="p-1.5 rounded-lg text-gray-400 hover:text-red-600
                                       hover:bg-red-50 transition-colors disabled:opacity-50"
                          >
                            {isDeleting ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function UploadProgressRow({ item }: { item: UploadItem }) {
  const isError = item.status === 'error';
  const isDone = item.status === 'done';

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm
                  ${isError ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'}`}
    >
      <FileText className={`w-4 h-4 flex-shrink-0 ${isError ? 'text-red-400' : 'text-gray-400'}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="truncate text-gray-700 font-medium">{item.file.name}</span>
          <span className={`text-xs ml-2 flex-shrink-0 ${isError ? 'text-red-500' : 'text-gray-400'}`}>
            {isError ? 'Failed' : isDone ? 'Done' : `${item.progress}%`}
          </span>
        </div>
        {isError ? (
          <p className="text-xs text-red-500">{item.error}</p>
        ) : (
          <div className="bg-gray-200 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all ${isDone ? 'bg-emerald-500' : 'bg-indigo-500'}`}
              style={{ width: `${item.progress}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function DocIcon({ contentType }: { contentType?: string }) {
  if (contentType?.startsWith('image/')) {
    return <Image className="w-4 h-4 text-purple-400 flex-shrink-0" />;
  }
  return <FileText className="w-4 h-4 text-indigo-400 flex-shrink-0" />;
}
