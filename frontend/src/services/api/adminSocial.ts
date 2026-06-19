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
    adminAuthConfig(),
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
      params: {
        dry_run: opts.dryRun ?? true,
        platforms: opts.platforms ?? 'threads,facebook',
      },
    },
  );
  return res.data;
}
