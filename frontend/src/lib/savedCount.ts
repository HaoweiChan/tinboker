/**
 * How many saved episodes to show in a header count.
 *
 * The resolved list is empty while the episodes are still being fetched, so the raw
 * id count stands in until then. The fallback keys on `resolvedTotal` — whether the
 * fetch produced anything — and NEVER on the visible count: `visible || ids` reads
 * the stale id count the moment a swipe empties the list, which left 會員專區 showing
 * 1集數 with no cards under it.
 *
 * @param resolvedTotal episodes that came back (unaffected by swipes — the list is
 *                      filtered for display, not edited)
 * @param visible       what the tab is actually rendering
 * @param idCount       saved ids, known before the episodes resolve
 */
export function savedCount(resolvedTotal: number, visible: number, idCount: number): number {
  return resolvedTotal ? visible : idCount;
}
