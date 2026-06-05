import { useEffect, useMemo, useState } from 'react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, FilterPills } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { HomeRail } from '@/components/redesign/HomeRail';
import { getRecentEpisodes, getSortedPodcasts, type Episode as ApiEpisode, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useSubscriptions } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';

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
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('最新');
  const subscriptions = useSubscriptions();
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const rawTranslationMap = useTranslationMap(episodeTickers);
  // Flatten to ticker → displayName for the adapter (keeps episodeAdapter dependency-free)
  const translationMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k, v.displayName);
    return m;
  }, [rawTranslationMap]);
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of podcasts) {
      if (p.name && p.image_url) map.set(p.name, p.image_url);
    }
    return map;
  }, [podcasts]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const [data, podcastList] = await Promise.all([
        fetchWithFallback<ApiEpisode[]>(
          () => getRecentEpisodes({ limit: 60, sortBy: 'released_at_ms', order: 'desc', includeContent: false }),
          [],
          'getRecentEpisodes',
        ).catch(() => [] as ApiEpisode[]),
        fetchWithFallback<Podcast[]>(
          () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }),
          [],
          'getSortedPodcasts',
        ).catch(() => [] as Podcast[]),
      ]);
      if (!alive) return;
      setEpisodes(Array.isArray(data) ? data : []);
      setPodcasts(Array.isArray(podcastList) ? podcastList : []);
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

  // Per-(episode, ticker) sentiment for the visible cards (async; chips populate after render).
  const visibleEpisodeIds = useMemo(() => filtered.map((e) => e.id), [filtered]);
  const sentimentMap = useEpisodeSentimentMap(visibleEpisodeIds);

  return (
    <>
      <SEO description="聽播客 TinBoker — 最新的財經 Podcast 摘要、情緒與相關個股。" />
      <PageContent rail={<HomeRail episodeCount={episodes.length} podcasts={podcasts} />}>
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
                <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, sentimentMap.get(ep.id))} />
              ))}
            </div>
            <div className="mt-6 py-3 text-center text-[12px] text-muted-foreground">— 到這邊 —</div>
          </>
        )}
      </PageContent>
    </>
  );
};
