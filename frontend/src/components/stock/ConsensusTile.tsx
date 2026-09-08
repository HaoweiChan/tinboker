import React, { useMemo } from 'react';
import { SentBar } from '@/components/redesign';
import { CountUp } from '@/components/common/CountUp';
import { aggregateSentiment } from '@/lib/sentiment';
import { cn } from '@/lib/utils';
import { useGrowIn } from '@/hooks/useMotion';
import type { TickerInsight } from '@/services/types';

interface ConsensusTileProps {
  insights: TickerInsight[];
  className?: string;
  /** Tile label; the stock page says 近 30 天 Podcast 共識, a show page says 近 30 天立場. */
  title?: string;
}

const DAY_MS = 86400e3;
const HORIZONS = ['短期', '中期', '長期'] as const;
const WEEKS = 13;

// Monday (UTC) of the ISO week containing `ms`, as a day index.
const weekOf = (ms: number) => { const d = new Date(ms); const dow = (d.getUTCDay() + 6) % 7; return Math.floor((ms - dow * DAY_MS) / (7 * DAY_MS)); };

/** The page's headline tile: how the podcasts lean on this ticker over the last 30 days,
 *  with the 90-day time-horizon mix underneath. Tinted by the dominant stance. */
export const ConsensusTile: React.FC<ConsensusTileProps> = ({ insights, className, title = '近 30 天 Podcast 共識' }) => {
  const b = useMemo(() => {
    const since = Date.now() - 30 * DAY_MS;
    return aggregateSentiment(insights.filter((i) => Date.parse(i.podcast_launch_time) >= since).map((i) => ({ sentiment_label: i.sentiment_label })));
  }, [insights]);
  const horizons = useMemo(() => {
    const counts = new Map<string, number>();
    for (const i of insights) {
      const key = (HORIZONS as readonly string[]).includes(i.time_horizon) ? i.time_horizon : '其他';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...HORIZONS, '其他'].filter((k) => counts.has(k)).map((k) => ({ label: k, n: counts.get(k) ?? 0 }));
  }, [insights]);

  // Stacked bull / neutral / bear count per ISO week, oldest → newest, last 13 weeks.
  const weeks = useMemo(() => {
    const now = weekOf(Date.now());
    const rows = Array.from({ length: WEEKS }, () => ({ bull: 0, neu: 0, bear: 0 }));
    for (const i of insights) {
      const idx = WEEKS - 1 - (now - weekOf(Date.parse(i.podcast_launch_time)));
      if (idx < 0 || idx >= WEEKS) continue;
      const k = aggregateSentiment([{ sentiment_label: i.sentiment_label }]);
      if (k.bull) rows[idx].bull++; else if (k.bear) rows[idx].bear++; else rows[idx].neu++;
    }
    const max = rows.reduce((m, r) => Math.max(m, r.bull + r.neu + r.bear), 1);
    return { rows, max };
  }, [insights]);
  const grown = useGrowIn();

  const lean = b.total === 0 ? 'none' : b.bull > b.bear ? 'bull' : b.bear > b.bull ? 'bear' : 'flat';
  const tint = lean === 'bull' ? 'bg-sentiment-bull-soft/60 border-sentiment-bull/25' : lean === 'bear' ? 'bg-sentiment-bear-soft/60 border-sentiment-bear/25' : 'bg-card border-border';
  const big = lean === 'bear' ? b.bear : b.bull;
  const bigCls = lean === 'bear' ? 'text-sentiment-bear' : lean === 'bull' ? 'text-sentiment-bull' : 'text-foreground';
  const bigLabel = lean === 'bear' ? '集看空' : '集看多';

  return (
    <div className={cn('rounded-[10px] border p-5 flex flex-col justify-between gap-4', tint, className)}>
      <div className={cn('text-xs', lean === 'bull' ? 'text-sentiment-bull' : lean === 'bear' ? 'text-sentiment-bear' : 'text-muted-foreground')}>{title}</div>
      {b.total > 0 ? (
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className={cn('font-mono tabular-nums font-semibold leading-none text-[44px] lg:text-[52px]', bigCls)}><CountUp value={big} /></span>
            <span className="text-base">{bigLabel}</span>
          </div>
          <div className="text-sm text-muted-foreground">
            {lean === 'bear' ? <>{b.bull} 集看多，</> : null}{b.neutral} 集中立{lean !== 'bear' ? <>，{b.bear} 集看空</> : null}
          </div>
        </div>
      ) : (
        <div className="text-base text-muted-foreground">近 30 天沒有節目談到這檔。</div>
      )}
      {insights.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-end gap-1 h-16" aria-label={`每週提及集數，近 ${WEEKS} 週`}>
            {weeks.rows.map((r, i) => {
              const total = r.bull + r.neu + r.bear;
              const h = (total / weeks.max) * 100;
              return (
                <div key={i} className="flex-1 flex flex-col justify-end h-full" title={`${total} 集 · 多 ${r.bull} 中 ${r.neu} 空 ${r.bear}`}>
                  <div className="flex flex-col-reverse rounded-sm overflow-hidden" style={{ height: grown ? `${h}%` : '0%', transition: 'height 600ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 30}ms` }}>
                    {r.bull > 0 && <span className="w-full bg-sentiment-bull" style={{ flex: r.bull }} />}
                    {r.neu > 0 && <span className="w-full bg-muted-foreground/40" style={{ flex: r.neu }} />}
                    {r.bear > 0 && <span className="w-full bg-sentiment-bear" style={{ flex: r.bear }} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-2xs text-muted-foreground"><span>每週提及集數</span><span>近 {WEEKS} 週</span></div>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {b.total > 0 && <SentBar bull={b.bull} neutral={b.neutral} bear={b.bear} />}
        {insights.length > 0 && (
          <div className="text-xs text-muted-foreground tabular-nums">
            {horizons.map((h, i) => <React.Fragment key={h.label}>{i > 0 && ' · '}{h.label} {h.n}</React.Fragment>)}
            {' · '}共 {insights.length} 則（90 天）
          </div>
        )}
      </div>
    </div>
  );
};
