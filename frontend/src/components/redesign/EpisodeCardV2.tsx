import React from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';
import { PodMark, type PodMarkKind } from './PodMark';
import { ShareMenu } from './ShareMenu';
import { TickerRow, type TickerRowData } from './TickerRow';

export interface EpisodeCardV2Props {
  podcasterName: string;
  podcasterInitial: string;
  podcasterImageUrl?: string | null;
  podcasterKind?: PodMarkKind;
  episodeNumber?: string; // "EP 451"
  timeAgo: string; // "3 小時前"
  durationMinutes?: number;
  title: string;
  summary?: string; // 1-2 line teaser (fallback when keyInsights is absent)
  keyInsights?: string[]; // precomputed bullet takeaways — the episode's essence
  tickers?: TickerRowData[];
  tags?: string[];
  commentCount?: number;
  isNew?: boolean;
  /** Destination — internal route path. */
  href: string;
  /** Render the solid (dark) avatar — used for the most-recent episode. */
  highlight?: boolean;
  /** Optional click handlers for tag / ticker chips (default: navigate via href). */
  onTagClick?: (tag: string) => void;
  /** Episode ID — needed for bookmark toggling from the card. */
  episodeId?: string;
  /** Whether the episode is currently bookmarked. */
  isBookmarked?: boolean;
  /** Called when the user taps bookmark in the share menu. */
  onBookmark?: () => void;
  className?: string;
}

/** The Polymarket-honest episode card. Replaces the legacy glass `EpisodeCard` over time. */
export const EpisodeCardV2: React.FC<EpisodeCardV2Props> = ({
  podcasterName,
  podcasterInitial,
  podcasterImageUrl,
  podcasterKind = 'mute',
  episodeNumber,
  timeAgo,
  durationMinutes,
  title,
  summary,
  keyInsights,
  tickers,
  tags,
  commentCount,
  isNew,
  href,
  highlight = false,
  onTagClick,
  episodeId: _episodeId,
  isBookmarked,
  onBookmark,
  className,
}) => {
  const shareUrl = `${window.location.origin}${href}`;
  const tagLabels = useTagLabels();

  return (
    <Link
      to={href}
      className={cn('group/card relative block bg-card border border-border rounded-[var(--radius-md)] p-4 transition-colors hover:border-foreground/25', className)}
    >
      {/* Podcaster header */}
      <div className="flex items-center gap-2.5 mb-3">
        {podcasterImageUrl ? (
          <img src={podcasterImageUrl} alt="" className="w-7 h-7 rounded-[6px] object-cover shrink-0" />
        ) : (
          <PodMark label={podcasterInitial} kind={highlight ? 'solid' : podcasterKind} size={28} />
        )}
        <div className="min-w-0 flex-1 text-sm truncate">
          <span className="font-semibold text-foreground">{podcasterName}</span>
          <span className="text-muted-foreground ml-1.5">
            {episodeNumber ? `${episodeNumber} · ` : ''}
            {timeAgo}
          </span>
        </div>
        <div className="shrink-0 sm:opacity-0 sm:group-hover/card:opacity-100 sm:transition-opacity">
          <ShareMenu
            shareUrl={shareUrl}
            shareTitle={`${podcasterName} — ${title}`}
            isBookmarked={isBookmarked}
            onBookmark={onBookmark}
          />
        </div>
      </div>

      {/* Title */}
      <h3 className="text-lg font-medium leading-[1.35] tracking-[-0.005em] mb-2 text-foreground line-clamp-2">{title}</h3>

      {/* Essence — precomputed key-insight bullets, else the plain teaser */}
      {keyInsights && keyInsights.length > 0 ? (
        <ul className="grid gap-1 text-sm leading-[1.5] text-muted-foreground mb-3.5">
          {keyInsights.slice(0, 3).map((insight, i) => (
            <li key={i} className="grid grid-cols-[10px_1fr] gap-2">
              <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-accent-info shrink-0" />
              <span>{insight}</span>
            </li>
          ))}
        </ul>
      ) : (
        summary && <p className="text-sm leading-[1.55] text-muted-foreground mb-3.5 line-clamp-2">{summary}</p>
      )}

      {/* Ticker rows */}
      {tickers && tickers.length > 0 && (
        <div className="flex flex-col gap-1.5 mb-3">
          {tickers.slice(0, 4).map((t) => (
            <TickerRow key={t.symbol} ticker={t} />
          ))}
        </div>
      )}

      {/* Tags */}
      {tags && tags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-3">
          {tags.slice(0, 4).map((tag) =>
            onTagClick ? (
              <button
                key={tag}
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onTagClick(tag);
                }}
                className="text-2xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground hover:bg-accent-info-soft hover:text-accent-info transition-colors"
              >
                #{tagLabelFor(tag, tagLabels)}
              </button>
            ) : (
              <span key={tag} className="text-2xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                #{tagLabelFor(tag, tagLabels)}
              </span>
            ),
          )}
        </div>
      )}

      {/* Footer — only when there's something to show */}
      {(durationMinutes != null || commentCount != null || isNew) && (
        <div className="flex items-center gap-2.5 pt-2.5 border-t border-border text-xs text-muted-foreground">
          {durationMinutes != null && <span>{durationMinutes} 分鐘</span>}
          {durationMinutes != null && commentCount != null && <span aria-hidden>·</span>}
          {commentCount != null && <span>{commentCount} 則討論</span>}
          {isNew && (
            <span className="ml-auto inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-semibold uppercase tracking-[0.06em] bg-accent-info-soft text-accent-info">
              NEW
            </span>
          )}
        </div>
      )}
    </Link>
  );
};
