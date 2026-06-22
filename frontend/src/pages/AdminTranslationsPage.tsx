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
} from '@/services/api/translations';
import { useAppStore } from '@/store/useAppStore';
import type { Translation, TranslationStatus, TranslationUpdate, TranslationListParams } from '@/types/translation';

const ITEMS_PER_PAGE = 50;

export const AdminTranslationsPage: React.FC = () => {
  const logout = useAppStore((state) => state.logout);
  const [authenticated, setAuthenticated] = useState(false);
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
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 401 || status === 403) {
        logout();
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

  // Handle update — accepts a partial patch; uses the server's row as the new local state.
  const handleUpdate = async (id: number, data: TranslationUpdate) => {
    try {
      const updated = await updateTranslation(id, data);
      setTranslations((prev) => prev.map((t) => (t.id === id ? updated : t)));
    } catch (error) {
      const resp = (error as { response?: { status?: number; data?: { detail?: string } } })?.response;
      if (resp?.status === 401 || resp?.status === 403) {
        logout();
        setAuthenticated(false);
        return;
      }
      // Surface a market-collision (409) or other failure; refetch so the row reverts.
      const detail = resp?.data?.detail || 'Update failed';
      alert(`Could not update translation: ${detail}`);
      fetchTranslations();
    }
  };

  // Handle delete
  const handleDelete = async (id: number) => {
    await deleteTranslation(id);
    // Remove from local state
    setTranslations((prev) => prev.filter((t) => t.id !== id));
    setTotal((prev) => prev - 1);
  };

  const handleLogout = () => {
    logout();
    setAuthenticated(false);
  };

  // Pagination
  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-background">
        <AdminLogin onSuccess={() => setAuthenticated(true)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">
              股票翻譯管理
            </h1>
            <p className="text-base text-muted-foreground">
              共 {total} 筆翻譯
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchTranslations}
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted"
            >
              <RefreshCw className="h-4 w-4" />
              重新整理
            </button>
            <button
              onClick={() => setShowBulkImport(true)}
              className="flex items-center gap-2 rounded-md bg-accent-info px-3 py-2 text-base text-accent-info-foreground hover:bg-accent-info/90"
            >
              <Upload className="h-4 w-4" />
              批次匯入
            </button>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted"
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
            <div className="text-base text-muted-foreground">
              第 {page} 頁，共 {totalPages} 頁
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-md border border-border p-2 text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-md border border-border p-2 text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
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
