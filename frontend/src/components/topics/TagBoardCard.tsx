import React from 'react';
import { Link } from 'react-router-dom';
import { Hash } from 'lucide-react';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import type { TrendingTag } from '@/services/api/podcasts';

// Tag identity is amber across the app (sectors are individually colored), so the
// hash chip + discussion-trend sparkline use amber to read as a tag, not a sector.
const TAG_ACCENT = '#F59E0B';

interface TagBoardCardProps {
  tag: TrendingTag;
  /** zh-TW display label, resolved via the tag registry (tag.name is the raw slug). */
  label: string;
}

/**
 * Card in the 熱門標籤 grid — the tag analogue of SectorBoardCard. Tags carry no
 * tickers/price, so the header shows a discussion-volume sparkline (weekly_counts)
 * instead of a change %, and the body lists recent episodes instead of member rows.
 */
export const TagBoardCard: React.FC<TagBoardCardProps> = ({ tag, label }) => {
  const episodes = tag.recent_episodes.slice(0, 4);
  // weekly_counts is most-recent-first from the API; reverse to read old→new like
  // the member sparklines elsewhere on the page.
  const weekly = Array.isArray(tag.weekly_counts) ? [...tag.weekly_counts].reverse() : [];
  const hasTrend = weekly.length > 1 && weekly.some((v) => v > 0);

  return (
    <div
      className="bg-card border border-border dark:border-white/[0.08] rounded-xl overflow-hidden transition-all duration-200
                 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.18)]
                 hover:border-border/80 dark:hover:border-white/[0.14]
                 hover:shadow-[0_4px_16px_-6px_rgba(0,0,0,0.10)] dark:hover:shadow-[0_4px_20px_-6px_rgba(0,0,0,0.35)]"
    >
      {/* ── Card header ─────────────────────────────────────────── */}
      <Link
        to={`/topics/${encodeURIComponent(tag.id)}`}
        className="group flex items-start justify-between gap-3 px-4 pt-3.5 pb-3 border-b border-border/40"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1.5">
            <span
              className="inline-grid place-items-center rounded-md shrink-0"
              style={{ width: 22, height: 22, color: TAG_ACCENT, backgroundColor: `${TAG_ACCENT}24` }}
            >
              <Hash size={13} />
            </span>
            <span className="text-2xs font-medium text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded leading-none shrink-0">
              標籤
            </span>
          </div>
          <span className="text-base font-semibold tracking-[-0.01em] group-hover:text-foreground/80 transition-colors leading-snug block truncate">
            #{label}
          </span>
        </div>

        <div className="shrink-0 flex flex-col items-end gap-1.5 pt-0.5">
          {hasTrend && (
            <SimpleSparkline
              data={weekly}
              isPositive
              color={TAG_ACCENT}
              strokeWidth={1.2}
              fill={false}
              width={56}
              height={20}
              className="opacity-70"
            />
          )}
          <span className="text-2xs text-muted-foreground font-mono tabular-nums">
            {tag.scoped_count} 集
          </span>
        </div>
      </Link>

      {/* ── Recent episodes ─────────────────────────────────────── */}
      {episodes.length > 0 && (
        <div className="px-4 py-2.5 divide-y divide-border/20">
          {episodes.map((ep) => (
            <Link
              key={ep.id}
              to={`/episode/${encodeURIComponent(ep.id)}${ep.podcast_name ? `?podcast=${encodeURIComponent(ep.podcast_name)}` : ''}`}
              className="group/row flex items-center gap-3 py-2 first:pt-0 last:pb-0 -mx-1 px-1 rounded transition-colors hover:bg-muted/40"
            >
              <span className="text-2xs text-foreground/80 truncate flex-1 min-w-0 leading-snug group-hover/row:text-accent-info transition-colors">
                {ep.title || '(無標題)'}
              </span>
              <span className="text-2xs text-muted-foreground truncate max-w-[40%] shrink-0 leading-none">
                {ep.podcast_name}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};
