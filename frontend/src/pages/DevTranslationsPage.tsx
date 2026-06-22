import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Languages, Search } from 'lucide-react';
import { listTranslations } from '@/services/api/translations';
import { useAppStore } from '@/store/useAppStore';
import type { Translation, TranslationListParams } from '@/types/translation';

const ITEMS_PER_PAGE = 50;

const STATUS_LABELS: Record<string, string> = {
  approved: 'Approved',
  pending: 'Pending',
  auto: 'Auto',
};

const STATUS_COLORS: Record<string, string> = {
  approved: 'bg-sentiment-bull-soft text-sentiment-bull',
  pending: 'bg-primary/15 text-primary',
  auto: 'bg-accent-info-soft text-accent-info',
};

const statusLabel = (s: string) => STATUS_LABELS[s] ?? s;
const statusColor = (s: string) =>
  STATUS_COLORS[s] ?? 'bg-muted text-muted-foreground';

export const DevTranslationsPage: React.FC = () => {
  const authenticated = !!useAppStore.getState().token;
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
          <Languages className="h-6 w-6 text-muted-foreground" />
          <h1 className="text-2xl font-bold text-foreground">
            US Ticker Translations
          </h1>
        </div>
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/50 p-12 text-center">
          <Languages className="mb-3 h-10 w-10 text-muted-foreground" />
          <p className="mb-2 text-base font-medium text-foreground">
            Admin authentication required
          </p>
          <p className="mb-6 text-xs text-muted-foreground">
            Log in to the admin panel first to load translation data.
          </p>
          <Link
            to="/admin/translations"
            className="rounded-md bg-accent-info px-4 py-2 text-base font-medium text-accent-info-foreground hover:bg-accent-info/90"
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
          <Languages className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              US Ticker Translations
            </h1>
            <p className="text-base text-muted-foreground">
              {loading ? 'Loading…' : `${total.toLocaleString('en-US')} US tickers`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 rounded-md border border-input bg-card px-3 py-2 text-base">
            <Search className="h-4 w-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search ticker or name…"
              className="bg-transparent outline-none placeholder:text-muted-foreground text-foreground"
            />
          </label>
          <Link
            to="/admin/translations"
            className="rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted"
          >
            Edit in Admin
          </Link>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-base">
          <thead>
            <tr className="border-b border-border bg-muted text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-3">Ticker</th>
              <th className="px-4 py-3">English Name</th>
              <th className="px-4 py-3">中文名稱</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3">
                      <div className="h-4 w-16 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-48 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-32 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-5 w-16 rounded-full bg-muted" />
                    </td>
                  </tr>
                ))
              : translations.length === 0
              ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-muted-foreground"
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
                    className="hover:bg-muted/50"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-foreground">
                      {t.ticker}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {t.name_en || '—'}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {t.name_zh_tw || (
                        <span className="text-muted-foreground">未翻譯</span>
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
        <div className="mt-4 flex items-center justify-between text-base">
          <span className="text-muted-foreground">
            Page {page} of {totalPages}
          </span>
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
    </div>
  );
};
