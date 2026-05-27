import React, { useEffect, useMemo, useState } from 'react';
import { Search, Mic2 } from 'lucide-react';
import { getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

function formatTs(ts: number | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleDateString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

export const DevPodcasterListPage: React.FC = () => {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const data = await fetchWithFallback<Podcast[]>(
        () => getSortedPodcasts({ sortBy: 'episode_count', order: 'desc', limit: 500 }),
        [],
        'devPodcasterList'
      ).catch(() => [] as Podcast[]);
      if (!alive) return;
      setPodcasts(Array.isArray(data) ? data : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const list = useMemo(
    () =>
      podcasts.filter(
        (p) => !q || (p.name || '').toLowerCase().includes(q.toLowerCase())
      ),
    [podcasts, q]
  );

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Mic2 className="h-6 w-6 text-gray-500 dark:text-gray-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Podcasters</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {loading ? 'Loading…' : `${podcasts.length} podcasters total`}
            </p>
          </div>
        </div>

        <label className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800">
          <Search className="h-4 w-4 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by name…"
            className="bg-transparent outline-none placeholder:text-gray-400 dark:text-gray-200"
          />
        </label>
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:border-gray-700 dark:bg-gray-700 dark:text-gray-400">
              <th className="px-4 py-3">Image</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3 text-right">Episodes</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {loading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3">
                      <div className="h-9 w-9 rounded-lg bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-40 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-24 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="ml-auto h-4 w-10 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-600" />
                    </td>
                  </tr>
                ))
              : list.length === 0
              ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-12 text-center text-gray-400 dark:text-gray-500"
                    >
                      {q ? `No podcasters matching "${q}"` : 'No podcaster data available.'}
                    </td>
                  </tr>
                )
              : list.map((p) => (
                  <tr
                    key={p.id || p.name}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50"
                  >
                    <td className="px-4 py-3">
                      {p.image_url ? (
                        <img
                          src={p.image_url}
                          alt=""
                          className="h-9 w-9 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-200 text-xs font-bold text-gray-500 dark:bg-gray-600 dark:text-gray-400">
                          {(p.name || '?').charAt(0).toUpperCase()}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                      {p.name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">
                      {p.id || '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                      {(p.episode_count || 0).toLocaleString('en-US')}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {formatTs(p.created_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                      {formatTs(p.updated_at)}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
