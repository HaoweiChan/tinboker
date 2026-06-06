import type { Episode as ApiEpisode } from '@/services/api/podcasts';
import type { EpisodeCardV2Props } from './EpisodeCardV2';
import type { Sentiment } from '@/lib/sentiment';

/** Strip light markdown so a long `summary_content` reads as a plain teaser. */
function plainTeaser(md: string | null | undefined, max = 200): string | undefined {
  if (!md) return undefined;
  const text = md
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/[*_`>#~]/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return undefined;
  return text.length > max ? text.slice(0, max).trimEnd() + '…' : text;
}

function timeAgo(release: string | number | null | undefined, created: number): string {
  const ms = typeof release === 'string' ? Date.parse(release) : (release ?? created);
  const t = Number.isFinite(ms) ? (ms as number) : created;
  const diff = Date.now() - t;
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return '剛剛';
  if (hours < 24) return `${hours} 小時前`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '昨天';
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} 個月前` : `${Math.floor(months / 12)} 年前`;
}

/** Map a backend Episode to props for the redesigned EpisodeCardV2.
 *  Pass `priceMap` (ticker → changePercent) to hydrate live price cells.
 *  Pass `podcastImageMap` (podcast_name → image_url) to show cover art.
 *  Pass `translationMap` (TICKER_UPPER → displayName) to show localized names.
 *  Pass `sentimentMap` (TICKER_UPPER → Sentiment) for this episode to show sentiment chips. */
export function apiEpisodeToCardV2(
  ep: ApiEpisode,
  priceMap?: Map<string, number>,
  podcastImageMap?: Map<string, string>,
  translationMap?: Map<string, string>,
  sentimentMap?: Map<string, Sentiment>,
): EpisodeCardV2Props {
  const released = ep.released_at_ms ?? ep.spotify_release_date ?? ep.created_time;
  const releaseTime = typeof released === 'string' ? Date.parse(released) : (released ?? ep.created_time);
  // "NEW" = published within the last day. The feed is already scoped to ~30 days
  // of frequently-published shows, so a 7-day window flagged every card; 24h keeps
  // the badge meaningful (≈ today's drops only).
  const isRecent = Number.isFinite(releaseTime) && Date.now() - (releaseTime as number) < 24 * 3_600_000;
  return {
    podcasterName: ep.podcast_name,
    podcasterInitial: (ep.podcast_name || 'P').charAt(0),
    podcasterImageUrl: podcastImageMap?.get(ep.podcast_name) ?? ep.spotify_images?.[0] ?? null,
    podcasterKind: 'mute',
    episodeNumber: ep.episode_number != null ? `EP ${ep.episode_number}` : undefined,
    timeAgo: timeAgo(ep.released_at_ms ?? ep.spotify_release_date, ep.created_time),
    title: ep.episode_title || (ep.episode_number != null ? `EP ${ep.episode_number}` : '本集摘要'),
    // Precomputed essence (agents-populated, no GCS hydration needed). Falls back to
    // the plain teaser when absent — see firestore-contract.md (key_insights).
    keyInsights: Array.isArray(ep.key_insights) && ep.key_insights.length > 0 ? ep.key_insights : undefined,
    summary: plainTeaser(ep.modified_summary_content || ep.summary_content),
    tickers: (() => {
      if (!Array.isArray(ep.related_tickers)) return undefined;
      // If the pipeline scored any ticker on this episode, drop the rest as
      // passing mentions (a bank cited for a report, a non-ticker like
      // SpaceX/"X"). When nothing is scored, show whatever was mentioned so
      // the row isn't empty.
      const scored = sentimentMap && sentimentMap.size > 0
        ? ep.related_tickers.filter((s) => sentimentMap.has(s.toUpperCase()))
        : ep.related_tickers;
      const shown = scored.length > 0 ? scored : ep.related_tickers;
      return shown.slice(0, 4).map((symbol) => ({
        symbol,
        name: translationMap?.get(symbol.toUpperCase()),
        sentiment: sentimentMap?.get(symbol.toUpperCase()),
        changePercent: priceMap?.get(symbol) ?? priceMap?.get(symbol.toUpperCase()),
      }));
    })(),
    tags: ep.tags ?? [],
    isNew: isRecent,
    href: `/episode/${encodeURIComponent(ep.id)}?podcast=${encodeURIComponent(ep.podcast_name)}`,
  };
}
