/**
 * MarkdownContent — renders assistant response text as rich markdown.
 *
 * Features:
 *  - GitHub-Flavored Markdown (tables, strikethrough, task lists) via remark-gfm
 *  - Syntax-highlighted code blocks (Prism one-dark theme)
 *  - Inline code with a subtle background
 *  - Tailwind Typography `prose` for consistent headings, lists, blockquotes
 *  - Streaming cursor preserved via the `streaming` prop
 */
import { type ComponentProps, lazy, Suspense } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Lazy-load the syntax highlighter so it doesn't inflate the initial bundle
const SyntaxHighlighter = lazy(() =>
  import('react-syntax-highlighter').then((m) => ({ default: m.Prism })),
);
// oneDark style — imported eagerly as it's tiny JSON, not code
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface Props {
  content: string;
  streaming?: boolean;
}

// Custom code renderer: block code → syntax-highlighted, inline → subtle pill
function CodeBlock({
  inline,
  className,
  children,
  ...rest
}: ComponentProps<'code'> & { inline?: boolean }) {
  const match = /language-(\w+)/.exec(className ?? '');
  const language = match?.[1] ?? 'text';
  const code = String(children).replace(/\n$/, '');

  if (!inline && (match || code.includes('\n'))) {
    return (
      <div className="my-2 rounded-lg overflow-hidden text-xs">
        {match && (
          <div className="flex items-center justify-between bg-[#282c34] px-3 py-1.5 border-b border-white/10">
            <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
              {language}
            </span>
          </div>
        )}
        <Suspense fallback={
          <pre className="bg-[#282c34] text-gray-200 p-3 text-xs overflow-x-auto">
            <code>{code}</code>
          </pre>
        }>
          <SyntaxHighlighter
            style={oneDark}
            language={language}
            PreTag="div"
            customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.78rem', lineHeight: 1.6 }}
            {...(rest as object)}
          >
            {code}
          </SyntaxHighlighter>
        </Suspense>
      </div>
    );
  }

  return (
    <code
      className="bg-gray-100 text-indigo-700 px-1 py-0.5 rounded text-[0.8em] font-mono"
      {...rest}
    >
      {children}
    </code>
  );
}

export default function MarkdownContent({ content, streaming = false }: Props) {
  return (
    <div
      className={[
        'prose prose-sm prose-gray max-w-none',
        // Fine-tune link colours to match app palette
        'prose-a:text-indigo-600 prose-a:no-underline hover:prose-a:underline',
        // Blockquote style
        'prose-blockquote:border-l-indigo-300 prose-blockquote:text-gray-500',
        // Table borders
        'prose-table:text-xs',
        // Streaming cursor
        streaming ? 'streaming-cursor' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: CodeBlock,
          // Open external links in a new tab
          a: ({ href, children, ...props }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
