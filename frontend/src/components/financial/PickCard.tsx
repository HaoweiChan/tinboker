import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronUp, Play } from 'lucide-react';
import { Card } from '@/components/ui';
import { Change, SentimentChip, ShareMenu, PodMark } from '@/components/redesign';
import { normalizeSentiment } from '@/lib/sentiment';
import { cn } from '@/lib/utils';
import type { PickWindowReturns, TickerInsight } from '@/services/types';

interface PickCardProps {
  pick: TickerInsight;
  /** Forward 7/30/90D returns for this (ticker, mention-date), from useTickerWindowReturns. */
  windows?: PickWindowReturns;
  /** Localized ticker display name (台積電, 輝達, …). */
  displayName?: string;
  /** Channel cover image; falls back to a PodMark of the podcaster's initial. */
  podcastImage?: string;
  /** Episode title for the footer (TickerInsight only carries episode_id). */
  episodeTitle?: string;
  /** Absolute URL to share (Phase 4 OG route); defaults to the ticker page. */
  shareUrl?: string;
  /** Seek the player to a reason/risk timestamp. When omitted, ▶ buttons are hidden. */
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
  className?: string;
}

const WINDOWS: { key: 'd7' | 'd30' | 'd90'; label: string }[] = [
  { key: 'd7', label: '7D' },
  { key: 'd30', label: '30D' },
  { key: 'd90', label: '90D' },
];

/** Podket-style pick card: channel + ticker + sentiment + 7/30/90D returns,
 *  expandable to transcript-anchored 看多理由 / 風險 with play-at-timestamp. */
export const PickCard: React.FC<PickCardProps> = ({
  pick,
  windows,
  displayName,
  podcastImage,
  episodeTitle,
  shareUrl,
  onPlaySegment,
  className,
}) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const sentiment = normalizeSentiment(pick.sentiment_label);
  const dateLabel = pick.podcast_launch_time
    ? new Date(pick.podcast_launch_time).toLocaleDateString()
    : '';
  const podcaster = pick.podcaster || '';

  const canPlay = typeof onPlaySegment === 'function';

  return (
    <Card className={cn('p-4', className)}>
      {/* Header: channel + ticker + sentiment + share */}
      <div className="flex items-start gap-3">
        {podcastImage ? (
          <img src={podcastImage} alt={podcaster} className="w-9 h-9 rounded-md object-cover shrink-0" />
        ) : (
          <PodMark label={(podcaster || pick.ticker || '?').charAt(0)} kind="solid" size={36} />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] text-muted-foreground truncate">{podcaster}</span>
            <span className="text-[12px] text-muted-foreground tabular-nums shrink-0">{dateLabel}</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <button
              type="button"
              onClick={() => navigate(`/stock/${encodeURIComponent(pick.ticker)}`)}
              className="font-mono font-semibold text-[16px] text-foreground hover:text-accent-info transition-colors"
            >
              {pick.ticker}
            </button>
            {displayName && <span className="text-[13px] text-muted-foreground truncate">{displayName}</span>}
            {sentiment && <SentimentChip sentiment={sentiment} />}
          </div>
        </div>
        <ShareMenu
          shareUrl={shareUrl}
          shareTitle={`${podcaster} 看${sentiment === 'BEARISH' ? '空' : '多'} ${pick.ticker}｜TinBoker`}
          className="shrink-0"
        />
      </div>

      {/* Forward 7/30/90D returns */}
      <div className="grid grid-cols-3 gap-2 mt-3 mb-1">
        {WINDOWS.map(({ key, label }) => (
          <div key={key} className="text-center">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
            <Change value={windows ? windows[key] : null} />
          </div>
        ))}
      </div>

      {/* Thesis + expand toggle */}
      {pick.bluf_thesis && (
        <p className={cn('text-[13px] text-muted-foreground leading-relaxed mt-2', !expanded && 'line-clamp-2')}>
          {pick.bluf_thesis}
        </p>
      )}

      {(pick.reasons?.length || pick.risks?.length) ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-[12px] text-accent-info mt-2 hover:underline"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? '收合' : '查看原因'}
        </button>
      ) : null}

      {expanded && (
        <div className="mt-3 pt-3 border-t border-border space-y-3">
          {pick.reasons?.length > 0 && (
            <Segment title="看多理由" items={pick.reasons} tone="bull" episodeId={pick.episode_id} onPlaySegment={canPlay ? onPlaySegment : undefined} />
          )}
          {pick.risks?.length > 0 && (
            <Segment title="風險提示" items={pick.risks} tone="bear" episodeId={pick.episode_id} onPlaySegment={canPlay ? onPlaySegment : undefined} />
          )}
        </div>
      )}

      {episodeTitle && (
        <p className="text-[11px] text-muted-foreground/80 mt-3 truncate" title={episodeTitle}>{episodeTitle}</p>
      )}
    </Card>
  );
};

interface SegmentItem {
  title: string;
  start_time: number;
}

const Segment: React.FC<{
  title: string;
  items: SegmentItem[];
  tone: 'bull' | 'bear';
  episodeId: string;
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
}> = ({ title, items, tone, episodeId, onPlaySegment }) => (
  <div>
    <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">{title}</h4>
    <ul className="space-y-1.5">
      {items.map((item, idx) => (
        <li
          key={idx}
          className={cn(
            'flex items-center justify-between gap-2 rounded p-2 text-[13px] group/item',
            tone === 'bull' ? 'bg-sentiment-bull-soft/40' : 'bg-sentiment-bear-soft/40',
          )}
        >
          <span className="text-foreground/90 min-w-0">{item.title}</span>
          {onPlaySegment && (
            <button
              type="button"
              title="播放片段"
              onClick={() => onPlaySegment(episodeId, item.start_time)}
              className="shrink-0 opacity-50 group-hover/item:opacity-100 text-accent-info transition-opacity"
            >
              <Play size={12} className="fill-current" />
            </button>
          )}
        </li>
      ))}
    </ul>
  </div>
);
