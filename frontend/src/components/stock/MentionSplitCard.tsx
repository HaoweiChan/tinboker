import React, { useMemo } from 'react';
import { SentBar } from '@/components/redesign';
import { aggregateSentiment, type SentimentBreakdown } from '@/lib/sentiment';
import type { TickerInsight } from '@/services/types';

interface MentionSplitCardProps {
  insights: TickerInsight[];
}

const DAY_MS = 86400e3;
const HORIZONS = ['短期', '中期', '長期'] as const;
const HORIZON_CLASS: Record<string, string> = {
  短期: 'bg-accent-info',
  中期: 'bg-primary',
  長期: 'bg-accent-warning',
  其他: 'bg-muted-foreground/40',
};

function within(insights: TickerInsight[], days: number): TickerInsight[] {
  const since = Date.now() - days * DAY_MS;
  return insights.filter((i) => Date.parse(i.podcast_launch_time) >= since);
}

/** Bullish / neutral / bearish split over 30 and 90 days, plus the time-horizon mix,
 *  from the same by-ticker insights the crawler description is built from. */
export const MentionSplitCard: React.FC<MentionSplitCardProps> = ({ insights }) => {
  const rows = useMemo(
    () =>
      [30, 90].map((days) => ({
        days,
        b: aggregateSentiment(within(insights, days).map((i) => ({ sentiment_label: i.sentiment_label }))),
      })),
    [insights],
  );
  const horizons = useMemo(() => {
    const counts = new Map<string, number>();
    for (const i of insights) {
      const key = (HORIZONS as readonly string[]).includes(i.time_horizon) ? i.time_horizon : '其他';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const order = [...HORIZONS, '其他'].filter((k) => counts.has(k));
    const total = insights.length;
    return { total, items: order.map((k) => ({ label: k, n: counts.get(k) ?? 0, pct: total ? ((counts.get(k) ?? 0) / total) * 100 : 0 })) };
  }, [insights]);

  if (insights.length === 0) return null;

  const counts = (b: SentimentBreakdown) => (
    <span className="text-xs tabular-nums">
      <span className="text-sentiment-bull">多 {b.bull}</span> · <span className="text-muted-foreground">中 {b.neutral}</span> ·{' '}
      <span className="text-sentiment-bear">空 {b.bear}</span>
    </span>
  );

  return (
    <div className="bg-card border border-border rounded-md p-5">
      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">Podcast 觀點分佈</h3>
      <div className="flex flex-col gap-3">
        {rows.map(({ days, b }) => (
          <div key={days}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">近 {days} 天 · {b.total} 集</span>
              {b.total > 0 ? counts(b) : <span className="text-xs text-muted-foreground">—</span>}
            </div>
            {b.total > 0 ? <SentBar bull={b.bull} neutral={b.neutral} bear={b.bear} /> : <div className="sent-bar opacity-30" />}
          </div>
        ))}
        <div className="pt-3 border-t border-border/60">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">時間框架 · 近 90 天</span>
            <span className="text-xs tabular-nums text-muted-foreground">
              {horizons.items.map((h, i) => (
                <React.Fragment key={h.label}>
                  {i > 0 && ' · '}
                  {h.label} {h.n}
                </React.Fragment>
              ))}
            </span>
          </div>
          <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted" aria-label={horizons.items.map((h) => `${h.label} ${h.n}`).join(' / ')}>
            {horizons.items.map((h) => (
              <span key={h.label} className={HORIZON_CLASS[h.label]} style={{ width: `${h.pct}%` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
