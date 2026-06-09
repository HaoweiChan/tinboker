/**
 * Types for the Pipeline Settings page (admin-editable overrides).
 */

export interface PipelineSettingsMeta {
  source: string;
  read_only?: boolean;
  live?: boolean;
  fetched_from?: string;
  stale?: boolean;
  snapshot_of_commit?: string;
  snapshot_date?: string;
  note?: string;
  has_overrides?: boolean;
}

export interface ModelOption {
  id: string;
  label: string;
  price_per_ep: string;
  topic_score: string;
  speed: string;
}

export interface PipelineSettingsResponse {
  meta: PipelineSettingsMeta;
  settings: Record<string, unknown>;
  overrides: Record<string, unknown>;
  available_models: ModelOption[];
}

export interface PipelineOverridesPayload {
  overrides: Record<string, unknown>;
}
