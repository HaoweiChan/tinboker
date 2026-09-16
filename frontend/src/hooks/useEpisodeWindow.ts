import { useEffect, useState } from 'react';
import { z } from 'zod';
import { apiClient } from '@/services/api/client';

const ScopeSchema = z.object({ episode_window_days: z.number().int().nonnegative() });

let cached: number | null = null;
let inflight: Promise<number | null> | null = null;

function load(): Promise<number | null> {
  if (cached !== null) return Promise.resolve(cached);
  inflight ??= apiClient
    .get('/api/podcast/scope')
    .then((res) => (cached = ScopeSchema.parse(res.data).episode_window_days))
    // Unknown is not "no window": a failed lookup must not bring back 「集已分析」.
    .catch(() => {
      inflight = null;
      return null;
    });
  return inflight;
}

/** Days of episodes the site serves (0 = no window), or null until known. Fetched once. */
export function useEpisodeWindowDays(): number | null {
  const [days, setDays] = useState<number | null>(cached);
  useEffect(() => {
    if (cached !== null) return;
    let alive = true;
    load().then((d) => {
      if (alive && d !== null) setDays(d);
    });
    return () => {
      alive = false;
    };
  }, []);
  return days;
}

/**
 * Words around an episode count. Counts are release-scoped, so with a 60-day window
 * 股癌 reads 17 while 698 are stored — a bare 「17 集已分析」 read as "only 17 were
 * ever processed". Say the window instead; say nothing about it until it is known.
 */
export function episodeCountWords(days: number | null): { before: string; after: string } {
  if (days === null) return { before: '', after: '集' };
  return days > 0 ? { before: `近 ${days} 天 `, after: '集' } : { before: '', after: '集已分析' };
}
