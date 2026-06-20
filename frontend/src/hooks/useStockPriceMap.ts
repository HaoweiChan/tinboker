import { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';

const tickerCache = new Map<string, { value: number; ts: number }>();
const TTL = 60_000;

// Module-level cache — all page mounts share one fetch per ticker within the TTL.
export function useStockPriceMap(tickers: string[]): Map<string, number> {
  const tickerKey = [...new Set(tickers.map((t) => t.toUpperCase()))].sort().join(',');
  const [map, setMap] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    const unique = tickerKey ? tickerKey.split(',') : [];
    if (!unique.length) return;

    const now = Date.now();
    const stale = unique.filter((t) => {
      const entry = tickerCache.get(t);
      return !entry || now - entry.ts > TTL;
    });

    const buildMap = (): Map<string, number> => {
      const m = new Map<string, number>();
      for (const t of unique) {
        const entry = tickerCache.get(t);
        if (entry) m.set(t, entry.value);
      }
      return m;
    };

    if (!stale.length) {
      setMap(buildMap());
      return;
    }

    let alive = true;
    // /api/stocks/batch-prices caps at 100 tickers per request — chunk so large
    // lists (e.g. a sector page with 170+ related tickers) don't silently drop the
    // tail, which showed priceable tickers (NVDA, MU, …) as an empty "—".
    const CHUNK = 90;
    const chunks: string[][] = [];
    for (let i = 0; i < stale.length; i += CHUNK) chunks.push(stale.slice(i, i + CHUNK));
    Promise.all(
      chunks.map((c) =>
        apiClient
          .get('/api/stocks/batch-prices', { params: { tickers: c.join(',') } })
          .then((res) => res.data as Record<string, unknown>)
          .catch(() => ({} as Record<string, unknown>)),
      ),
    ).then((results) => {
      if (!alive) return;
      const ts = Date.now();
      for (const data of results) {
        for (const [ticker, changePercent] of Object.entries(data ?? {})) {
          if (Number.isFinite(changePercent)) {
            tickerCache.set(ticker, { value: changePercent as number, ts });
          }
        }
      }
      setMap(buildMap());
    });

    return () => {
      alive = false;
    };
  }, [tickerKey]);

  return map;
}
