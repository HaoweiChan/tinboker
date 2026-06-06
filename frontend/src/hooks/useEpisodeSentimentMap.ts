import { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';
import { normalizeSentiment, type Sentiment } from '@/lib/sentiment';

// episodeId → (TICKER_UPPER → Sentiment). Module-level cache shared across mounts.
// Sentiments are immutable once published, so we cache for the session (incl. empties
// to avoid refetching episodes with no per-ticker sentiment).
const cache = new Map<string, Map<string, Sentiment>>();
const SEP = '\u0001'; // SOH — episode ids contain spaces/CJK but never this control char

/**
 * Resolves per-(episode, ticker) sentiment for the given episodes via
 * POST /api/episodes/ticker-sentiments. Returns episodeId → (ticker → Sentiment).
 * Fetches async (chips populate after the cards render), mirroring useStockPriceMap.
 */
export function useEpisodeSentimentMap(episodeIds: string[]): Map<string, Map<string, Sentiment>> {
  const key = [...new Set(episodeIds.filter(Boolean))].sort().join(SEP);
  const [map, setMap] = useState<Map<string, Map<string, Sentiment>>>(new Map());

  useEffect(() => {
    const ids = key ? key.split(SEP) : [];
    if (!ids.length) return;

    const build = (): Map<string, Map<string, Sentiment>> => {
      const m = new Map<string, Map<string, Sentiment>>();
      for (const id of ids) {
        const entry = cache.get(id);
        if (entry) m.set(id, entry);
      }
      return m;
    };

    const missing = ids.filter((id) => !cache.has(id));
    if (!missing.length) {
      setMap(build());
      return;
    }

    let alive = true;
    apiClient
      .post('/api/episodes/ticker-sentiments', { episode_ids: missing })
      .then((res) => {
        if (!alive) return;
        const data = (res.data ?? {}) as Record<string, Record<string, string>>;
        for (const id of missing) {
          const perTicker = new Map<string, Sentiment>();
          for (const [ticker, raw] of Object.entries(data[id] ?? {})) {
            const norm = normalizeSentiment(raw);
            if (norm) perTicker.set(ticker.toUpperCase(), norm);
          }
          cache.set(id, perTicker); // cache even empty → don't refetch this session
        }
        setMap(build());
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return map;
}
