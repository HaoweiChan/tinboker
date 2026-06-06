/**
 * Types for the read-only Pipeline Settings page (snapshot of the agents' default.yaml).
 */

export interface PipelineSettingsMeta {
  source: string;
  read_only?: boolean;
  // Live read (agents service reachable)
  live?: boolean;
  fetched_from?: string;
  // Snapshot fallback (service unreachable)
  stale?: boolean;
  snapshot_of_commit?: string;
  snapshot_date?: string;
  note?: string;
}

export interface PipelineSettingsResponse {
  meta: PipelineSettingsMeta;
  settings: Record<string, unknown>;
}
