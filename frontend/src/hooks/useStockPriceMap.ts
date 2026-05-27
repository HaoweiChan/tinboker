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
    apiClient
      .get('/api/stocks/batch-prices', { params: { tickers: stale.join(',') } })
      .then((res) => {
        if (!alive) return;
        const ts = Date.now();
        for (const [ticker, changePercent] of Object.entries(res.data ?? {})) {
          if (Number.isFinite(changePercent)) {
            tickerCache.set(ticker, { value: changePercent as number, ts });
          }
        }
        setMap(buildMap());
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerKey]);

  return map;
}
