import React, { useEffect, useMemo, useRef } from 'react';
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
  /** Land on a section instead of the top: the ms offset a social link carried in
   *  `?t=`. Scrolls to the last section starting at or before it — so a section's own
   *  anchor and a mention's timestamp inside that section both work. */
  focusMs?: number | null;
}

export const SummaryMarkdown: React.FC<SummaryMarkdownProps> = ({ content, onSeek, focusMs }) => {
  const rootRef = useRef<HTMLDivElement>(null);

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

  // A reader who tapped a Threads link about ONE judgment should arrive at it, not at
  // the top of a thirteen-screen summary (measured 2026-09-19: the sentence they had
  // just liked sat five screens down). Runs once per (content, focusMs).
  useEffect(() => {
    if (focusMs == null || !Number.isFinite(focusMs) || !rootRef.current) return;
    const marks = Array.from(rootRef.current.querySelectorAll<HTMLElement>('[data-section-ms]'));
    if (!marks.length) return;
    const at = (el: HTMLElement) => Number(el.dataset.sectionMs);
    const target = marks.filter((el) => at(el) <= focusMs).pop() ?? marks[0];
    const heading = target.closest('h2, h3, h4, h5') ?? target;
    heading.scrollIntoView({ block: 'start', behavior: 'auto' });
    heading.classList.add('bg-primary/10', 'rounded', 'transition-colors', 'duration-1000');
    const timer = window.setTimeout(() => heading.classList.remove('bg-primary/10'), 2500);
    return () => window.clearTimeout(timer);
  }, [prepared, focusMs]);

  if (!prepared.trim()) return null;

  return (
    <div ref={rootRef} className="text-xl md:text-lg leading-relaxed md:leading-[1.9] text-foreground">
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
            <h3 className="scroll-mt-24 text-2xl md:text-xl font-bold tracking-tight leading-tight mt-8 mb-2">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="scroll-mt-24 text-xl md:text-lg font-semibold leading-snug text-foreground mt-7 mb-2">{children}</h4>
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
            <blockquote className="border-l-[3px] border-border dark:border-muted-foreground/60 pl-5 my-5 text-foreground/70 dark:text-foreground/85 italic">{children}</blockquote>
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
                  data-section-ms={ms}
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
