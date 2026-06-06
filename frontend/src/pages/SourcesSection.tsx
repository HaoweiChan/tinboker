/**
 * Followed content sources (podcast shows + news feeds) admin section.
 * Mirrors the translations admin section; the platform owns this config and the
 * agents pipeline pulls the active rows via GET /api/sources.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Plus, RefreshCw } from 'lucide-react';
import { SourceFilters } from '@/components/admin/SourceFilters';
import { SourceTable } from '@/components/admin/SourceTable';
import { SourceFormDialog, type SourceFormValues } from '@/components/admin/SourceFormDialog';
import { listSources, createSource, updateSource, deleteSource, getSourcesRunStatus } from '@/services/api/sources';
import type {
  ContentSource,
  ContentSourceCreate,
  ContentSourceUpdate,
  ContentSourceListParams,
  SourceRunStatus,
  SourceType,
} from '@/types/contentSource';

const ITEMS_PER_PAGE = 50;

const trimOrNull = (v: string): string | null => (v.trim() ? v.trim() : null);

export const SourcesSection: React.FC = () => {
  const [sources, setSources] = useState<ContentSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // Filters
  const [sourceType, setSourceType] = useState<SourceType>('podcast');
  const [search, setSearch] = useState('');
  const [locale, setLocale] = useState('');
  const [active, setActive] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  // Dialog
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ContentSource | null>(null);
  // Firestore-derived ingest status, keyed by source name (podcasts only in v1).
  const [runStatus, setRunStatus] = useState<Map<string, SourceRunStatus>>(new Map());

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const params: ContentSourceListParams = {
        type: sourceType,
        page,
        limit: ITEMS_PER_PAGE,
      };
      if (debouncedSearch) params.search = debouncedSearch;
      if (locale) {
        if (sourceType === 'news') params.region = locale;
        else params.language = locale;
      }
      if (active) params.active = active === 'true';
      const response = await listSources(params);
      setSources(response.items);
      setTotal(response.total);
    } catch (error) {
      console.error('Failed to fetch sources:', error);
    } finally {
      setLoading(false);
    }
  }, [sourceType, page, debouncedSearch, locale, active]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const fetchRunStatus = useCallback(async () => {
    try {
      const items = await getSourcesRunStatus();
      setRunStatus(new Map(items.map((i) => [i.name, i])));
    } catch (error) {
      console.error('Failed to fetch run status:', error);
    }
  }, []);

  useEffect(() => {
    fetchRunStatus();
  }, [fetchRunStatus]);

  const handleSourceTypeChange = (value: SourceType) => {
    setSourceType(value);
    setLocale('');
    setPage(1);
  };

  // Inline updates (name, episode_limit, active toggle) with optimistic local state.
  const handleUpdate = async (id: number, data: ContentSourceUpdate) => {
    const updated = await updateSource(id, data);
    setSources((prev) => prev.map((s) => (s.id === id ? updated : s)));
  };

  const handleDelete = async (id: number) => {
    await deleteSource(id);
    setSources((prev) => prev.filter((s) => s.id !== id));
    setTotal((prev) => prev - 1);
  };

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (source: ContentSource) => {
    setEditing(source);
    setDialogOpen(true);
  };

  // Build the right payload for create vs edit, normalizing empty strings to null.
  const handleSave = async (values: SourceFormValues, editingId?: number) => {
    const isPodcast = values.source_type === 'podcast';
    const toIntOrNull = (v: string) => (v.trim() ? parseInt(v, 10) : null);
    const shared = {
      name: values.name.trim(),
      feed_url: values.feed_url.trim(),
      region: isPodcast ? null : trimOrNull(values.region),
      language: isPodcast ? trimOrNull(values.language) : null,
      spotify_url: isPodcast ? trimOrNull(values.spotify_url) : null,
      lookback_days: toIntOrNull(values.lookback_days),
      max_episodes: toIntOrNull(values.max_episodes),
      transcript_service: isPodcast ? trimOrNull(values.transcript_service) : null,
      transcript_model: isPodcast ? trimOrNull(values.transcript_model) : null,
      active: values.active,
    };
    if (editingId != null) {
      await updateSource(editingId, shared as ContentSourceUpdate);
    } else {
      await createSource({ source_type: values.source_type, ...shared } as ContentSourceCreate);
    }
    await fetchSources();
  };

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Content Sources</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {total} {sourceType === 'podcast' ? 'podcast shows' : 'news feeds'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              fetchSources();
              fetchRunStatus();
            }}
            className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add {sourceType === 'podcast' ? 'Podcast' : 'Feed'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-6">
        <SourceFilters
          sourceType={sourceType}
          onSourceTypeChange={handleSourceTypeChange}
          search={search}
          onSearchChange={setSearch}
          locale={locale}
          onLocaleChange={(v) => {
            setLocale(v);
            setPage(1);
          }}
          active={active}
          onActiveChange={(v) => {
            setActive(v);
            setPage(1);
          }}
        />
      </div>

      {/* Table */}
      <SourceTable
        sources={sources}
        loading={loading}
        onUpdate={handleUpdate}
        onDelete={handleDelete}
        onEdit={openEdit}
        runStatus={runStatus}
      />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-between">
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Page {page} of {totalPages}
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

      {/* Create / edit dialog */}
      <SourceFormDialog
        isOpen={dialogOpen}
        sourceType={sourceType}
        editing={editing}
        onClose={() => setDialogOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
};
