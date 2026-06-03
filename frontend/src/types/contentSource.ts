/**
 * TypeScript types for followed content sources (podcast shows + news RSS feeds).
 */

export type SourceType = 'podcast' | 'news';

export interface ContentSource {
  id: number;
  source_type: SourceType;
  name: string;
  slug: string;
  feed_url: string;
  region: string | null;
  language: string | null;
  spotify_url: string | null;
  lookback_days: number | null;
  max_episodes: number | null;
  transcript_service: string | null;
  transcript_model: string | null;
  active: boolean;
  extra: Record<string, unknown> | null;
  last_updated_by: string | null;
  last_updated_at: string | null;
  created_at: string | null;
}

export interface ContentSourceCreate {
  source_type: SourceType;
  name: string;
  feed_url: string;
  region?: string | null;
  language?: string | null;
  spotify_url?: string | null;
  lookback_days?: number | null;
  max_episodes?: number | null;
  transcript_service?: string | null;
  transcript_model?: string | null;
  active?: boolean;
}

export interface ContentSourceUpdate {
  name?: string;
  feed_url?: string;
  region?: string | null;
  language?: string | null;
  spotify_url?: string | null;
  lookback_days?: number | null;
  max_episodes?: number | null;
  transcript_service?: string | null;
  transcript_model?: string | null;
  active?: boolean;
}

export interface ContentSourceListResponse {
  total: number;
  page: number;
  limit: number;
  items: ContentSource[];
}

export interface ContentSourceListParams {
  type?: SourceType;
  region?: string;
  language?: string;
  active?: boolean;
  search?: string;
  page?: number;
  limit?: number;
}

export interface ContentSourceStats {
  total: number;
  active: number;
  by_type: Record<string, number>;
}
