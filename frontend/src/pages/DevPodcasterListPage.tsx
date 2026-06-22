import React, { useEffect, useMemo, useState } from 'react';
import { Search, Mic2 } from 'lucide-react';
import { getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { formatDate } from '@/lib/date';

function formatTs(ts: number | null | undefined): string {
  if (!ts) return '—';
  return formatDate(ts * 1000);
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
          <Mic2 className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Podcasters</h1>
            <p className="text-base text-muted-foreground">
              {loading ? 'Loading…' : `${podcasts.length} podcasters total`}
            </p>
          </div>
        </div>

        <label className="flex items-center gap-2 rounded-md border border-input bg-card px-3 py-2 text-base">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by name…"
            className="bg-transparent outline-none placeholder:text-muted-foreground text-foreground"
          />
        </label>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-base">
          <thead>
            <tr className="border-b border-border bg-muted text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-3">Image</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3 text-right">Episodes</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3">
                      <div className="h-9 w-9 rounded-lg bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-40 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-24 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="ml-auto h-4 w-10 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-20 rounded bg-muted" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-4 w-20 rounded bg-muted" />
                    </td>
                  </tr>
                ))
              : list.length === 0
              ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-12 text-center text-muted-foreground"
                    >
                      {q ? `No podcasters matching "${q}"` : 'No podcaster data available.'}
                    </td>
                  </tr>
                )
              : list.map((p) => (
                  <tr
                    key={p.id || p.name}
                    className="hover:bg-muted/50"
                  >
                    <td className="px-4 py-3">
                      {p.image_url ? (
                        <img
                          src={p.image_url}
                          alt=""
                          className="h-9 w-9 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-xs font-bold text-muted-foreground">
                          {(p.name || '?').charAt(0).toUpperCase()}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">
                      {p.name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {p.id || '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-foreground">
                      {(p.episode_count || 0).toLocaleString('en-US')}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatTs(p.created_at)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
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
