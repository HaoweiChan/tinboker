/**
 * API client for the admin "promo" composer — operator-authored posts (text + media)
 * cross-posted to Threads and/or Facebook. Separate from the episode social flow.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

// Uploads + multi-platform publishing can take a while (Meta processes video); the
// client's 30s default would abort first.
const PROMO_TIMEOUT_MS = 180000;

export type PromoMediaType = 'image' | 'video';

export interface PromoMedia {
  type: PromoMediaType;
  url: string;
  filename?: string;
}

export interface PromoPlatformResult {
  platform: string;
  configured?: boolean;
  dry_run?: boolean;
  posted?: boolean;
  reason?: string;
  plan?: string;
  media_id?: string;
  post_id?: string;
  comment_count?: number;
  posted_comments?: number;
  error?: string;
}

export interface PromoPublishResult {
  platforms: Record<string, PromoPlatformResult>;
}

/** Upload one image/video; returns its type + a signed URL Meta can fetch. */
export async function uploadPromoMedia(file: File): Promise<PromoMedia> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post<PromoMedia>('/api/admin/promo/media', form, {
    ...adminAuthConfig(),
    timeout: PROMO_TIMEOUT_MS,
  });
  return res.data;
}

/** Publish (or, with dryRun, plan) a promo to the selected platforms. */
export async function publishPromo(body: {
  text: string;
  media: PromoMedia[];
  comments: string[];
  platforms: string[];
  dryRun: boolean;
}): Promise<PromoPublishResult> {
  const res = await apiClient.post<PromoPublishResult>(
    '/api/admin/promo/publish',
    {
      text: body.text,
      media: body.media.map((m) => ({ type: m.type, url: m.url })),
      comments: body.comments,
      platforms: body.platforms,
      dry_run: body.dryRun,
    },
    { ...adminAuthConfig(), timeout: PROMO_TIMEOUT_MS },
  );
  return res.data;
}
