import { useEffect, useMemo, useState } from 'react';
import { AxiosError } from 'axios';
import { toast } from 'sonner';
import { getEpisodeByIdOnly, type Episode as ApiEpisode } from '@/services/api/podcasts';
import { userApi } from '@/services/api/user';
import { useAppStore } from '@/store/useAppStore';
import {
  bookmarkIdToToggleArgs,
  episodeIdCandidates,
  isEmptyPlan,
  planBookmarkRepair,
  type BookmarkResolution,
} from '@/lib/bookmarkRepair';

// Episode lookups are stable for a session; cache them so a repair-triggered re-render
// doesn't refetch the whole list. `null` records a confirmed 404.
const episodeCache = new Map<string, ApiEpisode | null>();

async function lookupEpisode(episodeId: string): Promise<ApiEpisode | 'missing' | 'failed'> {
  const cached = episodeCache.get(episodeId);
  if (cached !== undefined) return cached ?? 'missing';
  try {
    const episode = await getEpisodeByIdOnly(episodeId);
    episodeCache.set(episodeId, episode);
    return episode;
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 404) {
      episodeCache.set(episodeId, null);
      return 'missing';
    }
    return 'failed';
  }
}

/** Resolve one bookmark id, trying each candidate doc id until one comes back. */
async function resolveBookmark(bookmarkId: string): Promise<BookmarkResolution<ApiEpisode>> {
  let sawFailure = false;
  for (const episodeId of episodeIdCandidates(bookmarkId)) {
    const result = await lookupEpisode(episodeId);
    if (result === 'failed') sawFailure = true;
    else if (result !== 'missing') return { kind: 'ok', episode: result };
  }
  // A 404 on every candidate means gone; a fault anywhere means we simply don't know.
  return sawFailure ? { kind: 'failed' } : { kind: 'missing' };
}

/** Add or remove one stored bookmark id through the toggle endpoint. */
async function toggleBookmarkId(bookmarkId: string): Promise<void> {
  const args = bookmarkIdToToggleArgs(bookmarkId);
  if (!args) throw new Error(`Bookmark id has no usable split: ${bookmarkId}`);
  await userApi.toggleEpisodeBookmark(args.podcastName, args.episodeId);
}

// Repairs are per-session and idempotent; this keeps a re-render (or the other
// saved-episodes page) from running the same one twice.
const repaired = new Set<string>();

/**
 * Bring stored bookmarks in line with the ids episodes carry today: rewrite the ones we
 * can still identify, drop the ones we can't. Returns the resulting bookmark list, or
 * null when nothing needed doing.
 *
 * The new id is added before the stale one is removed, so an interrupted repair leaves a
 * duplicate (deduplicated on render) rather than a lost bookmark.
 */
async function repairBookmarks(
  bookmarkIds: string[],
  resolutions: Map<string, BookmarkResolution<ApiEpisode>>,
): Promise<string[] | null> {
  const plan = planBookmarkRepair(bookmarkIds, resolutions, repaired);
  if (isEmptyPlan(plan)) return null;

  const next = new Set(bookmarkIds);
  for (const { from, to } of plan.migrate) {
    try {
      await toggleBookmarkId(to);
      next.add(to);
      await toggleBookmarkId(from);
      next.delete(from);
      repaired.add(from);
    } catch {
      // Leave it stored and try again on the next visit.
    }
  }
  for (const id of [...plan.gone, ...plan.duplicate]) {
    try {
      await toggleBookmarkId(id);
      next.delete(id);
      repaired.add(id);
    } catch {
      /* same — retried next visit */
    }
  }
  // Only the genuinely-gone ones are worth telling the user about; a de-duplicated
  // leftover and a rewritten id both leave their episode right where it was.
  const removed = plan.gone.filter((id) => !next.has(id)).length;
  if (removed > 0) toast.info(`已移除 ${removed} 個已下架的收藏集數`);
  return [...next];
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
 * With `repair`, a bookmark whose id no longer matches the episode is rewritten to the
 * current one, and a bookmark whose episode is confirmed gone (404, never a fetch
 * failure) is removed, so the list stops carrying entries that can never render.
 * `onChange` reports the resulting ids.
 *
 * `resolved` turns true once every id has settled, so callers can tell "still loading"
 * from "none of these could be loaded" instead of showing skeletons forever.
 */
export function useBookmarkedEpisodes(
  bookmarkIds: string[],
  options?: { repair?: boolean; onChange?: (ids: string[]) => void },
): { episodes: ApiEpisode[]; resolved: boolean } {
  const { repair = false, onChange } = options ?? {};
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
    (async () => {
      const results = await Promise.all(ids.map(async (id) => [id, await resolveBookmark(id)] as const));
      if (!alive) return;
      // Keyed by episode, so a bookmark stored twice (mid-migration) lists once.
      const byEpisodeId = new Map<string, ApiEpisode>();
      for (const [, resolution] of results) {
        if (resolution.kind === 'ok') byEpisodeId.set(resolution.episode.id, resolution.episode);
      }
      setEpisodes([...byEpisodeId.values()].sort((a, b) => releaseTime(b) - releaseTime(a)));
      setResolved(true);

      if (!repair || !useAppStore.getState().token) return;
      const next = await repairBookmarks(ids, new Map(results));
      if (!alive || !next) return;
      useAppStore.setState({ episodeBookmarks: next });
      onChange?.(next);
    })();
    return () => {
      alive = false;
    };
    // onChange is a render-scoped callback; re-running on its identity would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, repair]);

  return { episodes, resolved };
}
