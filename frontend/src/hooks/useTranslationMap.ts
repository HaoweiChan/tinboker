import { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';

export interface TranslationEntry {
  displayName: string;       // zh-TW name when available, English otherwise
  hasZhName: boolean;        // true only for a real CJK name
  nameEn?: string | null;    // English full name (e.g. "HP Inc.")
  nameZhTw?: string | null;  // raw zh-TW name (may be a Latin value parked here)
  brandColor?: string | null;
}

// Module-level cache — shared across all mounts, long TTL (names rarely change).
const translationCache = new Map<string, { value: TranslationEntry; ts: number }>();
const TTL = 24 * 60 * 60_000; // 24h

/**
 * Resolves a list of ticker symbols to their localized display names.
 * Calls GET /api/stocks/translations/batch (read-only, no stub creation).
 * Returns a map of TICKER_UPPER → TranslationEntry.
 */
export function useTranslationMap(tickers: string[]): Map<string, TranslationEntry> {
  const tickerKey = [...new Set(tickers.map((t) => t.toUpperCase()))].sort().join(',');
  const [map, setMap] = useState<Map<string, TranslationEntry>>(new Map());

  useEffect(() => {
    const unique = tickerKey ? tickerKey.split(',') : [];
    if (!unique.length) return;

    const now = Date.now();
    const stale = unique.filter((t) => {
      const entry = translationCache.get(t);
      return !entry || now - entry.ts > TTL;
    });

    const buildMap = (): Map<string, TranslationEntry> => {
      const m = new Map<string, TranslationEntry>();
      for (const t of unique) {
        const entry = translationCache.get(t);
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
      .get('/api/stocks/translations/batch', { params: { tickers: stale.join(',') } })
      .then((res) => {
        if (!alive) return;
        const ts = Date.now();
        for (const item of (res.data?.items ?? []) as Array<Record<string, unknown>>) {
          const key = String(item.ticker).toUpperCase();
          translationCache.set(key, {
            value: {
              displayName: String(item.display_name),
              hasZhName: Boolean(item.has_zh_name),
              nameEn: (item.name_en as string | null) ?? null,
              nameZhTw: (item.name_zh_tw as string | null) ?? null,
              brandColor: item.brand_color as string | null,
            },
            ts,
          });
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
