/**
 * Admin page for managing stock translations.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Upload, LogOut, RefreshCw } from 'lucide-react';
import { AdminLogin } from '@/components/auth/AdminLogin';
import { TranslationFilters } from '@/components/admin/TranslationFilters';
import { TranslationTable } from '@/components/admin/TranslationTable';
import { BulkImportDialog } from '@/components/admin/BulkImportDialog';
import {
  listTranslations,
  updateTranslation,
  deleteTranslation,
  adminLogout,
  isAdminAuthenticated,
} from '@/services/api/translations';
import type { Translation, TranslationStatus, TranslationListParams } from '@/types/translation';

const ITEMS_PER_PAGE = 50;

export const AdminTranslationsPage: React.FC = () => {
  const [authenticated, setAuthenticated] = useState(isAdminAuthenticated());
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // Filters
  const [search, setSearch] = useState('');
  const [market, setMarket] = useState('');
  const [status, setStatus] = useState('');
  // Dialogs
  const [showBulkImport, setShowBulkImport] = useState(false);
  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // Reset to first page on search
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch translations
  const fetchTranslations = useCallback(async () => {
    if (!authenticated) return;
    setLoading(true);
    try {
      const params: TranslationListParams = {
        page,
        limit: ITEMS_PER_PAGE,
      };
      if (debouncedSearch) params.search = debouncedSearch;
      if (market) params.market = market;
      if (status) params.status = status as TranslationStatus;
      const response = await listTranslations(params);
      setTranslations(response.items);
      setTotal(response.total);
    } catch (error: any) {
      if (error.response?.status === 401) {
        // Token expired, logout
        adminLogout();
        setAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  }, [authenticated, page, debouncedSearch, market, status]);

  useEffect(() => {
    fetchTranslations();
  }, [fetchTranslations]);

  // Handle filter changes
  const handleMarketChange = (value: string) => {
    setMarket(value);
    setPage(1);
  };

  const handleStatusChange = (value: string) => {
    setStatus(value);
    setPage(1);
  };

  // Handle update - supports updating name_zh_tw, name_en, or both
  const handleUpdate = async (id: number, nameZhTw?: string, nameEn?: string, newStatus?: TranslationStatus, brandColor?: string | null) => {
    const updateData: { name_zh_tw?: string; name_en?: string; translation_status?: TranslationStatus; brand_color?: string | null } = {};
    if (nameZhTw !== undefined) updateData.name_zh_tw = nameZhTw;
    if (nameEn !== undefined) updateData.name_en = nameEn;
    if (newStatus !== undefined) updateData.translation_status = newStatus;
    if (brandColor !== undefined) updateData.brand_color = brandColor;
    await updateTranslation(id, updateData);
    // Update local state
    setTranslations((prev) =>
      prev.map((t) =>
        t.id === id
          ? {
              ...t,
              name_zh_tw: nameZhTw !== undefined ? nameZhTw : t.name_zh_tw,
              name_en: nameEn !== undefined ? nameEn : t.name_en,
              translation_status: newStatus !== undefined ? newStatus : t.translation_status,
              brand_color: brandColor !== undefined ? brandColor : t.brand_color,
            }
          : t
      )
    );
  };

  // Handle delete
  const handleDelete = async (id: number) => {
    await deleteTranslation(id);
    // Remove from local state
    setTranslations((prev) => prev.filter((t) => t.id !== id));
    setTotal((prev) => prev - 1);
  };

  // Handle logout
  const handleLogout = () => {
    adminLogout();
    setAuthenticated(false);
  };

  // Pagination
  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <AdminLogin onSuccess={() => setAuthenticated(true)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4 dark:border-gray-700 dark:bg-gray-800">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              股票翻譯管理
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              共 {total} 筆翻譯
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchTranslations}
              className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              <RefreshCw className="h-4 w-4" />
              重新整理
            </button>
            <button
              onClick={() => setShowBulkImport(true)}
              className="flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
            >
              <Upload className="h-4 w-4" />
              批次匯入
            </button>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              <LogOut className="h-4 w-4" />
              登出
            </button>
          </div>
        </div>
      </header>
      {/* Content */}
      <main className="mx-auto max-w-7xl px-6 py-6">
        {/* Filters */}
        <div className="mb-6">
          <TranslationFilters
            search={search}
            onSearchChange={setSearch}
            market={market}
            onMarketChange={handleMarketChange}
            status={status}
            onStatusChange={handleStatusChange}
          />
        </div>
        {/* Table */}
        <TranslationTable
          translations={translations}
          loading={loading}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
        />
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-between">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              第 {page} 頁，共 {totalPages} 頁
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-md border border-gray-300 p-2 text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-md border border-gray-300 p-2 text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </main>
      {/* Bulk Import Dialog */}
      <BulkImportDialog
        isOpen={showBulkImport}
        onClose={() => setShowBulkImport(false)}
        onSuccess={fetchTranslations}
      />
    </div>
  );
};
