import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';
import { isRealTimeMarker } from '@/utils/parseTimestampedSections';
import { normalizeCjkMarkerSpacing } from '@/utils/summaryParser';

/** Render an episode summary as structured markdown, preserving heading levels and
 *  paragraphs, and turning the agents pipeline's inline markers into rich elements:
 *    [label](#ticker:SYMBOL) -> stock link
 *    [label](#tag:ID)        -> topic chip
 *    (#time:MILLISECONDS)     -> clickable timestamp badge that seeks the player
 *
 *  The pipeline emits well-formed markdown (no raw HTML), so remark-gfm alone is
 *  enough — we intentionally do NOT enable rehype-raw. */

function formatTimestamp(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

interface SummaryMarkdownProps {
  content: string;
  onSeek?: (seconds: number) => void;
}

export const SummaryMarkdown: React.FC<SummaryMarkdownProps> = ({ content, onSeek }) => {
  // Bare `(#time:MS)` markers aren't markdown links, so rewrite them into links
  // (with the formatted time as the label) — then the custom anchor renderer below
  // turns them into clickable badges.
  const prepared = useMemo(
    () => normalizeCjkMarkerSpacing(
      (content || '').replace(/\s*\(#time:(\d+)\)/g, (_match, ms) => {
        // Drop ordinal/placeholder markers (the legacy writer-LLM bug) so they don't
        // render as bogus 00:00 badges; keep real offsets as clickable links.
        if (!isRealTimeMarker(Number(ms))) return '';
        return ` [${formatTimestamp(Number(ms))}](#time:${ms})`;
      }),
    ),
    [content],
  );

  if (!prepared.trim()) return null;

  return (
    <div className="text-xl md:text-lg leading-relaxed md:leading-[1.9] text-foreground">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h2 className="text-3xl md:text-2xl font-bold tracking-tight leading-tight mt-10 first:mt-0 mb-3">{children}</h2>
          ),
          // No flex here: flex makes each child (ticker link, title text, time badge)
          // an atomic item, so a long title wraps the leading ticker name onto its own
          // line. Plain inline flow lets "台積電 加速CoWoS…" read as one heading.
          h2: ({ children }) => (
            <h3 className="text-2xl md:text-xl font-bold tracking-tight leading-tight mt-8 mb-2">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="text-xl md:text-lg font-semibold leading-snug text-foreground mt-7 mb-2">{children}</h4>
          ),
          h4: ({ children }) => (
            <h5 className="text-lg md:text-md font-semibold text-foreground/90 mt-5 mb-1">{children}</h5>
          ),
          p: ({ children }) => <p className="mb-5 md:mb-7 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-6 mb-5 flex flex-col gap-2">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-6 mb-5 flex flex-col gap-2">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed md:leading-[1.9] pl-1">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-[3px] border-border pl-5 my-5 text-foreground/70 italic">{children}</blockquote>
          ),
          hr: () => <hr className="my-8 border-border" />,
          a: ({ href, children }) => {
            const h = (href || '').trim();
            if (h.startsWith('#ticker:')) {
              const symbol = h.slice('#ticker:'.length).trim().toUpperCase();
              return (
                <Link to={`/stock/${encodeURIComponent(symbol)}`} className="text-accent-info hover:underline font-medium">
                  {children}
                </Link>
              );
            }
            if (h.startsWith('#tag:')) {
              const id = h.slice('#tag:'.length).trim();
              // Reads as normal prose text; clickable, with a subtle hover that
              // reveals it links to the topic.
              return (
                <Link
                  to={`/topics/${encodeURIComponent(id)}`}
                  className="hover:text-accent-info hover:underline transition-colors"
                >
                  {children}
                </Link>
              );
            }
            if (h.startsWith('#time:')) {
              const ms = Number(h.slice('#time:'.length).trim());
              if (!isRealTimeMarker(ms)) return <>{children}</>;
              return (
                <button
                  type="button"
                  onClick={() => onSeek?.(Math.round(ms / 1000))}
                  className="inline-flex items-center align-middle font-mono text-xs font-medium px-1.5 py-0.5 mx-0.5 rounded bg-primary/15 text-primary hover:bg-primary/25 transition-colors"
                >
                  {children}
                </button>
              );
            }
            // External / other links
            return (
              <a href={h} target="_blank" rel="noopener noreferrer" className="text-accent-info hover:underline">
                {children}
              </a>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
};
