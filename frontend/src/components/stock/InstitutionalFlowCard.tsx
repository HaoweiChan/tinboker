import React, { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { getStockInstitutional } from '@/services/api/stocks';
import type { InstitutionalRow } from '@/validation/schemas';
import { useGrowIn } from '@/hooks/useMotion';

interface InstitutionalFlowCardProps {
  symbol: string;
  className?: string;
  /** Bento tile: shorter chart, stats on one line. */
  compact?: boolean;
}

type Series = 'total' | 'foreign' | 'trust';
const SERIES: { key: Series; label: string; field: keyof InstitutionalRow }[] = [
  { key: 'total', label: '三大法人', field: 'total_net_shares' },
  { key: 'foreign', label: '外資', field: 'foreign_net_shares' },
  { key: 'trust', label: '投信', field: 'trust_net_shares' },
];

// Shares → 張 (1,000 shares), the unit TW investors read institutional flows in.
const lots = (shares: number) => shares / 1000;
const fmtLots = (shares: number) => {
  const v = lots(shares);
  const abs = Math.abs(v);
  const s = abs >= 10000 ? `${(abs / 10000).toFixed(1)} 萬` : abs >= 1000 ? `${Math.round(abs).toLocaleString('en-US')}` : abs.toFixed(0);
  return `${v < 0 ? '-' : '+'}${s} 張`;
};

// A diverging bar: buy above the axis, sell below, in the market's up/down colours.
const Bar: React.FC<{ value: number; maxAbs: number; x: number; w: number; mid: number; half: number; title: string; grown: boolean; delayMs: number }> = ({ value, maxAbs, x, w, mid, half, title, grown, delayMs }) => {
  const trend = useStockTrendColor(value);
  const h = maxAbs > 0 ? (Math.abs(value) / maxAbs) * half : 0;
  // Scale out of the axis (transform-origin on the mid line, in viewBox units).
  const style = { transform: `scaleY(${grown ? 1 : 0})`, transformOrigin: `0px ${mid}px`, transition: 'transform 600ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${delayMs}ms` } as const;
  return <rect x={x} y={value >= 0 ? mid - h : mid} width={w} height={Math.max(h, value === 0 ? 0 : 1)} fill={trend.lineColor} opacity={0.85} style={style}><title>{title}</title></rect>;
};

/** 三大法人 daily net buy/sell for one TW ticker, from the warmed institutional table.
 *  Hidden for US tickers and for tickers with no rows. */
export const InstitutionalFlowCard: React.FC<InstitutionalFlowCardProps> = ({ symbol, className, compact = false }) => {
  const [rows, setRows] = useState<InstitutionalRow[]>([]);
  const [series, setSeries] = useState<Series>('total');

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setRows([]);
    getStockInstitutional(symbol, 60)
      .then((res) => { if (!cancelled) setRows(res.rows); })
      .catch(() => { if (!cancelled) setRows([]); });
    return () => { cancelled = true; };
  }, [symbol]);

  const field = SERIES.find((s) => s.key === series)!.field;
  const values = useMemo(() => rows.map((r) => ({ date: r.date, v: (r[field] as number | null) ?? 0 })), [rows, field]);
  const maxAbs = useMemo(() => values.reduce((m, p) => Math.max(m, Math.abs(p.v)), 0), [values]);
  const sum = (n: number) => values.slice(-n).reduce((a, p) => a + p.v, 0);
  const net5 = sum(5);
  const net20 = sum(20);
  const streak = useMemo(() => {
    // Consecutive days on the same side, counted from the newest day.
    let n = 0;
    const sign = values.length ? Math.sign(values[values.length - 1].v) : 0;
    if (sign === 0) return 0;
    for (let i = values.length - 1; i >= 0 && Math.sign(values[i].v) === sign; i--) n++;
    return n * sign;
  }, [values]);

  if (rows.length === 0) return null;

  const first = values[0]?.date.slice(5).replace('-', '/');
  const last = values[values.length - 1]?.date.slice(5).replace('-', '/');

  return (
    <div className={cn('bg-card border border-border p-5', compact ? 'rounded-[10px] flex flex-col justify-between gap-2' : 'rounded-md', className)}>
      <div className={cn('flex items-center justify-between gap-3 flex-wrap', compact ? '' : 'mb-3.5')}>
        <h3 className={cn('text-xs text-muted-foreground', compact ? '' : 'font-semibold uppercase tracking-[0.08em]')}>{compact ? '三大法人 · 60 日' : '三大法人買賣超'}</h3>
        <div className="flex items-center gap-0.5 text-2xs">
          {SERIES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setSeries(s.key)}
              className={cn('rounded px-1.5 py-0.5 transition-colors', series === s.key ? 'bg-primary/15 font-semibold text-primary' : 'text-muted-foreground/70 hover:text-foreground')}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {/* key: remount so the bars grow out of the axis again when the data or series changes. */}
      <Bars key={`${series}:${values.length}`} values={values} maxAbs={maxAbs} label={SERIES.find((s) => s.key === series)!.label} height={compact ? 64 : 140} />
      {compact ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground tabular-nums">
          <span>近 5 日 <Stat value={net5} inline /></span>
          <span>近 20 日 <Stat value={net20} inline /></span>
          <span>連續 <Stat value={streak} inline text={streak === 0 ? '—' : `${Math.abs(streak)} 日${streak > 0 ? '買超' : '賣超'}`} /></span>
        </div>
      ) : (
      <>
      <div className="flex items-center justify-between text-2xs text-muted-foreground tabular-nums mt-1">
        <span>{first}</span>
        <span>{last}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-border/60">
        {[
          { label: '近 5 日', value: net5 },
          { label: '近 20 日', value: net20 },
          { label: '連續', value: streak, text: streak === 0 ? '—' : `${Math.abs(streak)} 日${streak > 0 ? '買超' : '賣超'}` },
        ].map((s) => (
          <div key={s.label}>
            <div className="text-2xs uppercase tracking-wider text-muted-foreground mb-0.5">{s.label}</div>
            <Stat value={s.value} text={s.text} />
          </div>
        ))}
      </div>
      </>
      )}
    </div>
  );
};

const W = 600, H = 140, PAD = 4;
const Bars: React.FC<{ values: { date: string; v: number }[]; maxAbs: number; label: string; height?: number }> = ({ values, maxAbs, label, height = H }) => {
  const grown = useGrowIn();
  const mid = height / 2, half = height / 2 - PAD;
  const slot = (W - PAD * 2) / values.length;
  const barW = Math.max(1, slot * 0.7);
  return (
    <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }} role="img" aria-label={`${label}近 ${values.length} 個交易日買賣超`}>
      <line x1={0} x2={W} y1={mid} y2={mid} className="stroke-border" strokeWidth={1} />
      {values.map((p, i) => (
        <Bar key={p.date} value={p.v} maxAbs={maxAbs} x={PAD + i * slot + (slot - barW) / 2} w={barW} mid={mid} half={half} title={`${p.date} ${fmtLots(p.v)}`} grown={grown} delayMs={i * 10} />
      ))}
    </svg>
  );
};

const Stat: React.FC<{ value: number; text?: string; inline?: boolean }> = ({ value, text, inline }) => {
  const trend = useStockTrendColor(value);
  const Tag = inline ? 'span' : 'div';
  return <Tag className={cn('font-mono tabular-nums font-semibold', inline ? 'text-xs' : 'text-sm')} style={{ color: value === 0 ? undefined : trend.lineColor }}>{text ?? fmtLots(value)}</Tag>;
};
