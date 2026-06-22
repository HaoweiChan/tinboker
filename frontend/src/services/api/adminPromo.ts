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
  /** Durable gs:// location; persisted in drafts and re-signed into `url` on load. */
  path?: string;
  filename?: string;
}

export interface PromoDraftMeta {
  id: number;
  name: string;
  updated_at: string | null;
  media_count: number;
  comment_count: number;
  platforms: string[];
}

export interface PromoDraftDetail {
  id: number;
  name: string;
  text: string;
  media: PromoMedia[];
  comments: string[];
  platforms: string[];
  updated_at: string | null;
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
  // The shared apiClient defaults to Content-Type: application/json — override it so
  // axios re-detects the FormData and emits multipart/form-data with the boundary,
  // otherwise the backend can't parse the file field (422).
  const auth = adminAuthConfig();
  const res = await apiClient.post<PromoMedia>('/api/admin/promo/media', form, {
    headers: { ...auth.headers, 'Content-Type': 'multipart/form-data' },
    timeout: PROMO_TIMEOUT_MS,
  });
  return res.data;
}

/** List saved promo drafts (newest first, metadata only). */
export async function listPromoDrafts(): Promise<PromoDraftMeta[]> {
  const res = await apiClient.get<{ drafts: PromoDraftMeta[] }>('/api/admin/promo/drafts', adminAuthConfig());
  return res.data.drafts;
}

/** Load one draft, with media re-signed to fresh URLs. */
export async function getPromoDraft(id: number): Promise<PromoDraftDetail> {
  const res = await apiClient.get<PromoDraftDetail>(`/api/admin/promo/drafts/${id}`, adminAuthConfig());
  return res.data;
}

/** Create (no id) or overwrite (with id) a draft. Returns the saved id + name. */
export async function savePromoDraft(
  body: { name: string; text: string; media: PromoMedia[]; comments: string[]; platforms: string[] },
  id?: number,
): Promise<{ id: number; name: string }> {
  const payload = {
    name: body.name,
    text: body.text,
    media: body.media.map((m) => ({ type: m.type, url: m.url, path: m.path, filename: m.filename })),
    comments: body.comments,
    platforms: body.platforms,
  };
  const res = id
    ? await apiClient.put<{ id: number; name: string }>(`/api/admin/promo/drafts/${id}`, payload, adminAuthConfig())
    : await apiClient.post<{ id: number; name: string }>('/api/admin/promo/drafts', payload, adminAuthConfig());
  return res.data;
}

export async function deletePromoDraft(id: number): Promise<void> {
  await apiClient.delete(`/api/admin/promo/drafts/${id}`, adminAuthConfig());
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
