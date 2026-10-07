import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronUp, Play, Share2 } from 'lucide-react';
import { Card } from '@/components/ui';
import { Change, PodAvatar, SentimentChip } from '@/components/redesign';
import { StockCardShareModal } from '@/components/charts/StockCardShareModal';
import { renderThemeCardPng } from '@/lib/themeCardImage';
import { useAppStore } from '@/store/useAppStore';
import { SaveCheck } from '@/components/financial/SaveCheck';
import { formatDate } from '@/lib/date';
import { cn } from '@/lib/utils';
import { windowReturnsKey } from '@/hooks/useTickerWindowReturns';
import type { PickWindowReturns } from '@/services/types';
import type { ThemeCardData, ThemeMention } from '@/services/api/themeViews';

interface ThemeCardProps {
  card: ThemeCardData;
  /** Forward returns keyed `"{TICKER}:{reference_ms}"`, from useTickerWindowReturns. */
  windowsMap: Map<string, PickWindowReturns>;
  podcastImage?: string;
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
  /** 我的清單 state and toggle; the corner check is hidden when no toggle is given. */
  saved?: boolean;
  onToggleSaved?: () => void;
  className?: string;
}

const METRICS: { key: 'since' | 'd7' | 'd30' | 'd90'; label: string }[] = [
  { key: 'since', label: '自提及' },
  { key: 'd7', label: '7天' },
  { key: 'd30', label: '30天' },
  { key: 'd90', label: '90天' },
];

/** 看多/看空 reuse the stock card's chip (it follows the member's red/green setting);
 *  多空並陳 has no direction, so it gets a neutral one. */
const StanceChip: React.FC<{ stance: ThemeMention['stance'] }> = ({ stance }) =>
  stance === 'mixed'
    ? <span className="rounded border border-border bg-muted px-1.5 py-0.5 text-xs font-medium text-foreground/80">多空並陳</span>
    : <SentimentChip sentiment={stance === 'bullish' ? 'BULLISH' : 'BEARISH'} />;

/** Mean of the non-null values, or null when none has come due yet. */
function mean(values: (number | null | undefined)[]): number | null {
  const nums = values.filter((v): v is number => v != null && Number.isFinite(v));
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
}

/** A theme a show has been talking about: when it started, what it said, and how the
 *  companies it named have done since that FIRST mention. */
export const ThemeCard: React.FC<ThemeCardProps> = ({ card, windowsMap, podcastImage, onPlaySegment, saved = false, onToggleSaved, className }) => {
  const [open, setOpen] = useState(false);
  const [sharing, setSharing] = useState(false);
  const colorMode = useAppStore((st) => st.stockColorMode);
  const first = card.mentions[0];
  const latest = card.mentions[card.mentions.length - 1];
  const rows = card.tickers.map((t) => ({
    ...t,
    windows: windowsMap.get(windowReturnsKey(t.ticker, card.first_ms)),
  }));
  const averages = METRICS.map((m) => ({ ...m, value: mean(rows.map((r) => r.windows?.[m.key])) }));

  return (
    <Card className={cn('p-4', className)}>
      <div className="flex items-start gap-3">
        <PodAvatar src={podcastImage} name={card.podcaster} kind="solid" size={36} className="w-9 h-9 rounded-md object-cover shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground truncate">{card.podcaster}</span>
            <span className="text-xs text-muted-foreground tabular-nums shrink-0">{formatDate(card.first_ms)} 起</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="font-semibold text-lg text-foreground">{card.theme_label}</span>
            <StanceChip stance={latest.stance} />
            {latest.conviction === 'tentative' && (
              <span className="rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground">語氣保留</span>
            )}
          </div>
        </div>
        {/* Actions, apart from the date: share, then the bookmark as the right anchor. */}
        <div className="-mr-2 -mt-2.5 flex shrink-0 items-center">
          <button
            type="button"
            aria-label="分享圖卡"
            title="分享圖卡"
            onClick={() => setSharing(true)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <Share2 size={14} />
          </button>
          {onToggleSaved && <SaveCheck saved={saved} onToggle={onToggleSaved} className="-ml-2" />}
        </div>
      </div>
      {sharing && (
        <StockCardShareModal
          ticker={card.theme_label}
          load={() => renderThemeCardPng({ card, podcastImage, rows, averages, colorMode })}
          onClose={() => setSharing(false)}
        />
      )}

      <p className={cn('text-base text-foreground/85 leading-relaxed mt-3', !open && 'line-clamp-3')}>{first.thesis}</p>

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground mt-3">節目沒有點名個股，這個題材沒有可計算的走勢。</p>
      ) : (
        <>
          <div className="mt-3 flex items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {card.tickers_source === 'members' ? '題材成分股（節目未點名）' : '節目點名個股'}
            </span>
            {rows.length > 1 && <span className="text-xs text-muted-foreground shrink-0">{rows.length} 檔平均</span>}
          </div>
          <div className="grid grid-cols-4 gap-2 mt-1.5 rounded-md bg-muted/40 py-2">
            {averages.map(({ key, label, value }) => (
              <div key={key} className="text-center">
                <div className="text-xs text-muted-foreground">{label}</div>
                <Change value={value} />
              </div>
            ))}
          </div>
          {/* One row that scrolls sideways at every width, so cards in a grid keep the
             same height however many stocks they list. The right edge fades to show
             there is more, and the trailing padding lets the last tile clear the fade.
             Touch swipes with no scrollbar; a mouse gets a hairline one (scroll-quiet),
             whose space is reserved even when nothing overflows (md:overflow-x-scroll) so
             a two-stock card is exactly as tall as a nine-stock one. */}
          <ul
            aria-label="成分股走勢"
            className="scroll-quiet mt-2 flex snap-x gap-2 overflow-x-auto pb-1.5 pr-8 md:overflow-x-scroll [mask-image:linear-gradient(to_right,black_calc(100%-2rem),transparent)]"
          >
            {rows.map((r) => (
              <li key={r.ticker} className="w-36 shrink-0 snap-start rounded-md border border-border p-2.5">
                <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="block hover:text-accent-info">
                  <span className="block truncate text-sm font-medium text-foreground">{r.name}</span>
                  <span className="block font-mono text-xs text-muted-foreground">{r.ticker}</span>
                </Link>
                <dl className="mt-1.5 space-y-0.5">
                  {METRICS.map((m) => (
                    <div key={m.key} className="flex items-baseline justify-between gap-2">
                      <dt className="text-xs text-muted-foreground">{m.label}</dt>
                      <dd><Change value={r.windows?.[m.key] ?? null} className="text-xs" /></dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-10 items-center gap-1 text-xs text-accent-info mt-1 hover:underline"
      >
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {open ? '收合' : card.mentions.length > 1 ? `連續提及 ${card.mentions.length} 集` : '查看這一集'}
      </button>

      {open && (
        <div className="mt-1 pt-3 border-t border-border">
          <ol className="space-y-3">
            {card.mentions.map((m) => (
              <li key={m.episode_id} className="text-sm">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="tabular-nums">{formatDate(m.released_at_ms)}</span>
                  {/* An old mention's episode may be outside the public window: text, not a dead link. */}
                  {m.episode_public ? (
                    <Link to={`/episode/${encodeURIComponent(m.episode_id)}`} className="hover:text-accent-info hover:underline">
                      {m.episode_number ? `EP${m.episode_number}` : '這一集'}
                    </Link>
                  ) : (
                    <span>{m.episode_number ? `EP${m.episode_number}` : '較早的集數'}</span>
                  )}
                  <StanceChip stance={m.stance} />
                  {m.conviction === 'tentative' && <span>語氣保留</span>}
                  {onPlaySegment && m.episode_public && m.start_ms != null && (
                    <button
                      type="button"
                      onClick={() => onPlaySegment(m.episode_id, m.start_ms as number)}
                      className="inline-flex items-center gap-1 text-accent-info hover:underline"
                      aria-label={`從這段開始播放 ${m.episode_number ? `EP${m.episode_number}` : ''}`}
                    >
                      <Play size={12} /> 播放
                    </button>
                  )}
                </div>
                <p className="text-foreground/85 leading-relaxed mt-1">{m.thesis}</p>
                {m.quote && <p className="text-muted-foreground mt-1">「{m.quote}」</p>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
};

export default ThemeCard;
