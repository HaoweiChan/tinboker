import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Plus, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2 } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { cn } from '@/lib/utils';
import { getEpisodesByTag, type Episode as ApiEpisode } from '@/services/api';
import { getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useAppStore, useTagSubscriptions } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';
import { topicVisual } from '@/lib/topicVisual';

interface EpisodesByTagResponse {
  tag?: string;
  episodes?: ApiEpisode[];
  total?: number;
}

export const TagPage: React.FC = () => {
  const { tag } = useParams();
  const { toggleTagSubscription } = useAppStore();
  const tagSubs = useTagSubscriptions();
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  // Localize ticker codes (2330 → 台積電) — same wiring as HomeFeed/PodcasterPage,
  // without it the shared episode card falls back to raw symbols on this page.
  const rawTranslationMap = useTranslationMap(episodeTickers);
  const translationMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k, v.displayName);
    return m;
  }, [rawTranslationMap]);
  const tagLabels = useTagLabels();
  // Real podcaster channel icons (podcast_name → image_url); without this the
  // episode cards fall back to placeholder letter avatars on this page.
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of podcasts) {
      if (p.name && p.image_url) map.set(p.name, p.image_url);
    }
    return map;
  }, [podcasts]);

  const cleanTag = decodeURIComponent(tag || '').replace(/^#/, '');
  const displayLabel = tagLabelFor(cleanTag, tagLabels);
  const isSubscribed = tagSubs.includes(cleanTag) || tagSubs.includes(`#${cleanTag}`);

  useEffect(() => {
    if (!cleanTag) return;
    let alive = true;
    setLoading(true);
    (async () => {
      const [res, podcastList] = await Promise.all([
        fetchWithFallback<EpisodesByTagResponse>(
          () => getEpisodesByTag(cleanTag, 50, 0, false),
          { tag: cleanTag, episodes: [], total: 0 },
          `getEpisodesByTag:${cleanTag}`,
        ).catch(() => ({ episodes: [] as ApiEpisode[] })),
        fetchWithFallback<Podcast[]>(
          () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }),
          [],
          'getSortedPodcasts',
        ).catch(() => [] as Podcast[]),
      ]);
      if (!alive) return;
      const list = (Array.isArray(res?.episodes) ? res.episodes : []).slice().sort((a, b) => {
        const da = typeof a.spotify_release_date === 'string' ? Date.parse(a.spotify_release_date) : (a.spotify_release_date ?? a.created_time);
        const db = typeof b.spotify_release_date === 'string' ? Date.parse(b.spotify_release_date) : (b.spotify_release_date ?? b.created_time);
        return (db as number) - (da as number);
      });
      setEpisodes(list);
      setPodcasts(Array.isArray(podcastList) ? podcastList : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [cleanTag]);

  return (
    <>
      <SEO title={`#${displayLabel}`} description={`所有關於「${displayLabel}」的 Podcast 摘要與市場討論。`} />
      <PageContent>
        <div className="flex items-start gap-5 bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
          {(() => {
            const { Icon, gradient } = topicVisual(cleanTag);
            return (
              <div className="w-[72px] h-[72px] rounded-md grid place-items-center text-white shadow-sm shrink-0" style={{ background: gradient }}>
                <Icon size={30} />
              </div>
            );
          })()}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-[-0.02em]">#{displayLabel}</h1>
                <p className="text-sm text-muted-foreground mt-1 max-w-[56ch] leading-[1.55]">
                  瀏覽所有關於「{displayLabel}」的 Podcast 摘要與市場討論{loading ? '' : ` · ${episodes.length} 集`}。
                </p>
              </div>
              <button
                type="button"
                onClick={() => toggleTagSubscription(cleanTag)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0',
                  isSubscribed ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
                )}
              >
                {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
                {isSubscribed ? '已追蹤' : '追蹤話題'}
              </button>
            </div>
          </div>
        </div>

        <h2 className="text-sm font-semibold text-muted-foreground mb-3">相關集數</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">目前沒有相關 Podcast 集數。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {episodes.map((ep) => (
              <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, undefined, priceSinceMap)} />
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};

export default TagPage;
