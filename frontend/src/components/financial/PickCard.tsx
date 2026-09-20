import React, { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Play, Mic, Layers } from 'lucide-react';
import { Change, SentimentChip, ShareMenu, PodAvatar } from '@/components/redesign';
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
   *  length > 1, the row shows a "連續 N 次" badge + an occurrence timeline in the
   *  expanded panel. */
  mentions?: TickerInsight[];
  /** False when the caller renders its own date-group headers above rows that
   *  share a mention date (see PicksPage 最新 view) — omits the per-row date on
   *  the mobile line so the group header is the only date shown. */
  showDate?: boolean;
  className?: string;
}

type MetricKey = 'since' | 'd7' | 'd30' | 'd90';

// "自提及" (since mention → today) is always available once a baseline close
// exists; the 7/30/90D windows fill in as each elapses ("—" until then).
const METRICS: { key: MetricKey; label: string; days: number }[] = [
  { key: 'since', label: '自提及', days: 0 },
  { key: 'd7', label: '7天', days: 7 },
  { key: 'd30', label: '30天', days: 30 },
  { key: 'd90', label: '90天', days: 90 },
];

interface MetricCell {
  key: MetricKey;
  label: string;
  kind: 'matured' | 'pending' | 'dash';
  value?: number;
  pendingText?: string;
}

/** One metric's cell: a matured return, a countdown while pending, or a dash
 *  for the rare case a window elapsed with no close data. */
function computeCell(
  m: (typeof METRICS)[number],
  windows: PickWindowReturns | undefined,
  deltaDays: number,
): MetricCell {
  const v = windows ? windows[m.key] : null;
  if (v != null) return { key: m.key, label: m.label, kind: 'matured', value: v };
  if (m.key === 'since') {
    // "Since mention" has no return until the market has closed after the
    // mention (the backend leaves it null over a weekend / same day).
    return { key: m.key, label: m.label, kind: 'pending', pendingText: '待收盤' };
  }
  if (deltaDays < m.days) {
    const remaining = m.days - deltaDays;
    return {
      key: m.key,
      label: m.label,
      kind: 'pending',
      pendingText: m.days === 7 ? `剩餘 ${remaining} 天` : `${remaining} 天後揭曉`,
    };
  }
  return { key: m.key, label: m.label, kind: 'dash' };
}

function renderCell(c: MetricCell, sizeClass = 'text-2xs') {
  if (c.kind === 'matured') return <Change value={c.value} className={sizeClass} />;
  if (c.kind === 'pending') {
    // Countdown text ("28 天後揭曉") runs noticeably longer than a formatted
    // return — always render it at the micro-label size so it fits the narrow
    // desktop return columns instead of bleeding into the next one.
    return <span className="text-2xs text-muted-foreground/50 whitespace-nowrap">{c.pendingText}</span>;
  }
  return <span className={cn(sizeClass, 'text-muted-foreground/50')}>—</span>;
}

// Shared column template so the desktop header row and every data row line up
// like a table: 標的 | 節目 | 日期 | 自提及 | 7天 | 30天 | 90天 | chevron.
const ROW_GRID_COLS = 'md:grid-cols-[minmax(0,1fr)_8rem_4.25rem_4.25rem_4.25rem_4.25rem_4.25rem_1.25rem]';

/** Muted table header for the desktop (md+) row layout below. Render once above
 *  the list, inside the same bordered panel. */
export const PickListHeader: React.FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      'hidden md:grid md:items-center md:gap-3 px-3 py-1.5 text-2xs uppercase tracking-wide text-muted-foreground',
      ROW_GRID_COLS,
      className,
    )}
  >
    <span>標的</span>
    <span>節目</span>
    <span>日期</span>
    {METRICS.map((m) => (
      <span key={m.key} className="text-right">{m.label}</span>
    ))}
    <span aria-hidden="true" />
  </div>
);

/** Podket-style pick row: collapsed to a scannable line (ticker · podcaster ·
 *  headline return), expandable to the full thesis, 看多理由/風險 with
 *  play-at-timestamp, repeat-mention history, and share. Renders as one row of
 *  a bordered list — the container (PicksPage / PodcasterPage) supplies the
 *  panel chrome and `divide-y` between rows. */
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
  showDate = true,
  className,
}) => {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  const ticker = displayTicker || pick.ticker;
  const sentiment = normalizeSentiment(pick.sentiment_label);
  const dateLabel = formatDate(pick.podcast_launch_time);
  const podcaster = pick.podcaster || '';
  const repeatCount = mentions && mentions.length > 1 ? mentions.length : 0;
  const canPlay = typeof onPlaySegment === 'function';

  // Days elapsed since the mention — drives the forward-window countdown text
  // ("剩餘 N 天" / "N 天後揭曉") while a window hasn't matured yet.
  const mentionMs = Date.parse(pick.podcast_launch_time);
  const deltaDays = Number.isFinite(mentionMs)
    ? Math.max(0, Math.floor((Date.now() - mentionMs) / 86_400_000))
    : 9999;

  const cells = METRICS.map((m) => computeCell(m, windows, deltaDays));
  const cellMap = new Map(cells.map((c) => [c.key, c]));

  // Headline = the most mature matured window (90 → 30 → 7 → since). Nothing
  // matured yet → fall back to the single most relevant countdown, in
  // chronological order (since resolves first, then 7/30/90D).
  const headline =
    (['d90', 'd30', 'd7', 'since'] as MetricKey[])
      .map((k) => cellMap.get(k)!)
      .find((c) => c.kind === 'matured') ??
    (['since', 'd7', 'd30', 'd90'] as MetricKey[])
      .map((k) => cellMap.get(k)!)
      .find((c) => c.kind !== 'dash') ??
    cellMap.get('since')!;

  // Up to 2 other matured windows, compact, longest-first — pending ones are
  // simply omitted. Capped at 2 so the podcaster name on the mobile row never
  // gets squeezed to nothing when all 4 windows have matured.
  const otherCells = (['d90', 'd30', 'd7', 'since'] as MetricKey[])
    .filter((k) => k !== headline.key)
    .map((k) => cellMap.get(k)!)
    .filter((c) => c.kind === 'matured')
    .slice(0, 2);

  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          'w-full min-h-11 text-left px-3 py-2 transition-colors hover:bg-muted/30',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
          'md:grid md:items-center md:gap-3',
          ROW_GRID_COLS,
        )}
      >
        {/* Phone (< md): two-line layout */}
        <div className="md:hidden flex flex-col gap-1 min-w-0">
          <div className="flex items-center justify-between gap-2 min-w-0">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="font-mono font-semibold text-sm text-foreground shrink-0">{ticker}</span>
              {displayName && (
                <span className="text-xs text-muted-foreground truncate min-w-0">{displayName}</span>
              )}
              {sentiment && <SentimentChip sentiment={sentiment} className="shrink-0" />}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {headline.kind === 'matured' ? (
                <>
                  <span className="text-2xs text-muted-foreground/70">{headline.label}</span>
                  <Change value={headline.value} className="text-sm" />
                </>
              ) : (
                <span className="text-xs text-muted-foreground/60 whitespace-nowrap">{headline.pendingText ?? '—'}</span>
              )}
              <ChevronDown
                size={14}
                className={cn('text-muted-foreground/60 transition-transform shrink-0', expanded && 'rotate-180')}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 min-w-0">
            <div className="flex items-center gap-1.5 min-w-0 flex-1 text-2xs text-muted-foreground">
              <PodAvatar
                src={podcastImage}
                name={podcaster || pick.ticker}
                kind="solid"
                size={16}
                className="w-4 h-4 rounded-full object-cover shrink-0"
              />
              <span className="truncate">{podcaster}</span>
              {showDate && dateLabel && <span className="tabular-nums shrink-0">· {dateLabel}</span>}
              {repeatCount > 0 && (
                <span className="inline-flex items-center gap-0.5 shrink-0">
                  <Layers size={10} className="shrink-0" />
                  連續 {repeatCount} 次
                </span>
              )}
            </div>
            {otherCells.length > 0 && (
              <div className="flex items-center gap-1.5 shrink-0 text-2xs text-muted-foreground">
                {otherCells.map((c) => (
                  <span key={c.key} className="flex items-baseline gap-0.5 whitespace-nowrap">
                    <span className="text-muted-foreground/70">{c.label}</span>
                    {renderCell(c)}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Desktop (md+): one-line table row — `contents` makes these direct
            grid items of the button, so columns line up with PickListHeader. */}
        <div className="hidden md:contents">
          <div className="min-w-0 flex items-center gap-2">
            <span className="font-mono font-semibold text-sm text-foreground shrink-0">{ticker}</span>
            {displayName && <span className="text-sm text-muted-foreground truncate min-w-0">{displayName}</span>}
            {sentiment && <SentimentChip sentiment={sentiment} className="shrink-0" />}
            {repeatCount > 0 && (
              <span className="inline-flex items-center gap-0.5 shrink-0 text-2xs text-muted-foreground">
                <Layers size={10} className="shrink-0" />
                連續 {repeatCount}
              </span>
            )}
          </div>
          <div className="min-w-0 flex items-center gap-1.5 text-sm text-muted-foreground">
            <PodAvatar
              src={podcastImage}
              name={podcaster || pick.ticker}
              kind="solid"
              size={18}
              className="w-[18px] h-[18px] rounded-full object-cover shrink-0"
            />
            <span className="truncate">{podcaster}</span>
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">{showDate ? dateLabel : ''}</span>
          {METRICS.map((m) => (
            <span key={m.key} className="text-right">{renderCell(cellMap.get(m.key)!, 'text-sm')}</span>
          ))}
          <ChevronDown
            size={16}
            className={cn('text-muted-foreground/60 transition-transform justify-self-end', expanded && 'rotate-180')}
          />
        </div>
      </button>

      {expanded && (
        <div id={panelId} className="px-3 pb-3 pt-2 space-y-3 border-t border-border/60">
          <div className="flex items-center gap-3 flex-wrap pt-1">
            <Link
              to={`/stock/${encodeURIComponent(ticker)}`}
              className="text-xs font-medium text-accent-info hover:underline"
            >
              查看個股 →
            </Link>
            <ShareMenu
              shareUrl={shareUrl}
              shareTitle={`${podcaster} 看${sentiment === 'BEARISH' ? '空' : '多'} ${ticker}｜TinBoker`}
              className="ml-auto"
            />
          </div>

          {/* Phone-only: the full 4-cell return grid, so every number and every
              countdown stays reachable even though the collapsed row only
              surfaces the headline + other matured windows. */}
          <div className="grid grid-cols-4 gap-2 md:hidden">
            {cells.map((c) => (
              <div key={c.key} className="text-center">
                <div className="text-2xs uppercase tracking-wide text-muted-foreground">{c.label}</div>
                {renderCell(c, 'text-sm')}
              </div>
            ))}
          </div>

          {pick.bluf_thesis && (
            <p className="text-sm text-muted-foreground leading-relaxed">{pick.bluf_thesis}</p>
          )}

          {pick.reasons?.length > 0 && (
            <Segment title="看多理由" items={pick.reasons} tone="bull" episodeId={pick.episode_id} onPlaySegment={canPlay ? onPlaySegment : undefined} />
          )}
          {pick.risks?.length > 0 && (
            <Segment title="風險提示" items={pick.risks} tone="bear" episodeId={pick.episode_id} onPlaySegment={canPlay ? onPlaySegment : undefined} />
          )}

          {repeatCount > 0 && mentions && (
            <div>
              <h4 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                近期點名紀錄
              </h4>
              <ol className="space-y-2.5">
                {mentions.map((m) => (
                  <li key={`${m.episode_id}-${m.ticker}`} className="relative pl-3 border-l-2 border-border">
                    <div className="flex items-center gap-2 text-2xs text-muted-foreground">
                      <span className="tabular-nums shrink-0">
                        {formatDate(m.podcast_launch_time)}
                      </span>
                      {m.episode_title && (m.episode_public === false ? (
                        <span className="truncate" title={m.episode_title}>{m.episode_title}</span>
                      ) : (
                        <Link
                          to={`/episode/${encodeURIComponent(m.episode_id)}`}
                          className="truncate hover:text-accent-info"
                          title={m.episode_title}
                        >
                          {m.episode_title}
                        </Link>
                      ))}
                    </div>
                    {m.bluf_thesis && (
                      <p className="text-xs text-muted-foreground/90 leading-relaxed mt-0.5 line-clamp-2">
                        {m.bluf_thesis}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Picks read further back than the public episode window: an old pick's
              episode may no longer be served, so show its title without a link. */}
          {episodeTitle && (pick.episode_public === false ? (
            <span className="flex items-center gap-1 text-2xs text-muted-foreground/80 min-w-0" title={episodeTitle}>
              <Mic size={11} className="shrink-0" />
              <span className="truncate">{episodeTitle}</span>
            </span>
          ) : (
            <Link
              to={`/episode/${encodeURIComponent(pick.episode_id)}`}
              className="flex items-center gap-1 text-2xs text-muted-foreground/80 hover:text-accent-info min-w-0"
              title={episodeTitle}
            >
              <Mic size={11} className="shrink-0" />
              <span className="truncate">{episodeTitle}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
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
