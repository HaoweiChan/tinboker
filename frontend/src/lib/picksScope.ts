import type { TickerInsight } from '@/services/types';
import { canonicalTicker } from './pickGroups';

/**
 * "我的" scope for /picks (走勢): a pick belongs to the member's personal feed if
 * it's from a podcast they subscribe to, OR its canonical ticker is on their
 * watchlist. This mirrors the existing 訂閱節目 / 自選個股 lists on the member
 * hub — there is no separate "tracked picks" model.
 */

/** Trim + drop blanks; podcaster names are matched exactly (whitespace-insensitive). */
export function normalizeNames(names: string[]): Set<string> {
  return new Set(names.map((n) => n.trim()).filter(Boolean));
}

/** Canonicalize watchlist tickers the same way pick tickers are canonicalized
 *  (strips exchange suffixes, folds known ADRs), so `2330` matches `2330.TW`. */
export function normalizeTickers(tickers: string[]): Set<string> {
  return new Set(tickers.map(canonicalTicker).filter(Boolean));
}

export function isMyPick(
  pick: TickerInsight,
  mySubscribedNames: Set<string>,
  myTickers: Set<string>,
): boolean {
  const podcaster = (pick.podcaster || '').trim();
  if (podcaster && mySubscribedNames.has(podcaster)) return true;
  return myTickers.has(canonicalTicker(pick.ticker));
}

/**
 * Pure "我的" filter: subscribed-show picks ∪ watchlist-ticker picks, de-duplicated
 * by episode + canonical ticker. Callers pass in whatever sources they've already
 * loaded (e.g. subscribed-channel history unioned with the all-shows feed) — this
 * does no fetching of its own.
 */
export function filterMyPicks(
  picks: TickerInsight[],
  mySubscribedNames: string[],
  myWatchlistTickers: string[],
): TickerInsight[] {
  const names = normalizeNames(mySubscribedNames);
  const tickers = normalizeTickers(myWatchlistTickers);
  const seen = new Set<string>();
  const out: TickerInsight[] = [];
  for (const p of picks) {
    if (!isMyPick(p, names, tickers)) continue;
    const key = `${p.episode_id}|${canonicalTicker(p.ticker)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}
