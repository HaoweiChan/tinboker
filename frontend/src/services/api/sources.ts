/**
 * API client for followed content sources (admin CRUD).
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type {
  ContentSource,
  ContentSourceCreate,
  ContentSourceUpdate,
  ContentSourceListResponse,
  ContentSourceListParams,
  ContentSourceStats,
  SourceRunStatus,
} from '@/types/contentSource';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

/**
 * List content sources with filters and pagination.
 */
export async function listSources(
  params: ContentSourceListParams = {}
): Promise<ContentSourceListResponse> {
  const response = await apiClient.get<ContentSourceListResponse>(
    '/api/admin/sources',
    { params, ...adminAuthConfig() }
  );
  return response.data;
}

/**
 * Create a new content source.
 */
export async function createSource(
  data: ContentSourceCreate
): Promise<ContentSource> {
  const response = await apiClient.post<ContentSource>(
    '/api/admin/sources',
    data,
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Update an existing content source.
 */
export async function updateSource(
  id: number,
  data: ContentSourceUpdate
): Promise<ContentSource> {
  const response = await apiClient.put<ContentSource>(
    `/api/admin/sources/${id}`,
    data,
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Delete a content source.
 */
export async function deleteSource(id: number): Promise<void> {
  await apiClient.delete(`/api/admin/sources/${id}`, adminAuthConfig());
}

/**
 * Get content-source statistics.
 */
export async function getSourceStats(): Promise<ContentSourceStats> {
  const response = await apiClient.get<ContentSourceStats>(
    '/api/admin/sources/stats',
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Get per-source ingest run-status (last episode ingested), derived from Firestore.
 * Podcasts only in v1; news sources are absent from the result.
 */
export async function getSourcesRunStatus(): Promise<SourceRunStatus[]> {
  const response = await apiClient.get<{ items: SourceRunStatus[] }>(
    '/api/admin/sources/run-status',
    adminAuthConfig()
  );
  return response.data.items;
}
