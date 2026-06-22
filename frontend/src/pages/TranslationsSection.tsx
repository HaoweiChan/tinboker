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
import type { Translation, TranslationStatus, TranslationUpdate, TranslationListParams } from '@/types/translation';

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
            setTranslations(response.items);
            setTotal(response.total);
        } catch (error) {
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

    // Handle update — accepts a partial patch; uses the server's row as the new local state.
    const handleUpdate = async (id: number, data: TranslationUpdate) => {
        const updated = await updateTranslation(id, data);
        setTranslations((prev) => prev.map((t) => (t.id === id ? updated : t)));
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
                    <h1 className="text-2xl font-bold text-foreground">
                        Stock Translations
                    </h1>
                    <p className="text-base text-muted-foreground">
                        {total} translations
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={fetchTranslations}
                        className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted"
                    >
                        <RefreshCw className="h-4 w-4" />
                        Refresh
                    </button>
                    <button
                        onClick={() => setShowBulkImport(true)}
                        className="flex items-center gap-2 rounded-md bg-accent-info px-3 py-2 text-base text-accent-info-foreground hover:bg-accent-info/90"
                    >
                        <Upload className="h-4 w-4" />
                        Bulk Import
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
                    <div className="text-base text-muted-foreground">
                        Page {page} of {totalPages}
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

            {/* Bulk Import Dialog */}
            <BulkImportDialog
                isOpen={showBulkImport}
                onClose={() => setShowBulkImport(false)}
                onSuccess={fetchTranslations}
            />
        </div>
    );
};
