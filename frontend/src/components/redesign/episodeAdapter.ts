import type { Episode as ApiEpisode } from '@/services/api/podcasts';
import type { EpisodeCardV2Props } from './EpisodeCardV2';

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
 *  Pass `priceMap` (ticker → changePercent) to hydrate live price cells. */
export function apiEpisodeToCardV2(ep: ApiEpisode, priceMap?: Map<string, number>): EpisodeCardV2Props {
  const released = ep.spotify_release_date ?? ep.created_time;
  const releaseTime = typeof released === 'string' ? Date.parse(released) : (released ?? ep.created_time);
  const isRecent = Number.isFinite(releaseTime) && Date.now() - (releaseTime as number) < 7 * 24 * 3_600_000;
  return {
    podcasterName: ep.podcast_name,
    podcasterInitial: (ep.podcast_name || 'P').charAt(0),
    podcasterImageUrl: ep.spotify_images?.[0] ?? null,
    podcasterKind: 'mute',
    episodeNumber: ep.episode_number != null ? `EP ${ep.episode_number}` : undefined,
    timeAgo: timeAgo(ep.spotify_release_date, ep.created_time),
    title: ep.episode_title || (ep.episode_number != null ? `EP ${ep.episode_number}` : '本集摘要'),
    summary: plainTeaser(ep.modified_summary_content || ep.summary_content),
    tickers: Array.isArray(ep.related_tickers)
      ? ep.related_tickers.slice(0, 4).map((symbol) => ({
          symbol,
          changePercent: priceMap?.get(symbol) ?? priceMap?.get(symbol.toUpperCase()),
        }))
      : undefined,
    tags: ep.tags ?? [],
    isNew: isRecent,
    href: `/episode/${encodeURIComponent(ep.id)}?podcast=${encodeURIComponent(ep.podcast_name)}`,
  };
}
