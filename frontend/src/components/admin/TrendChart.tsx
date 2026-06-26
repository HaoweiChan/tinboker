/**
 * Tiny dependency-free SVG line chart for the admin analytics trends.
 *
 * Theme-aware: each series sets its colour via a Tailwind text class (e.g.
 * "text-accent-info") and the line uses stroke="currentColor", so it follows the
 * active theme tokens. Series are index-aligned (callers pass same-length, date-aligned
 * points). Renders a legend with each series' latest value.
 */

import React from 'react';

export interface TrendPoint {
  x: string; // date label
  y: number;
}
export interface TrendSeries {
  name: string;
  colorClass: string; // Tailwind text-* class → drives currentColor
  points: TrendPoint[];
}

const W = 320;
const PAD = 4;

const nf = new Intl.NumberFormat('en-US');

export const TrendChart: React.FC<{
  series: TrendSeries[];
  height?: number;
  format?: (n: number) => string;
}> = ({ series, height = 64, format }) => {
  const fmtVal = format || ((n: number) => nf.format(n));
  const maxLen = Math.max(0, ...series.map((s) => s.points.length));
  const allY = series.flatMap((s) => s.points.map((p) => p.y));

  if (maxLen < 2 || allY.length === 0) {
    return (
      <div className="flex h-16 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground">
        資料累積中…（需要至少兩天）
      </div>
    );
  }

  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const span = maxY - minY || 1;
  const innerH = height - PAD * 2;
  const xAt = (i: number) => (maxLen === 1 ? W / 2 : PAD + (i / (maxLen - 1)) * (W - PAD * 2));
  const yAt = (v: number) => PAD + innerH - ((v - minY) / span) * innerH;

  const dates = series[0]?.points.map((p) => p.x) ?? [];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        {series.map((s: TrendSeries) => {
          const pts = s.points.map((p, i) => `${xAt(i)},${yAt(p.y)}`).join(' ');
          return (
            <polyline
              key={s.name}
              points={pts}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              className={s.colorClass}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex flex-wrap gap-3">
          {series.map((s: TrendSeries) => {
            const last = s.points[s.points.length - 1]?.y ?? 0;
            return (
              <span key={s.name} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={`inline-block h-2 w-2 rounded-full bg-current ${s.colorClass}`} />
                {s.name} <span className="font-semibold text-foreground tabular-nums">{fmtVal(last)}</span>
              </span>
            );
          })}
        </div>
        {dates.length >= 2 && (
          <span className="text-2xs text-muted-foreground tabular-nums">
            {dates[0]} → {dates[dates.length - 1]}
          </span>
        )}
      </div>
    </div>
  );
};
