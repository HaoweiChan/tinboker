/**
 * API client for the read-only Pipeline Settings snapshot.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type { PipelineSettingsResponse } from '@/types/pipeline';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

/**
 * Get the read-only snapshot of the agents' pipeline config (default.yaml).
 */
export async function getPipelineSettings(): Promise<PipelineSettingsResponse> {
  const response = await apiClient.get<PipelineSettingsResponse>(
    '/api/admin/pipeline-settings',
    adminAuthConfig()
  );
  return response.data;
}
