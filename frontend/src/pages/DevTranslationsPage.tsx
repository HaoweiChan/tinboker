import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Languages, Search } from 'lucide-react';
import {
  isAdminAuthenticated,
  listTranslations,
} from '@/services/api/translations';
import type { Translation, TranslationListParams } from '@/types/translation';

const ITEMS_PER_PAGE = 50;

const STATUS_LABELS: Record<string, string> = {
  approved: 'Approved',
  pending: 'Pending',
  auto: 'Auto',
};

const STATUS_COLORS: Record<string, string> = {
  approved: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  auto: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
};

const statusLabel = (s: string) => STATUS_LABELS[s] ?? s;
const statusColor = (s: string) =>
  STATUS_COLORS[s] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';

export const DevTranslationsPage: React.FC = () => {
  const authenticated = isAdminAuthenticated();
  const [translations, setTranslations] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const fetchData = useCallback(async () => {
    if (!authenticated) return;
    setLoading(true);
    try {
      const params: TranslationListParams = {
        page,
        limit: ITEMS_PER_PAGE,
        market: 'US',
      };
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await listTranslations(params);
      setTranslations(res.items);
      setTotal(res.total);
    } catch {
      // silently fail — admin token may be expired
    } finally {
      setLoading(false);
    }
  }, [authenticated, page, debouncedSearch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

  if (!authenticated) {
    return (
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex items-center gap-3">
          <Languages className="h-6 w-6 text-gray-500 dark:text-gray-400" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            US Ticker Translations
          </h1>
        </div>
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 p-12 text-center dark:border-gray-600 dark:bg-gray-800/50">
          <Languages className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="mb-2 text-sm font-medium text-gray-600 dark:text-gray-400">
            Admin authentication required
          </p>
          <p className="mb-6 text-xs text-gray-500 dark:text-gray-500">
            Log in to the admin panel first to load translation data.
          </p>
          <Link
            to="/admin/translations"
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Go to Admin → Translations
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Languages className="h-6 w-6 text-gray-500 dark:text-gray-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              US Ticker Translations
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {loading ? 'Loading…' : `${total.toLocaleString('en-US')} US tickers`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800">
            <Search className="h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search ticker or name…"
              className="bg-transparent outline-none placeholder:text-gray-400 dark:text-gray-200"
            />
          </label>
          <Link
            to="/admin/translations"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            Edit in Admin
          </Link>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:border-gray-700 dark:bg-gray-700 dark:text-gray-400">
              <th className="px-4 py-3">Ticker</th>
              <th className="px-4 py-3">English Name</th>
              <th className="px-4 py-3">中文名稱</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3">
                      <div className="h-4 w-16 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-48 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-32 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-5 w-16 rounded-full bg-gray-200 dark:bg-gray-600" />
                    </td>
                  </tr>
                ))
              : translations.length === 0
              ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-gray-400 dark:text-gray-500"
                    >
                      {debouncedSearch
                        ? `No results for "${debouncedSearch}"`
                        : 'No translation data.'}
                    </td>
                  </tr>
                )
              : translations.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-gray-900 dark:text-white">
                      {t.ticker}
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                      {t.name_en || '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                      {t.name_zh_tw || (
                        <span className="text-gray-400 dark:text-gray-500">未翻譯</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(t.translation_status)}`}
                      >
                        {statusLabel(t.translation_status)}
                      </span>
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">
            Page {page} of {totalPages}
          </span>
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
    </div>
  );
};
