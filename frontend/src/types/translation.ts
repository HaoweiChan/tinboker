/**
 * TypeScript types for the stock translation system.
 */

// Translation status values
export type TranslationStatus = 'pending' | 'approved' | 'auto';

// Base translation interface
export interface Translation {
  id: number;
  ticker: string;
  market: string;
  name_en: string | null;
  name_zh_tw: string | null;
  brand_color: string | null;
  translation_status: TranslationStatus;
  last_updated_by: string | null;
  last_updated_at: string | null;
  created_at: string | null;
}

// Public translation response
export interface TranslationPublic {
  ticker: string;
  market: string;
  name_en: string | null;
  name_zh_tw: string | null;
  brand_color: string | null;
}

// Create translation request
export interface TranslationCreate {
  ticker: string;
  market: string;
  name_en?: string;
  name_zh_tw?: string;
  translation_status?: TranslationStatus;
}

// Update translation request
export interface TranslationUpdate {
  name_en?: string;
  name_zh_tw?: string;
  translation_status?: TranslationStatus;
  brand_color?: string | null;
}

// Paginated list response
export interface TranslationListResponse {
  total: number;
  page: number;
  limit: number;
  items: Translation[];
}

// Bulk import item
export interface BulkImportItem {
  ticker: string;
  market: string;
  name_en?: string;
  name_zh_tw?: string;
  translation_status?: TranslationStatus;
}

// Bulk import response
export interface BulkImportResponse {
  imported: number;
  updated: number;
  errors: string[];
}

// Missing translation
export interface MissingTranslation {
  ticker: string;
  market: string;
  name_en: string | null;
}

// Missing translations response
export interface MissingTranslationsResponse {
  total: number;
  items: MissingTranslation[];
}

// Translation stats
export interface TranslationStats {
  total: number;
  translated: number;
  by_market: Record<string, number>;
  by_status: Record<string, number>;
}

// Admin login request
export interface AdminLoginRequest {
  password: string;
}

// Admin login response
export interface AdminLoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// Query parameters for listing translations
export interface TranslationListParams {
  market?: string;
  status?: TranslationStatus;
  search?: string;
  page?: number;
  limit?: number;
}
