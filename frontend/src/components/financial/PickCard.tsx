import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ChevronDown, ChevronUp, Play, Mic, Layers } from 'lucide-react';
import { Card } from '@/components/ui';
import { Change, SentimentChip, ShareMenu, PodMark } from '@/components/redesign';
import { normalizeSentiment } from '@/lib/sentiment';
import { formatDate } from '@/lib/date';
import { cn } from '@/lib/utils';
import type { PickWindowReturns, TickerInsight } from '@/services/types';

interface PickCardProps {
  pick: TickerInsight;
  /** Forward 7/30/90D returns for this (ticker, mention-date), from useTickerWindowReturns. */
  windows?: PickWindowReturns;
  /** Localized ticker display name (台積電, 輝達, …). */
  displayName?: string;
  /** Canonical symbol to show/link (e.g. 2330 even when the row stored TSM). Defaults to pick.ticker. */
  displayTicker?: string;
  /** Channel cover image; falls back to a PodMark of the podcaster's initial. */
  podcastImage?: string;
  /** Episode title for the footer (TickerInsight only carries episode_id). */
  episodeTitle?: string;
  /** Absolute URL to share (Phase 4 OG route); defaults to the ticker page. */
  shareUrl?: string;
  /** Seek the player to a reason/risk timestamp. When omitted, ▶ buttons are hidden. */
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
  /** All mentions collapsed into this card (newest-first, incl. the master). When
   *  length > 1, the card shows a "近期連續點名 N 次" badge + an occurrence timeline. */
  mentions?: TickerInsight[];
  className?: string;
}

// "自提及" (since mention → today) is always available once a baseline close
// exists; the 7/30/90D windows fill in as each elapses ("—" until then).
const METRICS: { key: 'since' | 'd7' | 'd30' | 'd90'; label: string }[] = [
  { key: 'since', label: '自提及' },
  { key: 'd7', label: '7天' },
  { key: 'd30', label: '30天' },
  { key: 'd90', label: '90天' },
];

/** Podket-style pick card: channel + ticker + sentiment + 7/30/90D returns,
 *  expandable to transcript-anchored 看多理由 / 風險 with play-at-timestamp. */
export const PickCard: React.FC<PickCardProps> = ({
  pick,
  windows,
  displayName,
  displayTicker,
  podcastImage,
  episodeTitle,
  shareUrl,
  onPlaySegment,
  mentions,
  className,
}) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [mentionsOpen, setMentionsOpen] = useState(false);

  const ticker = displayTicker || pick.ticker;
  const sentiment = normalizeSentiment(pick.sentiment_label);
  const dateLabel = formatDate(pick.podcast_launch_time);
  const podcaster = pick.podcaster || '';
  const repeatCount = mentions && mentions.length > 1 ? mentions.length : 0;

  // Days elapsed since the mention — drives the forward-window countdown text
  // (方案一: show "剩餘 N 天" / "N 天後揭曉" instead of bare dashes while a window
  // hasn't matured yet).
  const mentionMs = Date.parse(pick.podcast_launch_time);
  const deltaDays = Number.isFinite(mentionMs)
    ? Math.max(0, Math.floor((Date.now() - mentionMs) / 86_400_000))
    : 9999;

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
            <span className="text-xs text-muted-foreground truncate">{podcaster}</span>
            <span className="text-xs text-muted-foreground tabular-nums shrink-0">{dateLabel}</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <button
              type="button"
              onClick={() => navigate(`/stock/${encodeURIComponent(ticker)}`)}
              className="font-mono font-semibold text-lg text-foreground hover:text-accent-info transition-colors"
            >
              {ticker}
            </button>
            {displayName && <span className="text-sm text-muted-foreground truncate">{displayName}</span>}
            {sentiment && <SentimentChip sentiment={sentiment} />}
            {repeatCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted/70 border border-border px-2 py-0.5 text-2xs font-medium text-muted-foreground">
                <Layers size={11} className="shrink-0" />
                近期連續點名 {repeatCount} 次
              </span>
            )}
          </div>
        </div>
        <ShareMenu
          shareUrl={shareUrl}
          shareTitle={`${podcaster} 看${sentiment === 'BEARISH' ? '空' : '多'} ${ticker}｜TinBoker`}
          className="shrink-0"
        />
      </div>

      {/* Forward 7/30/90D returns — pending windows show a muted countdown, not a bare dash */}
      <div className="grid grid-cols-4 gap-2 mt-3 mb-1">
        {METRICS.map(({ key, label }) => {
          const v = windows ? windows[key] : null;
          let content: React.ReactNode;
          if (key === 'since') {
            // "Since mention" has no return on the day of mention.
            content = deltaDays < 1
              ? <span className="text-2xs text-muted-foreground/50">今日</span>
              : <Change value={v} />;
          } else if (v != null) {
            content = <Change value={v} />;
          } else {
            const wd = key === 'd7' ? 7 : key === 'd30' ? 30 : 90;
            content = deltaDays < wd ? (
              <span className="text-2xs text-muted-foreground/50 whitespace-nowrap">
                {wd === 7 ? `剩餘 ${wd - deltaDays} 天` : `${wd - deltaDays} 天後揭曉`}
              </span>
            ) : (
              // window elapsed but no close data (rare) — keep a plain dash
              <span className="text-sm text-muted-foreground/50">—</span>
            );
          }
          return (
            <div key={key} className="text-center">
              <div className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</div>
              {content}
            </div>
          );
        })}
      </div>

      {/* Thesis + expand toggle */}
      {pick.bluf_thesis && (
        <p className={cn('text-sm text-muted-foreground leading-relaxed mt-2', !expanded && 'line-clamp-2')}>
          {pick.bluf_thesis}
        </p>
      )}

      {(pick.reasons?.length || pick.risks?.length) ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs text-accent-info mt-2 hover:underline"
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

      {repeatCount > 0 && mentions && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setMentionsOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-accent-info hover:underline"
          >
            {mentionsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            查看連續點名集數與摘要
          </button>
          {mentionsOpen && (
            <ol className="mt-2 pt-2 border-t border-border space-y-2.5">
              {mentions.map((m) => (
                <li key={`${m.episode_id}-${m.ticker}`} className="relative pl-3 border-l-2 border-border">
                  <div className="flex items-center gap-2 text-2xs text-muted-foreground">
                    <span className="tabular-nums shrink-0">
                      {formatDate(m.podcast_launch_time)}
                    </span>
                    {m.episode_title && (
                      <Link
                        to={`/episode/${encodeURIComponent(m.episode_id)}`}
                        className="truncate hover:text-accent-info"
                        title={m.episode_title}
                      >
                        {m.episode_title}
                      </Link>
                    )}
                  </div>
                  {m.bluf_thesis && (
                    <p className="text-xs text-muted-foreground/90 leading-relaxed mt-0.5 line-clamp-2">
                      {m.bluf_thesis}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {episodeTitle && (
        <Link
          to={`/episode/${encodeURIComponent(pick.episode_id)}`}
          className="flex items-center gap-1 text-2xs text-muted-foreground/80 hover:text-accent-info mt-3 min-w-0"
          title={episodeTitle}
        >
          <Mic size={11} className="shrink-0" />
          <span className="truncate">{episodeTitle}</span>
        </Link>
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
    <h4 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">{title}</h4>
    <ul className="space-y-1.5">
      {items.map((item, idx) => (
        <li
          key={idx}
          className={cn(
            'flex items-center justify-between gap-2 rounded p-2 text-sm group/item',
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
