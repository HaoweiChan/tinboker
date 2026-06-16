import { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';
import type { PickWindowReturns } from '@/services/types';

/** A pick to score: a ticker plus the mention (episode-release) timestamp. */
export interface PickRef {
  ticker: string;
  reference_ms: number;
}

const cache = new Map<string, { value: PickWindowReturns; ts: number }>();
const TTL = 5 * 60_000;

/** Composite key matching the backend's `"{TICKER}:{reference_ms}"` response keys. */
function keyOf(p: PickRef): string {
  return `${p.ticker.toUpperCase()}:${p.reference_ms}`;
}

/**
 * Forward 7/30/90D (+ since) returns per *pick*, from /api/stocks/batch-prices-windows.
 *
 * Unlike `useStockPriceSinceMap` (one entry per ticker), each (ticker, mention-date)
 * pair is scored independently, so the same ticker mentioned by different episodes
 * keeps its own scorecard. Returns a `Map` keyed by `"{TICKER}:{reference_ms}"`.
 */
export function useTickerWindowReturns(picks: PickRef[]): Map<string, PickWindowReturns> {
  const [map, setMap] = useState<Map<string, PickWindowReturns>>(new Map());

  const items = dedupe(picks);
  const requestKey = items.map(keyOf).sort().join(',');

  useEffect(() => {
    if (!requestKey) return;

    const now = Date.now();
    const stale = items.filter((p) => {
      const entry = cache.get(keyOf(p));
      return !entry || now - entry.ts > TTL;
    });
    const buildMap = (): Map<string, PickWindowReturns> => {
      const m = new Map<string, PickWindowReturns>();
      for (const p of items) {
        const entry = cache.get(keyOf(p));
        if (entry) m.set(keyOf(p), entry.value);
      }
      return m;
    };
    if (!stale.length) {
      setMap(buildMap());
      return;
    }

    let alive = true;
    apiClient
      .post('/api/stocks/batch-prices-windows', { items: stale })
      .then((res) => {
        if (!alive) return;
        const ts = Date.now();
        for (const [k, v] of Object.entries(res.data ?? {})) {
          if (v && typeof v === 'object') {
            cache.set(k.toUpperCase(), { value: v as PickWindowReturns, ts });
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

/** Build the composite lookup key for a (ticker, reference_ms) pair. */
export function windowReturnsKey(ticker: string, referenceMs: number): string {
  return `${ticker.toUpperCase()}:${referenceMs}`;
}

function dedupe(picks: PickRef[]): PickRef[] {
  const seen = new Set<string>();
  const out: PickRef[] = [];
  for (const p of picks) {
    if (!p.ticker || !Number.isFinite(p.reference_ms)) continue;
    const k = keyOf(p);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ ticker: p.ticker.toUpperCase(), reference_ms: p.reference_ms });
  }
  return out;
}
