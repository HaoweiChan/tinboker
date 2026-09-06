/** Shared bits for the home attention blocks. */

/** Percent change vs the prior window; null when there was nothing before (NEW). */
export function pctChange(now: number, prev: number): number | null {
  return prev === 0 ? null : Math.round(((now - prev) / prev) * 100);
}

/** What a click on a narrative / ticker row means for the feed below. */
export type Focus = { kind: 'tag'; key: string; label: string } | { kind: 'ticker'; key: string; label: string };
