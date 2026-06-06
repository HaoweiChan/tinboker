/**
 * API client for stock translations.
 * Includes both public and admin endpoints.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type {
  Translation,
  TranslationPublic,
  TranslationCreate,
  TranslationUpdate,
  TranslationListResponse,
  TranslationListParams,
  BulkImportItem,
  BulkImportResponse,
  MissingTranslationsResponse,
  TranslationStats,
} from '@/types/translation';

function adminAuthConfig() {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  return { headers: { Authorization: `Bearer ${token}` } };
}

// ==================== Public Endpoints ====================

/**
 * Get translation for a ticker.
 * If not found and auto_create=true (default), creates a pending entry for admin review.
 * @param ticker - Stock ticker symbol
 * @param market - Market code (US, TW, JP)
 * @param nameEn - Optional English name hint for auto-creation
 * @param autoCreate - Auto-create pending entry if not found (default: true)
 */
export async function getTranslation(
  ticker: string,
  market: string,
  nameEn?: string,
  autoCreate: boolean = true
): Promise<TranslationPublic | null> {
  try {
    const response = await apiClient.get<TranslationPublic>(
      `/api/stocks/translations/${ticker}`,
      { params: { market, name_en: nameEn, auto_create: autoCreate } }
    );
    return response.data;
  } catch (error: any) {
    if (error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

// ==================== Admin CRUD Endpoints ====================

/**
 * List translations with filters and pagination.
 */
export async function listTranslations(
  params: TranslationListParams = {}
): Promise<TranslationListResponse> {
  const response = await apiClient.get<TranslationListResponse>(
    '/api/admin/translations',
    {
      params,
      ...adminAuthConfig(),
    }
  );
  return response.data;
}

/**
 * Get a single translation by ID.
 */
export async function getTranslationById(
  id: number
): Promise<Translation> {
  const response = await apiClient.get<Translation>(
    `/api/admin/translations/${id}`,
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Create a new translation.
 */
export async function createTranslation(
  data: TranslationCreate
): Promise<Translation> {
  const response = await apiClient.post<Translation>(
    '/api/admin/translations',
    data,
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Update an existing translation.
 */
export async function updateTranslation(
  id: number,
  data: TranslationUpdate
): Promise<Translation> {
  const response = await apiClient.put<Translation>(
    `/api/admin/translations/${id}`,
    data,
    adminAuthConfig()
  );
  return response.data;
}

/**
 * Delete a translation.
 */
export async function deleteTranslation(id: number): Promise<void> {
  await apiClient.delete(`/api/admin/translations/${id}`, adminAuthConfig());
}

// ==================== Admin Bulk Operations ====================

/**
 * Bulk import translations from CSV file.
 */
export async function bulkImportCSV(file: File): Promise<BulkImportResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<BulkImportResponse>(
    '/api/admin/translations/bulk-import',
    formData,
    {
      ...adminAuthConfig(),
      headers: {
        ...adminAuthConfig().headers,
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data;
}

/**
 * Bulk import translations from JSON array.
 */
export async function bulkImportJSON(
  items: BulkImportItem[]
): Promise<BulkImportResponse> {
  const response = await apiClient.post<BulkImportResponse>(
    '/api/admin/translations/bulk-json',
    items,
    adminAuthConfig()
  );
  return response.data;
}

// ==================== Admin Reports ====================

/**
 * Get translations without ZH-TW name.
 */
export async function getMissingTranslations(
  market?: string,
  limit: number = 100
): Promise<MissingTranslationsResponse> {
  const response = await apiClient.get<MissingTranslationsResponse>(
    '/api/admin/translations/missing',
    {
      params: { market, limit },
      ...adminAuthConfig(),
    }
  );
  return response.data;
}

/**
 * Get translation statistics.
 */
export async function getTranslationStats(): Promise<TranslationStats> {
  const response = await apiClient.get<TranslationStats>(
    '/api/admin/translations/stats',
    adminAuthConfig()
  );
  return response.data;
}
