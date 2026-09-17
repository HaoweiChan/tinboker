import { useEffect, useMemo, useState } from 'react';
import { getEpisodeByIdOnly, type Episode as ApiEpisode } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

/**
 * Candidate episode doc ids for a stored bookmark, most likely first.
 *
 * A bookmark is stored as `{podcast_name}_{episode_id}` (see the toggle endpoint in
 * `backend/src/routers/user.py`), and an episode id is itself `{prefix}_{hash}` where
 * `prefix` is the sanitized show name (a hash of it for CJK names) and `hash` never
 * contains an underscore. So the doc id is the last two underscore-separated segments —
 * which is also the whole string for a legacy bookmark saved without the show prefix.
 *
 * The remaining candidates cover the rest: everything after the first underscore (a show
 * whose sanitized prefix itself contains one), then the bookmark id verbatim. Splitting
 * on the *first* underscore — what both saved-episode lists used to do — gets the podcast
 * name right but hands the API a truncated episode id for either of those shapes.
 */
export function episodeIdCandidates(bookmarkId: string): string[] {
  const parts = bookmarkId.split('_');
  const candidates = [parts.slice(-2).join('_'), parts.slice(1).join('_'), bookmarkId];
  return [...new Set(candidates.filter((c) => c.length > 0))];
}

/** Resolve one bookmark id, trying each candidate doc id until one comes back. */
async function resolveBookmark(bookmarkId: string): Promise<ApiEpisode | null> {
  for (const episodeId of episodeIdCandidates(bookmarkId)) {
    const episode = await fetchWithFallback<ApiEpisode | null>(
      () => getEpisodeByIdOnly(episodeId),
      null,
      `getEpisodeByIdOnly:${episodeId}`,
    ).catch(() => null);
    if (episode) return episode;
  }
  return null;
}

const releaseTime = (e: ApiEpisode) => e.released_at_ms ?? e.created_time ?? 0;

/**
 * Hydrates saved-episode bookmark ids into episodes, newest first.
 *
 * Looks each one up by id alone (`/api/episodes/{id}`) rather than through
 * `/api/podcast/{name}/episodes/{id}`: that endpoint 404s unless the show name stored in
 * the bookmark still matches the episode doc's `podcast_name` exactly, so a renamed show
 * silently emptied the saved-episodes list while the subscribed-shows list — which reads
 * the current names — kept working.
 *
 * `resolved` turns true once every id has settled, so callers can tell "still loading"
 * from "none of these could be loaded" instead of showing skeletons forever.
 */
export function useBookmarkedEpisodes(bookmarkIds: string[]): {
  episodes: ApiEpisode[];
  resolved: boolean;
} {
  // Serialized so the effect re-runs on content change, not on a new array identity.
  const key = useMemo(() => JSON.stringify(bookmarkIds), [bookmarkIds]);
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [resolved, setResolved] = useState(true);

  useEffect(() => {
    const ids: string[] = JSON.parse(key);
    if (ids.length === 0) {
      setEpisodes([]);
      setResolved(true);
      return;
    }
    let alive = true;
    setResolved(false);
    Promise.all(ids.map(resolveBookmark)).then((arr) => {
      if (!alive) return;
      setEpisodes(
        arr.filter((e): e is ApiEpisode => e != null).sort((a, b) => releaseTime(b) - releaseTime(a)),
      );
      setResolved(true);
    });
    return () => {
      alive = false;
    };
  }, [key]);

  return { episodes, resolved };
}
