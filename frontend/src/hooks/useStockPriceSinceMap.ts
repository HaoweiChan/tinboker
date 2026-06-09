import { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';
import type { Episode } from '@/services/api/podcasts';

const ONE_DAY_MS = 86_400_000;
const cache = new Map<string, { value: number; ts: number }>();
const TTL = 5 * 60_000;

function episodeReferenceMs(ep: Episode): number {
  return ep.released_at_ms ?? ep.created_time;
}

/** True when the episode is too recent (< 24 h) for a meaningful "since" delta. */
export function isRecentEpisode(ep: Episode): boolean {
  return Date.now() - episodeReferenceMs(ep) < ONE_DAY_MS;
}

/**
 * Like `useStockPriceMap` but returns the % change **from each ticker's episode
 * release date to today** instead of the intraday daily change.
 *
 * Returns a flat `Map<ticker, changePercent>`.  For episodes less than 1 day old
 * the caller should fall back to `useStockPriceMap` (daily).
 */
export function useStockPriceSinceMap(episodes: Episode[]): Map<string, number> {
  const [map, setMap] = useState<Map<string, number>>(new Map());

  // Build a stable key so we only refetch when the ticker set / dates change.
  const requestKey = buildRequestKey(episodes);

  useEffect(() => {
    if (!requestKey) return;
    const items = buildItems(episodes);
    if (!items.length) return;

    // Check cache — if all tickers are fresh, skip the fetch.
    const now = Date.now();
    const stale = items.filter((i) => {
      const entry = cache.get(i.ticker.toUpperCase());
      return !entry || now - entry.ts > TTL;
    });
    const buildMap = (): Map<string, number> => {
      const m = new Map<string, number>();
      for (const i of items) {
        const entry = cache.get(i.ticker.toUpperCase());
        if (entry) m.set(i.ticker.toUpperCase(), entry.value);
      }
      return m;
    };
    if (!stale.length) {
      setMap(buildMap());
      return;
    }

    let alive = true;
    apiClient
      .post('/api/stocks/batch-prices-since', { items: stale })
      .then((res) => {
        if (!alive) return;
        const ts = Date.now();
        for (const [ticker, pct] of Object.entries(res.data ?? {})) {
          if (Number.isFinite(pct)) {
            cache.set(ticker.toUpperCase(), { value: pct as number, ts });
          }
        }
        setMap(buildMap());
      })
      .catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  return map;
}

/** Deduplicate: one entry per unique ticker, using the earliest episode date. */
function buildItems(episodes: Episode[]): { ticker: string; reference_ms: number }[] {
  const earliest = new Map<string, number>();
  for (const ep of episodes) {
    if (isRecentEpisode(ep)) continue;
    const ref = episodeReferenceMs(ep);
    for (const t of ep.related_tickers ?? []) {
      const key = t.toUpperCase();
      const prev = earliest.get(key);
      if (!prev || ref < prev) earliest.set(key, ref);
    }
  }
  return Array.from(earliest, ([ticker, reference_ms]) => ({ ticker, reference_ms }));
}

function buildRequestKey(episodes: Episode[]): string {
  const items = buildItems(episodes);
  if (!items.length) return '';
  return items
    .map((i) => `${i.ticker}:${i.reference_ms}`)
    .sort()
    .join(',');
}
