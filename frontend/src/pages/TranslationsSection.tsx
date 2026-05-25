/**
 * Translations section for admin layout.
 * Simplified version that works within the admin layout context.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Upload, RefreshCw } from 'lucide-react';
import { TranslationFilters } from '@/components/admin/TranslationFilters';
import { TranslationTable } from '@/components/admin/TranslationTable';
import { BulkImportDialog } from '@/components/admin/BulkImportDialog';
import {
    listTranslations,
    updateTranslation,
    deleteTranslation,
} from '@/services/api/translations';
import type { Translation, TranslationStatus, TranslationListParams } from '@/types/translation';

const ITEMS_PER_PAGE = 50;

export const TranslationsSection: React.FC = () => {
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
            setPage(1);
        }, 300);
        return () => clearTimeout(timer);
    }, [search]);

    // Fetch translations
    const fetchTranslations = useCallback(async () => {
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
            const normalizedItems = Array.isArray(response.items)
                ? response.items
                : Array.isArray((response as unknown as { translations?: Translation[] }).translations)
                    ? (response as unknown as { translations: Translation[] }).translations
                    : [];
            const normalizedTotal = typeof response.total === 'number' ? response.total : normalizedItems.length;
            setTranslations(normalizedItems);
            setTotal(normalizedTotal);
        } catch (error: any) {
            console.error('Failed to fetch translations:', error);
        } finally {
            setLoading(false);
        }
    }, [page, debouncedSearch, market, status]);

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

    // Handle update
    const handleUpdate = async (id: number, nameZhTw?: string, nameEn?: string, newStatus?: TranslationStatus) => {
        const updateData: { name_zh_tw?: string; name_en?: string; translation_status?: TranslationStatus } = {};
        if (nameZhTw !== undefined) updateData.name_zh_tw = nameZhTw;
        if (nameEn !== undefined) updateData.name_en = nameEn;
        if (newStatus !== undefined) updateData.translation_status = newStatus;
        await updateTranslation(id, updateData);
        setTranslations((prev) =>
            prev.map((t) =>
                t.id === id
                    ? {
                        ...t,
                        name_zh_tw: nameZhTw !== undefined ? nameZhTw : t.name_zh_tw,
                        name_en: nameEn !== undefined ? nameEn : t.name_en,
                        translation_status: newStatus !== undefined ? newStatus : t.translation_status,
                    }
                    : t
            )
        );
    };

    // Handle delete
    const handleDelete = async (id: number) => {
        await deleteTranslation(id);
        setTranslations((prev) => prev.filter((t) => t.id !== id));
        setTotal((prev) => prev - 1);
    };

    // Pagination
    const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

    return (
        <div className="mx-auto max-w-7xl">
            {/* Header */}
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                        股票代號翻譯管理
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        共 {total} 筆
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
                </div>
            </div>

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
                        第 {page} / {totalPages} 頁
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

            {/* Bulk Import Dialog */}
            <BulkImportDialog
                isOpen={showBulkImport}
                onClose={() => setShowBulkImport(false)}
                onSuccess={fetchTranslations}
            />
        </div>
    );
};
