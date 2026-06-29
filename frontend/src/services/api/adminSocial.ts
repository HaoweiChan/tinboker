/**
 * API client for admin social-copy (Threads post + per-slide comments) management.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

export interface PostedStatus {
  threads: boolean;
  facebook: boolean;
}

export interface SocialEpisodeListItem {
  episode_id: string;
  podcast_name: string;
  episode_title: string | null;
  released_at_ms: number;
  theme_card_count: number;
  has_copy: boolean;
  comment_count: number;
  has_images: boolean;
  posted: PostedStatus;
}

export interface SocialComment {
  heading: string;
  text: string;
}

export interface SocialThemeCard {
  heading: string;
  bullets: string[];
  image_url: string | null;
}

export interface ComposedThread {
  main_text: string;
  replies: { text: string }[];
  image_urls: string[];
}

export interface SocialEpisodeBundle {
  episode_id: string;
  podcast_name: string;
  episode_title: string | null;
  post: string;
  comments: SocialComment[];
  theme_cards: SocialThemeCard[];
  marp_markdown: string;
  marp_size: string;
  composed: ComposedThread;
  has_copy: boolean;
  posted: PostedStatus;
}

export interface PublishPlatformResult {
  platform: string;
  configured?: boolean;
  dry_run?: boolean;
  posted?: boolean;
  reason?: string;
  url?: string;
  error?: string;
  // Present on a successful publish — used to link straight to the live post.
  post_id?: string;          // Facebook single-post path: {page}_{post}
  root_post_id?: string;     // Facebook thread/album path: {page}_{post}
  root_media_id?: string;    // Threads carousel/root media id
  reply_count?: number;      // Threads replies posted
  comment_count?: number;    // Facebook comments posted
}

export interface PublishResult {
  episode_id: string;
  platforms: Record<string, PublishPlatformResult>;
}

export async function listSocialEpisodes(limit = 30): Promise<SocialEpisodeListItem[]> {
  const res = await apiClient.get<{ episodes: SocialEpisodeListItem[] }>(
    '/api/admin/threads/episodes',
    { params: { limit }, ...adminAuthConfig() },
  );
  return res.data.episodes;
}

export async function getSocialEpisode(episodeId: string): Promise<SocialEpisodeBundle> {
  const res = await apiClient.get<SocialEpisodeBundle>(
    `/api/admin/threads/episodes/${encodeURIComponent(episodeId)}`,
    adminAuthConfig(),
  );
  return res.data;
}

export async function saveSocialEpisode(
  episodeId: string,
  body: { post: string; comments: SocialComment[] },
): Promise<void> {
  await apiClient.patch(
    `/api/admin/threads/episodes/${encodeURIComponent(episodeId)}`,
    body,
    adminAuthConfig(),
  );
}

// LLM generation + multi-post publishing run far longer than the client's 30s
// default; the backend proxies these with a 120s budget, so the browser must wait
// at least as long or it aborts (ECONNABORTED) before the real response lands.
const LLM_REQUEST_TIMEOUT_MS = 120000;

/**
 * Generate (or re-generate) the social copy for an episode via the LLM pipeline.
 * Persists the result server-side; returns the freshly written post + comments.
 */
export async function generateSocialEpisode(
  episodeId: string,
): Promise<{ post: string; comments: SocialComment[] }> {
  const res = await apiClient.post<{ post: string; comments: SocialComment[] }>(
    `/api/admin/threads/episodes/${encodeURIComponent(episodeId)}/social-copy`,
    null,
    { ...adminAuthConfig(), timeout: LLM_REQUEST_TIMEOUT_MS },
  );
  return res.data;
}

/**
 * Render the episode's Marp deck to per-slide card PNGs on demand (stored to GCS,
 * URLs written onto social_cards). Cards aren't pre-rendered per episode anymore;
 * this is triggered from the admin "產生卡片圖" button. Returns the image URLs.
 */
export async function renderSocialCards(
  episodeId: string,
): Promise<{ episode_id: string; image_urls: (string | null)[] }> {
  const res = await apiClient.post<{ episode_id: string; image_urls: (string | null)[] }>(
    `/api/admin/threads/episodes/${encodeURIComponent(episodeId)}/render-cards`,
    null,
    { ...adminAuthConfig(), timeout: LLM_REQUEST_TIMEOUT_MS },
  );
  return res.data;
}

/**
 * Publish one episode's saved copy to the given platforms. Dry-run by default
 * (composes without posting); pass dryRun=false to actually post.
 */
export async function publishSocialEpisode(
  episodeId: string,
  opts: { dryRun?: boolean; platforms?: string } = {},
): Promise<PublishResult> {
  const res = await apiClient.post<PublishResult>(
    `/api/admin/threads/episodes/${encodeURIComponent(episodeId)}/publish`,
    null,
    {
      ...adminAuthConfig(),
      timeout: LLM_REQUEST_TIMEOUT_MS,
      params: {
        dry_run: opts.dryRun ?? true,
        platforms: opts.platforms ?? 'threads,facebook',
      },
    },
  );
  return res.data;
}

export interface ScheduledPost {
  id: number;
  post_type: 'episode' | 'promo';
  episode_id: string | null;
  text: string;
  media: any[];
  comments: any[];
  platforms: string[];
  scheduled_for: string; // ISO-8601 string
  status: 'pending' | 'processing' | 'posted' | 'failed';
  error_message: string | null;
  posted_at: string | null;
  published_results: any;
  created_by: string | null;
  created_at: string;
}

export async function schedulePost(payload: {
  post_type: 'episode' | 'promo';
  episode_id?: string | null;
  text?: string;
  media?: any[] | null;
  comments?: any[] | null;
  platforms: string[];
  scheduled_for: string; // ISO string
}): Promise<{ id: number; status: string }> {
  const res = await apiClient.post<{ id: number; status: string }>(
    '/api/admin/threads/scheduled',
    payload,
    adminAuthConfig(),
  );
  return res.data;
}

export async function listScheduledPosts(status?: string, limit = 50): Promise<ScheduledPost[]> {
  const res = await apiClient.get<{ posts: ScheduledPost[] }>(
    '/api/admin/threads/scheduled',
    { params: { status, limit }, ...adminAuthConfig() },
  );
  return res.data.posts;
}

export async function deleteScheduledPost(postId: number): Promise<void> {
  await apiClient.delete(
    `/api/admin/threads/scheduled/${postId}`,
    adminAuthConfig(),
  );
}

export async function publishScheduledPostNow(postId: number): Promise<{ id: number; status: string }> {
  const res = await apiClient.post<{ id: number; status: string }>(
    `/api/admin/threads/scheduled/${postId}/publish-now`,
    null,
    { ...adminAuthConfig(), timeout: LLM_REQUEST_TIMEOUT_MS },
  );
  return res.data;
}

