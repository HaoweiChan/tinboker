import { useEffect, useMemo, useState } from 'react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, FilterPills } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { HomeRail } from '@/components/redesign/HomeRail';
import { getRecentEpisodes, getSortedPodcasts, type Episode as ApiEpisode } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useSubscriptions } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';

const FILTERS = ['最新', '我追的', '熱門'] as const;
type Filter = (typeof FILTERS)[number];

function CardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-md p-4 animate-pulse">
      <div className="flex items-center gap-2.5 mb-3">
        <div className="w-7 h-7 rounded-md bg-muted" />
        <div className="h-3 w-32 bg-muted rounded" />
      </div>
      <div className="h-4 w-full bg-muted rounded mb-2" />
      <div className="h-4 w-3/4 bg-muted rounded mb-3.5" />
      <div className="h-8 w-full bg-muted rounded mb-2" />
      <div className="h-8 w-full bg-muted rounded" />
    </div>
  );
}

export const HomeFeed: React.FC = () => {
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('最新');
  const [podcastImageMap, setPodcastImageMap] = useState<Map<string, string>>(new Map());
  const subscriptions = useSubscriptions();
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [data, podcasts] = await Promise.all([
        fetchWithFallback<ApiEpisode[]>(
          () => getRecentEpisodes({ limit: 60, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }),
          [],
          'getRecentEpisodes',
        ).catch(() => [] as ApiEpisode[]),
        fetchWithFallback(() => getSortedPodcasts({ limit: 200 }), [], 'getSortedPodcasts:feed').catch(() => []),
      ]);
      if (!alive) return;
      setEpisodes(Array.isArray(data) ? data : []);
      const map = new Map<string, string>();
      for (const p of Array.isArray(podcasts) ? podcasts : []) {
        if (p.name && p.image_url) map.set(p.name, p.image_url);
      }
      setPodcastImageMap(map);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    let list = episodes;
    if (filter === '我追的') {
      const subs = new Set(subscriptions);
      list = subs.size ? episodes.filter((e) => subs.has(e.podcast_name)) : [];
    } else if (filter === '熱門') {
      list = [...episodes].sort((a, b) => (b.num_likes ?? b.number_click ?? 0) - (a.num_likes ?? a.number_click ?? 0));
    }
    return list.slice(0, 30);
  }, [episodes, filter, subscriptions]);

  return (
    <>
      <SEO description="聽播客 TinBoker — 最新的財經 Podcast 摘要、情緒與相關個股。" />
      <PageContent rail={<HomeRail episodeCount={episodes.length} />}>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-3.5">今天聽什麼</h1>
        <FilterPills items={FILTERS} value={filter} onChange={setFilter} meta={loading ? null : <span>整理了 <span className="font-mono tabular-nums">{filtered.length}</span> 集</span>} />

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
            {filter === '我追的' ? '尚未追蹤任何節目，去「節目」頁追蹤幾個吧。' : '目前沒有集數。'}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {filtered.map((ep) => (
                <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap)} />
              ))}
            </div>
            <div className="mt-6 py-3 text-center text-[12px] text-muted-foreground">— 到這邊 —</div>
          </>
        )}
      </PageContent>
    </>
  );
};
