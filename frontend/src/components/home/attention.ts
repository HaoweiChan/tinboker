/** Percent change vs the prior window; null when there was nothing before (NEW). */
export function pctChange(now: number, prev: number): number | null {
  return prev === 0 ? null : Math.round(((now - prev) / prev) * 100);
}
