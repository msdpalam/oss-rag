import { ChevronRight, FileText, Image, Table } from 'lucide-react';
import type { CitedChunk } from '../types';

interface Props {
  chunks: CitedChunk[];
  isOpen: boolean;
  onToggle: () => void;
}

function scoreColor(score: number): string {
  if (score >= 0.75) return 'bg-emerald-100 text-emerald-700';
  if (score >= 0.5) return 'bg-amber-100 text-amber-700';
  return 'bg-red-100 text-red-700';
}

function scoreBarWidth(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function ContentTypeIcon({ type }: { type: CitedChunk['content_type'] }) {
  if (type === 'table') return <Table className="w-3.5 h-3.5 flex-shrink-0" />;
  if (type === 'image_caption') return <Image className="w-3.5 h-3.5 flex-shrink-0" />;
  return <FileText className="w-3.5 h-3.5 flex-shrink-0" />;
}

export default function CitationPanel({ chunks, isOpen, onToggle }: Props) {
  return (
    <>
      {/* Toggle tab — always visible */}
      <button
        onClick={onToggle}
        title={isOpen ? 'Close sources' : 'Open sources'}
        className={`absolute right-0 top-1/2 -translate-y-1/2 z-10
                    flex items-center gap-1 px-1 py-4 rounded-l-md
                    bg-white border border-r-0 border-gray-200 shadow-sm
                    text-gray-400 hover:text-gray-600 transition-colors
                    ${chunks.length === 0 ? 'opacity-40 cursor-default' : ''}`}
        style={{ position: 'fixed', right: isOpen ? '320px' : '0' }}
        disabled={chunks.length === 0}
      >
        <ChevronRight
          className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
        {!isOpen && chunks.length > 0 && (
          <span className="text-xs font-medium text-indigo-600 -rotate-90 whitespace-nowrap mt-1">
            {chunks.length} source{chunks.length !== 1 ? 's' : ''}
          </span>
        )}
      </button>

      {/* Panel */}
      <aside
        className={`flex-shrink-0 bg-gray-50 border-l border-gray-200
                    flex flex-col overflow-hidden transition-all duration-200
                    ${isOpen ? 'w-80' : 'w-0'}`}
      >
        {isOpen && (
          <>
            {/* Header */}
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-800">
                Sources
                <span className="ml-2 text-xs font-normal text-gray-400">
                  {chunks.length} chunk{chunks.length !== 1 ? 's' : ''} retrieved
                </span>
              </h2>
            </div>

            {/* Chunk list */}
            <ul className="flex-1 overflow-y-auto divide-y divide-gray-200 scrollbar-thin">
              {chunks.map((chunk, i) => (
                <li key={chunk.id} className="p-3 hover:bg-gray-100 transition-colors">
                  {/* Source filename + page */}
                  <div className="flex items-start gap-1.5 mb-1.5">
                    <ContentTypeIcon type={chunk.content_type} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-700 truncate">
                        {chunk.source}
                        {chunk.page != null && (
                          <span className="text-gray-400 font-normal ml-1">
                            p.{chunk.page}
                          </span>
                        )}
                      </p>
                    </div>
                    <span
                      className={`text-xs font-medium px-1.5 py-0.5 rounded-full flex-shrink-0
                                  ${scoreColor(chunk.score)}`}
                    >
                      {(chunk.score * 100).toFixed(0)}%
                    </span>
                  </div>

                  {/* Score bar */}
                  <div className="mb-2 bg-gray-200 rounded-full h-1">
                    <div
                      className="h-1 rounded-full bg-indigo-400 transition-all"
                      style={{ width: scoreBarWidth(chunk.score) }}
                    />
                  </div>

                  {/* Content snippet */}
                  <p className="text-xs text-gray-600 leading-relaxed line-clamp-4">
                    {chunk.content}
                  </p>

                  <p className="mt-1.5 text-xs text-gray-400">#{i + 1}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </>
  );
}
