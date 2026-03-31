import { X } from 'lucide-react';
import { useState } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Step {
  title: string;
  content: JSX.Element;
}

const STEPS: Step[] = [
  {
    title: 'What is this?',
    content: (
      <div className="space-y-3 text-sm text-gray-600">
        <p>
          This is an <strong className="text-gray-800">open-source RAG (Retrieval-Augmented Generation)</strong> assistant
          that grounds Claude's answers in your own documents.
        </p>
        <p>
          Upload PDFs, Word files, or spreadsheets and the system indexes them into a
          vector database. When you ask a question, the most relevant passages are
          retrieved and sent to Claude alongside your query — so answers are specific
          to <em>your</em> data, not just general knowledge.
        </p>
        <p>
          Everything runs on open infrastructure: <strong className="text-gray-800">PostgreSQL</strong> for chat history,
          <strong className="text-gray-800"> Qdrant</strong> for vector search, <strong className="text-gray-800">MinIO</strong> for
          document storage, and <strong className="text-gray-800">Anthropic Claude</strong> for language understanding.
        </p>
      </div>
    ),
  },
  {
    title: 'Key Features',
    content: (
      <ul className="space-y-3 text-sm text-gray-600">
        {[
          ['Document Upload', 'PDF, DOCX, PPTX, XLSX — text, tables, and image captions are all indexed.'],
          ['Semantic Search', 'Hybrid vector + keyword retrieval finds the most relevant passages, even when phrasing differs.'],
          ['Reranking', 'A cross-encoder reranker re-scores retrieved chunks for precision before sending to Claude.'],
          ['Chat History', 'Sessions persist across page reloads. Switch between conversations in the sidebar.'],
          ['Source Citations', 'Every assistant answer shows which document chunks were used. Click Citations to inspect them.'],
        ].map(([title, desc]) => (
          <li key={title} className="flex gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 flex-shrink-0 mt-1.5" />
            <span>
              <strong className="text-gray-800">{title}</strong> — {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
  },
  {
    title: 'Chat Modes',
    content: (
      <div className="space-y-4 text-sm text-gray-600">
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3">
          <p className="font-semibold text-indigo-800 mb-1">Expert + Context</p>
          <p>
            Claude uses its full knowledge <em>plus</em> your indexed documents. Best for
            analysis, code, and questions that benefit from both general expertise and
            specific document context. Sources are cited when retrieved.
          </p>
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="font-semibold text-amber-800 mb-1">Strict RAG</p>
          <p>
            Answers are drawn <em>only</em> from your indexed documents — Claude will not
            use outside knowledge. Use this when you want answers strictly grounded in
            your uploaded content (e.g., policy documents, internal reports).
          </p>
        </div>
        <p className="text-xs text-gray-400">
          Switch modes at any time using the toggle in the top-right of the chat pane.
        </p>
      </div>
    ),
  },
  {
    title: 'Quick Tips',
    content: (
      <ul className="space-y-3 text-sm text-gray-600">
        {[
          ['Upload first', 'Go to the Documents tab and upload your files before asking document-specific questions.'],
          ['Be specific', "Precise questions yield better retrieval — \"What is the Q3 revenue for ACME?\" beats \"Tell me about ACME\"."],
          ['Check citations', 'Open the Citations panel on the right to see which passages the answer drew from.'],
          ['Use Strict RAG', 'When you need answers strictly from your documents, switch to Strict RAG mode to prevent hallucination.'],
          ['Give feedback', 'Use the thumbs up / down buttons under each answer to help improve response quality.'],
        ].map(([title, desc]) => (
          <li key={title} className="flex gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0 mt-1.5" />
            <span>
              <strong className="text-gray-800">{title}</strong> — {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
  },
];

export default function HelpModal({ open, onClose }: Props) {
  const [step, setStep] = useState(0);

  if (!open) return null;

  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100">
          <div>
            <p className="text-xs font-medium text-indigo-600 uppercase tracking-wide mb-0.5">
              Step {step + 1} of {STEPS.length}
            </p>
            <h2 className="text-lg font-semibold text-gray-900">{current.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 flex-1 min-h-[220px]">
          {current.content}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
          {/* Step dots */}
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <button
                key={i}
                onClick={() => setStep(i)}
                className={`w-2 h-2 rounded-full transition-colors ${
                  i === step ? 'bg-indigo-600' : 'bg-gray-200 hover:bg-gray-300'
                }`}
                aria-label={`Go to step ${i + 1}`}
              />
            ))}
          </div>

          {/* Navigation */}
          <div className="flex gap-2">
            {!isFirst && (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="px-4 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Back
              </button>
            )}
            {isLast ? (
              <button
                onClick={onClose}
                className="px-4 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Get started
              </button>
            ) : (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="px-4 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
