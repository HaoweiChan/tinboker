import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, PodMark } from '@/components/redesign';
import { getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

type Sort = 'popularity' | 'episodes' | 'recent';

export const PodcasterIndex: React.FC = () => {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('popularity');

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const data = await fetchWithFallback<Podcast[]>(() => getSortedPodcasts({ sortBy: 'popularity', order: 'asc', limit: 200 }), [], 'getSortedPodcasts:index').catch(() => [] as Podcast[]);
      if (!alive) return;
      setPodcasts(Array.isArray(data) ? data : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const list = useMemo(() => {
    let arr = podcasts.filter((p) => !q || (p.name || '').toLowerCase().includes(q.toLowerCase()));
    arr = [...arr].sort((a, b) => {
      if (sort === 'episodes') return (b.episode_count || 0) - (a.episode_count || 0);
      if (sort === 'recent') return (b.updated_at || 0) - (a.updated_at || 0);
      // popularity: rank 1 first, unranked last, episode count as tiebreak
      const ra = a.popularity_rank ?? Infinity;
      const rb = b.popularity_rank ?? Infinity;
      if (ra !== rb) return ra - rb;
      return (b.episode_count || 0) - (a.episode_count || 0);
    });
    return arr;
  }, [podcasts, q, sort]);

  const totalEpisodes = podcasts.reduce((s, p) => s + (p.episode_count || 0), 0);

  return (
    <>
      <SEO title="所有節目" description="TinBoker 持續結構化分析的中文財經 Podcast。" />
      <PageContent>
        <div className="flex items-baseline justify-between mb-1">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">所有節目</h1>
          {!loading && (
            <div className="text-xs text-muted-foreground font-mono tabular-nums">
              {podcasts.length} 個節目 · {totalEpisodes.toLocaleString('en-US')} 集已分析
            </div>
          )}
        </div>
        <p className="text-base text-muted-foreground max-w-[60ch] mb-4">TinBoker 持續結構化的中文財經 podcast。點任一節目進入完整集數列表與情緒分析。</p>

        <div className="flex gap-2.5 items-center mb-4 flex-wrap">
          <label className="flex items-center gap-2 flex-1 min-w-[200px] bg-card border border-border rounded-md px-3 py-2">
            <Search size={14} className="text-muted-foreground shrink-0" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋節目名稱…" className="flex-1 bg-transparent outline-none text-sm" />
          </label>
          <Segmented options={[{ value: 'popularity', label: '人氣' }, { value: 'episodes', label: '集數' }, { value: 'recent', label: '最近更新' }] as const} value={sort} onChange={setSort} />
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md p-4 h-[88px] animate-pulse" />
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">{q ? `找不到符合「${q}」的節目` : '目前沒有節目資料。'}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {list.map((p) => (
              <Link key={p.id || p.name} to={`/podcaster/${encodeURIComponent(p.name)}`} className="flex items-center gap-3.5 bg-card border border-border rounded-md p-4 transition-colors hover:border-foreground/25">
                {p.image_url ? (
                  <img src={p.image_url} alt="" className="w-12 h-12 rounded-[10px] object-cover shrink-0" />
                ) : (
                  <PodMark label={(p.name || '?').charAt(0)} kind="mute" size={48} />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-semibold tracking-[-0.01em] truncate">{p.name}</div>
                  <div className="text-2xs text-muted-foreground font-mono tabular-nums mt-1">{(p.episode_count || 0).toLocaleString('en-US')} 集已分析</div>
                </div>
                {p.popularity_rank != null && (
                  <div
                    className={`shrink-0 font-mono tabular-nums font-medium text-xs leading-none px-2 py-1 rounded border ${
                      p.popularity_rank <= 3
                        ? 'border-primary/50 text-primary bg-primary/10'
                        : 'border-border text-muted-foreground'
                    }`}
                    title="Apple Podcasts 台灣財經排行榜名次"
                  >
                    Apple 財經榜 #{p.popularity_rank}
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};
