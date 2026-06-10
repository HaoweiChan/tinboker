import { apiClient } from './client';
import type { TickerTrending, TickerInsight } from '../types';

/** Streaming URL for an episode's MP3 (backend redirects to a signed GCS URL). */
export function getEpisodeAudioUrl(podcastName: string, episodeId: string): string {
  return `${apiClient.defaults.baseURL || ''}/api/podcast/${encodeURIComponent(podcastName)}/episodes/${encodeURIComponent(episodeId)}/audio`;
}


export interface Podcast {
  id: string;
  name: string;
  episode_count: number;
  created_at?: number | null;
  updated_at?: number | null;
  image_url?: string | null;
}

export interface Episode {
  id: string;
  podcast_name: string;
  episode_title?: string | null;
  episode_number?: number | null;
  transcript: string;
  summary_content: string;
  summary_image?: string | null;
  summary_image_url?: string | null;
  summary_image_public_url?: string | null;
  related_tickers: string[];
  tags?: string[];
  created_time: number;
  /** True publish time (Unix ms), agents-written from the feed. Prefer over
   *  created_time (ingestion time) and spotify_release_date for display. */
  released_at_ms?: number | null;
  number_click?: number;
  num_likes?: number;
  raw_mp3?: string | null;
  mp3_url?: string | null;
  mp3_public_url?: string | null;
  spotify_url?: string | null;
  spotify_id?: string | null;
  spotify_embed_url?: string | null;
  spotify_release_date?: string | number | null;
  spotify_images?: string[] | null;
  spotify_description?: string | null;
  events_markdown_content?: string | null;
  sentences_markdown_content?: string | null;
  events_markdown_url?: string | null;
  sentences_markdown_url?: string | null;
  events_markdown_public_url?: string | null;
  sentences_markdown_public_url?: string | null;
  marp_markdown_content?: string | null;
  ticker_marp_markdown_content?: string | null;
  ticker_insights_content?: string | null;
  ticker_insights_url?: string | null;
  ticker_insights_public_url?: string | null;
  key_insights?: string[] | null;
  modified_summary_url?: string | null;
  modified_summary_content?: string | null;
  modified_by?: string | null;
  modified_at?: number | null;
}

export interface Tag {
  id: string;
  name: string;
  episode_count: number;
}

export interface TagsResponse {
  tags: Tag[];
}

export interface EpisodesByTagResponse {
  tag: string;
  episodes: Episode[];
  total: number;
}

export interface MarketIndex {
  id: string;
  name: string;
  ticker: string;
  value: string;
  change: string;
  isPositive: boolean;
}

export interface TopMover {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  icon_url?: string;
  sparkline?: number[];
}

export async function getSortedPodcasts(options?: {
  sortBy?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}): Promise<Podcast[]> {
  const params: Record<string, any> = {};
  if (options?.sortBy) params.sort_by = options.sortBy;
  if (options?.order) params.order = options.order;
  if (options?.limit) params.limit = options.limit;
  if (options?.offset) params.offset = options.offset;
  const response = await apiClient.get('/api/podcast', { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function getPodcastByName(podcastName: string): Promise<Podcast> {
  const response = await apiClient.get(`/api/podcast/${encodeURIComponent(podcastName)}`);
  return response.data;
}

export async function getPodcastEpisodes(
  podcastName: string,
  options?: {
    sortBy?: string;
    order?: 'asc' | 'desc';
    limit?: number;
    offset?: number;
    includeContent?: boolean;
  }
): Promise<Episode[]> {
  const params: Record<string, any> = {};
  if (options?.sortBy) params.sort_by = options.sortBy;
  if (options?.order) params.order = options.order;
  if (options?.limit) params.limit = options.limit;
  if (options?.offset) params.offset = options.offset;
  if (options?.includeContent !== undefined) params.include_content = options.includeContent;
  const response = await apiClient.get(
    `/api/podcast/${encodeURIComponent(podcastName)}/episodes`,
    { params }
  );
  return Array.isArray(response.data) ? response.data : [];
}

export async function getEpisodeById(podcastName: string, episodeId: string): Promise<Episode> {
  const response = await apiClient.get(
    `/api/podcast/${encodeURIComponent(podcastName)}/episodes/${episodeId}`,
    { params: { include_heavy_content: false } }
  );
  return response.data;
}

// Fetch an episode by id alone, without the podcast name. Used for deep links /
// refreshes of /episode/{id} where the show name isn't available client-side.
export async function getEpisodeByIdOnly(episodeId: string): Promise<Episode> {
  const response = await apiClient.get(
    `/api/episodes/${encodeURIComponent(episodeId)}`,
    { params: { include_heavy_content: false } }
  );
  return response.data;
}

export async function regenerateEpisodeSummary(
  podcastName: string,
  episodeId: string
): Promise<{ status: string; message: string }> {
  const response = await apiClient.post(
    `/api/podcast/${encodeURIComponent(podcastName)}/episodes/${episodeId}/regenerate`
  );
  return response.data;
}

export async function getEpisodesByTicker(
  ticker: string,
  options?: { limit?: number; offset?: number; sortBy?: string; order?: 'asc' | 'desc'; includeContent?: boolean }
): Promise<Episode[]> {
  const params: Record<string, any> = {};
  if (options?.limit) params.limit = options.limit;
  if (options?.offset) params.offset = options.offset;
  if (options?.sortBy) params.sort_by = options.sortBy;
  if (options?.order) params.order = options.order;
  if (options?.includeContent !== undefined) params.include_content = options.includeContent;
  const normalizedTicker = ticker.toLowerCase();
  const response = await apiClient.get(`/api/episodes/by-ticker/${normalizedTicker}`, { params });
  if (Array.isArray(response.data)) return response.data;
  if (response.data && typeof response.data === 'object' && Array.isArray(response.data.episodes)) {
    return response.data.episodes;
  }
  return [];
}

// Phase B replacement, reading Firestore ticker_insights/*. Contract: spec § 4.
export async function getInsightsByTicker(
  ticker: string,
  params?: { start_date?: string; end_date?: string }
): Promise<TickerInsight[]> {
  const q: Record<string, string> = {};
  if (params?.start_date) q.start_date = params.start_date;
  if (params?.end_date) q.end_date = params.end_date;
  const response = await apiClient.get(`/api/ticker-insights/by-ticker/${encodeURIComponent(ticker)}`, {
    params: Object.keys(q).length ? q : undefined,
  });
  return Array.isArray(response.data) ? response.data : [];
}

export async function getInsightsByPodcaster(
  podcasterName: string,
  params?: { start_date?: string; end_date?: string }
): Promise<TickerInsight[]> {
  const q: Record<string, string> = {};
  if (params?.start_date) q.start_date = params.start_date;
  if (params?.end_date) q.end_date = params.end_date;
  const response = await apiClient.get(
    `/api/ticker-insights/by-podcaster/${encodeURIComponent(podcasterName)}`,
    { params: Object.keys(q).length ? q : undefined }
  );
  return Array.isArray(response.data) ? response.data : [];
}

// Phase A replacement reading Firestore trending_tickers/*.
// Contract: docs/firestore-contract.md § 5.
export async function getTrendingTickers(
  params?: { days?: number; limit?: number }
): Promise<TickerTrending[]> {
  const q: Record<string, number> = {};
  if (params?.days != null) q.days = params.days;
  if (params?.limit != null) q.limit = params.limit;
  const response = await apiClient.get('/api/ticker-insights/trending', {
    params: Object.keys(q).length ? q : undefined,
  });
  return Array.isArray(response.data) ? response.data : [];
}

export interface SentimentSummary {
  bull: number;
  neutral: number;
  bear: number;
}

export interface RisingTicker {
  ticker: string;
  name: string | null;
  delta: number;
}

export interface NewTicker {
  ticker: string;
  name: string | null;
}

export interface RecentBuzz {
  tickers: TickerTrending[];
  distinct_count: number;
  episode_count: number;
  sentiment_summary?: SentimentSummary;
  prev_sentiment_summary?: SentimentSummary;
  rising_ticker?: RisingTicker;
  new_tickers?: NewTicker[];
}

/** Genuine "what people are discussing lately" from the recent (zh-TW launch) feed:
 *  real mention counts + aggregated sentiment from recent episodes — NOT the all-time
 *  agents-precomputed trending_tickers (/api/ticker-insights/trending). */
export async function getRecentBuzz(
  params?: { days?: number; limit?: number }
): Promise<RecentBuzz> {
  const q: Record<string, number> = {};
  if (params?.days != null) q.days = params.days;
  if (params?.limit != null) q.limit = params.limit;
  const response = await apiClient.get('/api/episodes/buzz', {
    params: Object.keys(q).length ? q : undefined,
  });
  const d = response.data ?? {};
  const buzz: RecentBuzz = {
    tickers: Array.isArray(d.tickers) ? d.tickers : [],
    distinct_count: typeof d.distinct_count === 'number' ? d.distinct_count : 0,
    episode_count: typeof d.episode_count === 'number' ? d.episode_count : 0,
  };
  if (d.sentiment_summary) buzz.sentiment_summary = d.sentiment_summary;
  if (d.prev_sentiment_summary) buzz.prev_sentiment_summary = d.prev_sentiment_summary;
  if (d.rising_ticker) buzz.rising_ticker = d.rising_ticker;
  if (Array.isArray(d.new_tickers)) buzz.new_tickers = d.new_tickers;
  return buzz;
}

export interface EpisodePreview {
  id: string;
  title: string;
  podcast_name: string;
  released_at_ms?: number | null;
  key_insights: string[];
  related_tickers: string[];
}

export interface TrendingTag {
  id: string;
  name: string;
  scoped_count: number;
  weekly_counts: number[];
  recent_episodes: EpisodePreview[];
}

export interface TrendingTagsResponse {
  tags: TrendingTag[];
}

export async function getTrendingTags(
  weeks: number = 6,
  previewCount: number = 3,
): Promise<TrendingTagsResponse> {
  const response = await apiClient.get('/api/tags/trending', {
    params: { weeks, preview_count: previewCount },
  });
  const d = response.data ?? {};
  return { tags: Array.isArray(d.tags) ? d.tags : [] };
}

export interface TagRegistryEntry {
  slug: string;
  display_zh: string;
  tier: string;
}

export interface TagRegistryResponse {
  tags: TagRegistryEntry[];
}

export async function getTagRegistry(): Promise<TagRegistryResponse> {
  const response = await apiClient.get('/api/tags/registry');
  const d = response.data ?? {};
  return { tags: Array.isArray(d.tags) ? d.tags : [] };
}

export async function getTags(): Promise<TagsResponse> {
  const response = await apiClient.get('/api/tags');
  if (response.data?.tags && Array.isArray(response.data.tags)) {
    return response.data as TagsResponse;
  }
  if (Array.isArray(response.data)) {
    return { tags: response.data };
  }
  return { tags: [] };
}

export async function getEpisodesByTag(
  tag: string,
  limit: number = 50,
  offset: number = 0,
  includeContent?: boolean
): Promise<any> {
  const params: Record<string, any> = { limit, offset };
  if (includeContent !== undefined) params.include_content = includeContent;
  const response = await apiClient.get(`/api/episodes/by-tag/${encodeURIComponent(tag)}`, { params });
  return response.data;
}

export async function getRecentEpisodes(options?: {
  limit?: number;
  offset?: number;
  podcastName?: string;
  sortBy?: string;
  order?: 'asc' | 'desc';
  includeContent?: boolean;
}): Promise<Episode[]> {
  const params: Record<string, any> = {};
  if (options?.limit) params.limit = options.limit;
  if (options?.offset) params.offset = options.offset;
  if (options?.podcastName) params.podcast_name = options.podcastName;
  if (options?.sortBy) params.sort_by = options.sortBy;
  if (options?.order) params.order = options.order;
  if (options?.includeContent !== undefined) params.include_content = options.includeContent;
  const response = await apiClient.get('/api/episodes/recent', { params });
  if (Array.isArray(response.data)) return response.data;
  if (response.data && typeof response.data === 'object' && Array.isArray(response.data.episodes)) {
    return response.data.episodes;
  }
  if (response.data && typeof response.data === 'object' && Array.isArray(response.data.data)) {
    return response.data.data;
  }
  if (response.data && typeof response.data === 'object') {
    console.warn('[API] getRecentEpisodes - Unexpected response format:', response.data);
  }
  return [];
}

/** @deprecated Use getRecentEpisodes() instead. */
export async function getAllRecentEpisodes(limit: number = 20): Promise<Episode[]> {
  try {
    const podcasts = await getSortedPodcasts({ limit: 50 });
    const episodePromises = podcasts.map(podcast =>
      getPodcastEpisodes(podcast.name, {
        sortBy: 'spotify_release_date', order: 'desc', limit: 10,
      }).catch(() => [] as Episode[])
    );
    const allEpisodeArrays = await Promise.all(episodePromises);
    return allEpisodeArrays
      .flat()
      .sort((a, b) => {
        const dateA = a.spotify_release_date || a.created_time;
        const dateB = b.spotify_release_date || b.created_time;
        const timeA = typeof dateA === 'string' ? new Date(dateA).getTime() : dateA;
        const timeB = typeof dateB === 'string' ? new Date(dateB).getTime() : dateB;
        return timeB - timeA;
      })
      .slice(0, limit);
  } catch (error) {
    console.error('[API] Failed to fetch recent episodes:', error);
    return [];
  }
}

export async function updateEpisodeSummary(
  podcastName: string,
  episodeId: string,
  content: string,
  modifiedBy?: string
): Promise<Episode> {
  const response = await apiClient.put(
    `/api/podcast/${podcastName}/episodes/${episodeId}/summary`,
    { content, modified_by: modifiedBy }
  );
  return response.data;
}

export async function deleteEpisodeSummary(
  podcastName: string,
  episodeId: string
): Promise<void> {
  await apiClient.delete(
    `/api/podcast/${podcastName}/episodes/${episodeId}/summary`
  );
}

export async function patchEpisode(
  podcastName: string,
  episodeId: string,
  updates: Partial<Pick<Episode, 'summary_content' | 'key_insights' | 'related_tickers' | 'tags'>>,
): Promise<Episode> {
  const response = await apiClient.patch(
    `/api/podcast/${podcastName}/episodes/${episodeId}`,
    updates,
  );
  return response.data;
}

export async function getEpisodeHeavy(
  podcastName: string,
  episodeId: string,
): Promise<Episode> {
  const response = await apiClient.get(
    `/api/podcast/${podcastName}/episodes/${episodeId}`,
    { params: { include_heavy_content: true } },
  );
  return response.data;
}
