/** Where a session's podcast-attention share sits inside the ticker's OWN trailing year,
 *  as 0–100. 92 means "more discussed than on 92% of the sessions in the past year";
 *  8 means it has almost gone quiet.
 *
 *  Why a percentile and not the share itself: the share's scale moves with how much we
 *  ingest. When the roster grew in 2025-08 the median mentioned ticker's share fell to
 *  15–27% of its previous level with nothing about the stocks changing, so a share of
 *  "1%" means something different every quarter. Ranking each ticker against its own
 *  year cancels that, and it also cancels the difference between a name that is always
 *  discussed (TSMC ~10% of everything) and one that is rarely discussed. Across 15
 *  normalisations tested on 2020–2026 data this was the only family that read the same
 *  before and after the roster change (docs: 2026-09-10 sentiment quantamental report).
 *
 *  `shares` must be in time order (unix seconds). Sessions with fewer than `minSamples`
 *  earlier sessions inside the window get no value, so a freshly-ingested ticker shows
 *  nothing rather than a percentile computed against three weeks.
 */
export function attentionPercentile(
  shares: { time: number; share: number }[],
  windowDays = 364,
  minSamples = 60,
): Map<number, number> {
  const out = new Map<number, number>();
  const windowSec = windowDays * 86400;
  let start = 0;
  // ponytail: O(n × window) scan, ~500 sessions × ~250 — a sorted window if it ever matters.
  for (let i = 0; i < shares.length; i++) {
    const { time, share } = shares[i];
    while (shares[start].time < time - windowSec) start++;
    const n = i - start + 1;
    if (n < minSamples) continue;
    let le = 0;
    for (let j = start; j <= i; j++) if (shares[j].share <= share) le++;
    out.set(time, Math.round((le / n) * 100));
  }
  return out;
}
