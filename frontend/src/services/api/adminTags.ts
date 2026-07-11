/**
 * API client for admin tag registry management.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

export interface AdminTagEntry {
  /** null for VIRTUAL rows — auto-surfaced tags not yet in the registry. */
  id: number | null;
  slug: string;
  display_zh: string;
  tier: string;
  kind: string;
  /** false = virtual (no registry row); hiding it creates the row. */
  registered?: boolean;
  exposure_id?: string | null;
  /** 'sector' (industry) | 'theme' for sector-kind rows; absent for plain tags. */
  exposure_type?: string | null;
  icon_id?: string | null;
  color_hex?: string | null;
  episode_count?: number | null;
  updated_by?: string | null;
  members?: Array<{
    ticker: string;
    name?: string;
    name_en?: string;
    market?: string;
    source?: string;
    rank?: number;
    reason?: string;
  }>;
  aliases?: string[];
}

export interface AdminTagListResponse {
  tags: AdminTagEntry[];
  total: number;
}

export interface AdminTagCreate {
  slug: string;
  display_zh: string;
  tier: string;
}

export interface AdminTagUpdate {
  display_zh?: string;
  tier?: string;
  members?: Array<{
    ticker: string;
    name?: string;
    name_en?: string;
    market?: string;
    source?: string;
    rank?: number;
    reason?: string;
  }>;
  aliases?: string[];
}

export interface DiscoverResponse {
  discovered: number;
  message: string;
}

export interface SyncSectorsResponse {
  synced: number;
  total: number;
  message: string;
}

export async function listAdminTags(params?: {
  tier?: string;
  kind?: string;
  search?: string;
}): Promise<AdminTagListResponse> {
  const response = await apiClient.get<AdminTagListResponse>(
    '/api/admin/tags',
    { params, ...adminAuthConfig() },
  );
  return response.data;
}

export async function createAdminTag(data: AdminTagCreate): Promise<AdminTagEntry> {
  const response = await apiClient.post<AdminTagEntry>(
    '/api/admin/tags',
    data,
    adminAuthConfig(),
  );
  return response.data;
}

export async function updateAdminTag(id: number, data: AdminTagUpdate): Promise<AdminTagEntry> {
  const response = await apiClient.patch<AdminTagEntry>(
    `/api/admin/tags/${id}`,
    data,
    adminAuthConfig(),
  );
  return response.data;
}

export async function deleteAdminTag(id: number): Promise<void> {
  await apiClient.delete(`/api/admin/tags/${id}`, adminAuthConfig());
}

export async function discoverTags(minEpisodes: number = 3): Promise<DiscoverResponse> {
  const response = await apiClient.post<DiscoverResponse>(
    '/api/admin/tags/discover',
    null,
    { params: { min_episodes: minEpisodes }, ...adminAuthConfig() },
  );
  return response.data;
}

export async function syncSectors(): Promise<SyncSectorsResponse> {
  const response = await apiClient.post<SyncSectorsResponse>(
    '/api/admin/tags/sync-sectors',
    null,
    adminAuthConfig(),
  );
  return response.data;
}

// ── Theme discovery queue (emerging concepts not yet in the universe) ─────────

export interface ThemeCandidateExample {
  episode_title: string;
  context: string;
}

export interface ThemeCandidate {
  normalized_text: string;
  mention_text: string;
  count: number;
  examples: ThemeCandidateExample[];
}

interface ThemeCandidatesResponse {
  candidates: ThemeCandidate[];
}

export async function getThemeCandidates(threshold = 3, limit = 40): Promise<ThemeCandidate[]> {
  const response = await apiClient.get<ThemeCandidatesResponse>(
    '/api/admin/sectors/theme-candidates',
    { params: { threshold, limit }, ...adminAuthConfig() },
  );
  return response.data.candidates ?? [];
}
