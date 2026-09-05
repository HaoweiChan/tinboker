import React, { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { getStockInstitutional } from '@/services/api/stocks';
import type { InstitutionalRow } from '@/validation/schemas';

interface InstitutionalFlowCardProps {
  symbol: string;
  className?: string;
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
const Bar: React.FC<{ value: number; maxAbs: number; x: number; w: number; mid: number; half: number; title: string }> = ({ value, maxAbs, x, w, mid, half, title }) => {
  const trend = useStockTrendColor(value);
  const h = maxAbs > 0 ? (Math.abs(value) / maxAbs) * half : 0;
  return <rect x={x} y={value >= 0 ? mid - h : mid} width={w} height={Math.max(h, value === 0 ? 0 : 1)} fill={trend.lineColor} opacity={0.85}><title>{title}</title></rect>;
};

/** 三大法人 daily net buy/sell for one TW ticker, from the warmed institutional table.
 *  Hidden for US tickers and for tickers with no rows. */
export const InstitutionalFlowCard: React.FC<InstitutionalFlowCardProps> = ({ symbol, className }) => {
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

  const W = 600, H = 140, PAD = 4;
  const mid = H / 2, half = H / 2 - PAD;
  const slot = (W - PAD * 2) / values.length;
  const barW = Math.max(1, slot * 0.7);
  const first = values[0]?.date.slice(5).replace('-', '/');
  const last = values[values.length - 1]?.date.slice(5).replace('-', '/');

  return (
    <div className={cn('bg-card border border-border rounded-md p-5', className)}>
      <div className="flex items-center justify-between gap-3 mb-3.5 flex-wrap">
        <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">三大法人買賣超</h3>
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
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[140px]" role="img" aria-label={`${SERIES.find((s) => s.key === series)!.label}近 ${values.length} 個交易日買賣超`}>
        <line x1={0} x2={W} y1={mid} y2={mid} className="stroke-border" strokeWidth={1} />
        {values.map((p, i) => (
          <Bar key={p.date} value={p.v} maxAbs={maxAbs} x={PAD + i * slot + (slot - barW) / 2} w={barW} mid={mid} half={half} title={`${p.date} ${fmtLots(p.v)}`} />
        ))}
      </svg>
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
    </div>
  );
};

const Stat: React.FC<{ value: number; text?: string }> = ({ value, text }) => {
  const trend = useStockTrendColor(value);
  return <div className="text-sm font-mono tabular-nums font-semibold" style={{ color: value === 0 ? undefined : trend.lineColor }}>{text ?? fmtLots(value)}</div>;
};
