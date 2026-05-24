import { useEffect, useState } from 'react';
import { getBatchStockSummary, type StockSummary } from '@/services/api/stocks';

// Fetches display metadata (name + market + icon URL) for a list of tickers.
// Returns a stable map keyed by ticker so consumers can do `summaries[ticker]`.
export function useStockSummaries(tickers: string[]): Record<string, StockSummary> {
  const [summaries, setSummaries] = useState<Record<string, StockSummary>>({});
  const key = tickers.slice().sort().join(',');

  useEffect(() => {
    if (!key) {
      setSummaries({});
      return;
    }
    let alive = true;
    const list = key.split(',').filter(Boolean);
    getBatchStockSummary(list)
      .then((rows) => {
        if (!alive) return;
        const next: Record<string, StockSummary> = {};
        for (const row of rows) next[row.ticker] = row;
        setSummaries(next);
      })
      .catch((err) => {
        if (import.meta.env.DEV) console.warn('[useStockSummaries] fetch failed', err);
      });
    return () => {
      alive = false;
    };
  }, [key]);

  return summaries;
}
