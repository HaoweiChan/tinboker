/**
 * API client for Pipeline Settings (admin-editable overrides, prompts, trial runs).
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type { PipelineSettingsResponse, PipelineOverridesPayload } from '@/types/pipeline';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function getPipelineSettings(): Promise<PipelineSettingsResponse> {
  const response = await apiClient.get<PipelineSettingsResponse>(
    '/api/admin/pipeline-settings',
    adminAuthConfig()
  );
  return response.data;
}

export async function updatePipelineSettings(
  payload: PipelineOverridesPayload
): Promise<{ ok: boolean; overrides: Record<string, unknown>; updated_by: string; updated_at: string }> {
  const response = await apiClient.put(
    '/api/admin/pipeline-settings',
    payload,
    adminAuthConfig()
  );
  return response.data;
}

// --- Prompts ---

export async function getPipelinePrompts(): Promise<{ prompts: Record<string, string>; prompt_names: string[] }> {
  const response = await apiClient.get('/api/admin/pipeline-prompts', adminAuthConfig());
  return response.data;
}

export async function updatePipelinePrompt(name: string, content: string): Promise<{ ok: boolean }> {
  const response = await apiClient.put(
    `/api/admin/pipeline-prompts/${name}`,
    { content },
    adminAuthConfig()
  );
  return response.data;
}

// --- Trial Runs ---

export interface TrialRunRequest {
  model_id: string;
  role: string;
  episode_id?: string;
}

export interface TrialRunResult {
  run_id: string;
  model_id: string;
  role: string;
  episode_title: string;
  output: Record<string, unknown> | null;
  elapsed_ms: number;
  error: string | null;
  created_by?: string;
  created_at?: string;
}

export async function startTrialRun(req: TrialRunRequest): Promise<TrialRunResult> {
  const response = await apiClient.post('/api/admin/pipeline-trial-run', req, adminAuthConfig());
  return response.data;
}

export async function getTrialRuns(limit = 20): Promise<{ runs: TrialRunResult[] }> {
  const response = await apiClient.get(`/api/admin/pipeline-trial-runs?limit=${limit}`, adminAuthConfig());
  return response.data;
}

export async function deleteTrialRun(runId: string): Promise<{ ok: boolean }> {
  const response = await apiClient.delete(`/api/admin/pipeline-trial-runs/${runId}`, adminAuthConfig());
  return response.data;
}
