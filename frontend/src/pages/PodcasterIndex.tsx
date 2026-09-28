import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { ExploreTabs } from '@/components/layout/ExploreTabs';
import { PodAvatar } from '@/components/redesign';
import { getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { useEpisodeWindowDays, episodeCountWords } from '@/hooks/useEpisodeWindow';
import { fetchWithFallback } from '@/services/api/migration';
import { compareOptionalNumbers } from '@/lib/listSort';

type Sort = 'popularity_rank' | 'episode_count' | 'subscriber_count';
type Direction = 'asc' | 'desc';
const columns: { key: Sort; label: string; title: string }[] = [
  { key: 'episode_count', label: '集數', title: '已分析集數' },
  { key: 'subscriber_count', label: '站內訂閱', title: '站內訂閱人數' },
  { key: 'popularity_rank', label: 'Apple 排名', title: 'Apple Podcasts 台灣財經排行榜名次' },
];

export const PodcasterIndex: React.FC = () => {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('popularity_rank');
  const [direction, setDirection] = useState<Direction>('asc');
  const changeSort = (key: Sort) => {
    setDirection(key === sort ? (direction === 'asc' ? 'desc' : 'asc') : key === 'popularity_rank' ? 'asc' : 'desc');
    setSort(key);
  };

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const data = await fetchWithFallback<Podcast[]>(() => getSortedPodcasts({ sortBy: 'popularity', order: 'asc', limit: 200 }), [], 'getSortedPodcasts:index').catch(() => [] as Podcast[]);
      if (!alive) return;
      setPodcasts(Array.isArray(data) ? data : []);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const list = useMemo(() => podcasts
    .filter((p) => !q || (p.name || '').toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => compareOptionalNumbers(a[sort], b[sort], direction)
      || compareOptionalNumbers(a.episode_count, b.episode_count, 'desc')
      || a.name.localeCompare(b.name, 'zh-TW')),
  [podcasts, q, sort, direction]);

  const totalEpisodes = podcasts.reduce((s, p) => s + (p.episode_count || 0), 0);
  const countWords = episodeCountWords(useEpisodeWindowDays());

  return (
    <>
      <SEO title="所有節目" description="TinBoker 持續結構化分析的中文財經 Podcast。" />
      <PageContent>
        <ExploreTabs />
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 mb-1">
          <h1 className="heading-accent text-2xl font-semibold tracking-[-0.02em]">所有節目</h1>
          {!loading && <div className="text-xs text-muted-foreground font-mono tabular-nums">{podcasts.length} 個節目 · {countWords.before}{totalEpisodes.toLocaleString('en-US')} {countWords.after}</div>}
        </div>
        <p className="text-base text-muted-foreground max-w-[60ch] mb-4">TinBoker 持續結構化的中文財經 podcast。點任一節目進入完整集數列表與情緒分析。</p>
        <label className="mb-4 flex min-w-0 items-center gap-2 rounded-md border border-border bg-card px-3 py-2 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/30">
          <Search size={14} className="shrink-0 text-muted-foreground" />
          <input aria-label="搜尋節目名稱" value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋節目名稱…" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
        </label>
        {loading ? (
          <div className="overflow-hidden rounded-md border border-border bg-card">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-16 animate-pulse border-b border-border last:border-0" />)}
          </div>
        ) : list.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">{q ? `找不到符合「${q}」的節目` : '目前沒有節目資料。'}</div>
        ) : (
          <div className="overflow-hidden rounded-md border border-border bg-card">
            <table className="w-full table-fixed border-collapse">
              <caption className="sr-only">節目列表；點擊數字欄位標題可切換排序方向</caption>
              <colgroup><col /><col className="w-12 sm:w-24" /><col className="w-[68px] sm:w-28" /><col className="w-[76px] sm:w-32" /></colgroup>
              <thead className="border-b border-border bg-muted/30">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-muted-foreground sm:px-4">節目</th>
                  {columns.map((column) => {
                    const active = sort === column.key;
                    const Icon = active ? (direction === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
                    const nextDirection = active ? (direction === 'asc' ? 'desc' : 'asc') : column.key === 'popularity_rank' ? 'asc' : 'desc';
                    return (
                      <th key={column.key} scope="col" aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'} className="pr-2 text-right last:pr-3 sm:pr-4">
                        <button type="button" onClick={() => changeSort(column.key)} title={column.title}
                          aria-label={`${column.title}排序${active ? `，目前由${direction === 'asc' ? '小到大' : '大到小'}` : ''}，點擊由${nextDirection === 'asc' ? '小到大' : '大到小'}排序`}
                          className={`inline-flex min-h-11 items-center justify-end gap-0.5 whitespace-nowrap text-[10px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-primary sm:gap-1 sm:text-xs ${active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}`}>
                          {column.label}<Icon size={10} aria-hidden="true" className="shrink-0" />
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id || p.name} className="border-b border-border/60 last:border-0 hover:bg-muted/20">
                    <th scope="row" className="px-3 py-3 text-left font-medium sm:px-4">
                      <Link to={`/podcaster/${encodeURIComponent(p.name)}`} className="flex min-h-11 items-center gap-2 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-primary sm:gap-3">
                        <PodAvatar src={p.image_url} name={p.name} size={32} className="h-8 w-8 shrink-0 rounded-md object-cover" />
                        <span className="min-w-0 break-words text-sm leading-snug sm:text-base">{p.name}</span>
                      </Link>
                    </th>
                    <td className="pr-2 text-right text-xs tabular-nums sm:pr-4 sm:text-sm" title={`${countWords.before}${p.episode_count} ${countWords.after}`}>{p.episode_count.toLocaleString('zh-TW')}</td>
                    <td className="pr-2 text-right text-xs tabular-nums sm:pr-4 sm:text-sm" aria-label={p.subscriber_count != null ? `站內 ${p.subscriber_count.toLocaleString('zh-TW')} 人訂閱` : '站內訂閱數暫無資料'}>{p.subscriber_count?.toLocaleString('zh-TW') ?? '—'}</td>
                    <td className={`pr-3 text-right text-xs tabular-nums sm:pr-4 sm:text-sm ${p.popularity_rank != null && p.popularity_rank <= 3 ? 'font-semibold text-primary' : 'text-muted-foreground'}`} title="Apple Podcasts 台灣財經排行榜名次">{p.popularity_rank != null ? `#${p.popularity_rank}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PageContent>
    </>
  );
};
