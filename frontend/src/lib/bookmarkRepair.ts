// Saved-episode bookmarks are stored as `{podcast_name}_{episode_id}` strings on the user
// row (see the toggle endpoint in `backend/src/routers/user.py`). Nothing keeps them in
// step with the episode they point at, so a renamed show — or a bookmark written by an
// older client — leaves an entry that no longer addresses anything. This module decides
// what to do about each one; performing the writes is `useBookmarkedEpisodes`'s job.

/** The fields of an episode this module needs. */
export interface BookmarkTarget {
  id: string;
  podcast_name: string;
}

/** What a stored bookmark id turned out to point at. */
export type BookmarkResolution<T extends BookmarkTarget = BookmarkTarget> =
  | { kind: 'ok'; episode: T }
  /** Every candidate came back 404 — the episode is gone, or the id was never valid. */
  | { kind: 'missing' }
  /** A network or server fault. Says nothing about the bookmark, so never act on it. */
  | { kind: 'failed' };

/** The id this episode would be bookmarked under today. */
export const canonicalBookmarkId = (ep: BookmarkTarget) => `${ep.podcast_name}_${ep.id}`;

/**
 * Candidate episode doc ids for a stored bookmark, most likely first.
 *
 * An episode id is itself `{prefix}_{hash}`, where `prefix` is the sanitized show name (a
 * hash of it for CJK names) and `hash` never contains an underscore. So the doc id inside
 * a bookmark is the last two underscore-separated segments — which is also the whole
 * string for a legacy bookmark saved without the show prefix.
 *
 * The remaining candidates cover the rest: everything after the first underscore (a show
 * whose sanitized prefix itself contains one), then the bookmark id verbatim. Splitting on
 * the *first* underscore — what both saved-episode lists used to do — gets the podcast
 * name right but hands the API a truncated episode id for either of those shapes.
 */
export function episodeIdCandidates(bookmarkId: string): string[] {
  const parts = bookmarkId.split('_');
  const candidates = [parts.slice(-2).join('_'), parts.slice(1).join('_'), bookmarkId];
  return [...new Set(candidates.filter((c) => c.length > 0))];
}

/**
 * Split a stored bookmark id the way the toggle endpoint will re-join it.
 *
 * That endpoint takes a show name and an episode id and acts on their `{name}_{id}`
 * concatenation, so any split addresses the exact stored entry — which is how a bookmark
 * in an outdated shape gets removed at all. An id with no interior underscore can't be
 * expressed that way; the endpoint always joins the halves with one.
 */
export function bookmarkIdToToggleArgs(bookmarkId: string): { podcastName: string; episodeId: string } | null {
  const cut = bookmarkId.indexOf('_');
  if (cut <= 0 || cut === bookmarkId.length - 1) return null;
  return { podcastName: bookmarkId.slice(0, cut), episodeId: bookmarkId.slice(cut + 1) };
}

export interface RepairPlan {
  /** Stored under a stale id, but we know which episode it is: rewrite it. */
  migrate: { from: string; to: string }[];
  /** The episode is gone. Remove the bookmark — it can never render. */
  gone: string[];
  /** The same episode is already saved under its current id. Remove the leftover. */
  duplicate: string[];
}

export const isEmptyPlan = (plan: RepairPlan) =>
  plan.migrate.length === 0 && plan.gone.length === 0 && plan.duplicate.length === 0;

/**
 * Decide what each stored bookmark needs. Only ids we resolved definitively are touched:
 * a fetch that failed leaves the bookmark exactly as it is, so a flaky network can never
 * delete someone's saved episodes.
 */
export function planBookmarkRepair(
  bookmarkIds: string[],
  resolutions: Map<string, BookmarkResolution<BookmarkTarget>>,
  skip: ReadonlySet<string> = new Set(),
): RepairPlan {
  const plan: RepairPlan = { migrate: [], gone: [], duplicate: [] };
  const stored = new Set(bookmarkIds);
  // An id this pass is already rewriting to X makes X taken for every later bookmark.
  const claimed = new Set<string>();
  for (const id of bookmarkIds) {
    if (skip.has(id)) continue;
    const resolution = resolutions.get(id);
    if (!resolution || resolution.kind === 'failed') continue;
    if (resolution.kind === 'missing') {
      plan.gone.push(id);
      continue;
    }
    const canonical = canonicalBookmarkId(resolution.episode);
    if (canonical === id) continue;
    if (stored.has(canonical) || claimed.has(canonical)) {
      plan.duplicate.push(id);
    } else {
      plan.migrate.push({ from: id, to: canonical });
      claimed.add(canonical);
    }
  }
  return plan;
}
