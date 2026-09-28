import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { X } from 'lucide-react';
import { hasSeenOnboarding, markOnboardingSeen } from '@/lib/onboarding';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, FilterPills } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { NarrativeHero } from '@/components/home/NarrativeHero';
import { BuzzRank } from '@/components/home/BuzzRank';
import { RisingTable } from '@/components/home/RisingTable';
import { getRecentEpisodes, getSortedPodcasts, type Episode as ApiEpisode, type Podcast } from '@/services/api/podcasts';
import { getAttention } from '@/services/api/attention';
import type { Attention } from '@/validation/schemas';
import { fetchWithFallback } from '@/services/api/migration';
import { useSubscriptions, useEpisodeBookmarks, useAppStore } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';

const RANKINGS = ['最多人聊', '升溫最快'] as const;
const FILTERS = ['最新', '熱門', '追蹤'] as const;
type Filter = (typeof FILTERS)[number];

// Session snapshot of the last successful feed so returning to "/" paints instantly
// (no skeleton flash) and revalidates in the background. Mirrors the module-level
// caches in useStockPriceMap / useEpisodeSentimentMap / fetchWithFallback.
// ponytail: in-memory only; SWR self-heals, no persistence needed.
let homeSnapshot: { episodes: ApiEpisode[]; podcasts: Podcast[]; attention: Attention | null } | null = null;


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
  const location = useLocation();
  const [guideDismissed, setGuideDismissed] = useState(false);
  const guideParams = new URLSearchParams(location.search);
  guideParams.set('onboarding', 'tutorial');
  const [episodes, setEpisodes] = useState<ApiEpisode[]>(() => homeSnapshot?.episodes ?? []);
  const [podcasts, setPodcasts] = useState<Podcast[]>(() => homeSnapshot?.podcasts ?? []);
  const [attention, setAttention] = useState<Attention | null>(() => homeSnapshot?.attention ?? null);
  const [loading, setLoading] = useState(() => !homeSnapshot);
  const [filter, setFilter] = useState<Filter>('最新');
  const [ranking, setRanking] = useState<(typeof RANKINGS)[number]>('最多人聊');
  const subscriptions = useSubscriptions();
  const episodeBookmarks = useEpisodeBookmarks();
  const { toggleEpisodeBookmark } = useAppStore();
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
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
    // No setLoading(true) here: a warm return paints from homeSnapshot and revalidates
    // silently. The skeleton only shows on a cold start (loading inits to !homeSnapshot).
    (async () => {
      const [data, podcastList, att] = await Promise.all([
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
        getAttention().catch(() => null),
      ]);
      if (!alive) return;
      const eps = Array.isArray(data) ? data : [];
      const pods = Array.isArray(podcastList) ? podcastList : [];
      setEpisodes(eps);
      setPodcasts(pods);
      setAttention(att);
      if (eps.length || pods.length) homeSnapshot = { episodes: eps, podcasts: pods, attention: att };
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    let list = episodes;
    if (filter === '追蹤') {
      const subs = new Set(subscriptions);
      list = subs.size ? list.filter((e) => subs.has(e.podcast_name)) : [];
    } else if (filter === '熱門') {
      const now = Date.now();
      list = [...list].sort((a, b) => {
        const scoreOf = (ep: ApiEpisode) => {
          const engagement = (ep.num_likes ?? 0) + (ep.number_click ?? 0);
          const releaseMs = ep.released_at_ms ?? 0;
          const ageHours = Math.max(0, (now - releaseMs) / 3_600_000);
          return (engagement + 1) / Math.pow(ageHours + 2, 1.2);
        };
        return scoreOf(b) - scoreOf(a);
      });
    } else {
      // "最新" — defensive chronological sort by release time
      list = [...list].sort((a, b) => (b.released_at_ms ?? 0) - (a.released_at_ms ?? 0));
    }
    return list.slice(0, 30);
  }, [episodes, filter, subscriptions]);

  // Per-(episode, ticker) sentiment for the visible cards (async; chips populate after render).
  const visibleEpisodeIds = useMemo(() => filtered.map((e) => e.id), [filtered]);
  const sentimentMap = useEpisodeSentimentMap(visibleEpisodeIds);

  return (
    <>
      <SEO description="聽播客 TinBoker — 最新的財經 Podcast 摘要、情緒與相關個股。" />
      <PageContent>
        {!guideDismissed && !hasSeenOnboarding() && (
          <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-card px-3 py-1.5 text-sm">
            <span className="text-muted-foreground">第一次使用聽播客？</span>
            <Link to={{ pathname: '/', search: guideParams.toString(), hash: location.hash }} className="py-1.5 text-accent-info hover:underline">使用導覽</Link>
            <button type="button" aria-label="關閉導覽提示" onClick={() => { markOnboardingSeen(); setGuideDismissed(true); }} className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded text-muted-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
              <X size={15} aria-hidden />
            </button>
          </div>
        )}
        <section id="market" aria-label="本週市場" className="mb-7 scroll-mt-20">
          <NarrativeHero data={attention} />
          <div role="group" aria-label="選擇市場排行" className="mt-3.5 mb-4 flex items-center gap-5 border-b border-border md:hidden">
            {RANKINGS.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={ranking === item}
                onClick={() => setRanking(item)}
                className={`relative -mb-px py-2 text-sm font-medium tracking-tight transition-colors after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:transition-colors focus-visible:outline-2 focus-visible:outline-ring ${ranking === item ? 'text-foreground after:bg-primary' : 'text-muted-foreground hover:text-foreground after:bg-transparent'}`}
              >
                {item}
              </button>
            ))}
          </div>
          {/* Remount on selection so the newly visible ranking replays its bar animation. */}
          <div key={ranking} className="grid grid-cols-1 md:grid-cols-2 gap-3.5 md:mt-3.5">
            {/* Overlap on mobile so both panels contribute to the shared height.
                Visibility also removes the inactive links from keyboard navigation. */}
            <div className={`col-start-1 row-start-1 grid min-w-0 md:col-auto md:row-auto ${ranking === '最多人聊' ? 'visible' : 'invisible md:visible'}`}>
              <BuzzRank rows={attention?.tickers ?? []} />
            </div>
            <div className={`col-start-1 row-start-1 grid min-w-0 md:col-auto md:row-auto ${ranking === '升溫最快' ? 'visible' : 'invisible md:visible'}`}>
              <RisingTable rows={attention?.rising ?? []} />
            </div>
          </div>
        </section>

        <h2 className="heading-accent text-lg font-semibold tracking-[-0.02em] mb-3.5 flex items-center gap-2">
          今天聽什麼
        </h2>
        <FilterPills items={FILTERS} value={filter} onChange={setFilter} meta={loading ? null : <span>整理了 <span className="font-mono tabular-nums">{filtered.length}</span> 集</span>} />

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
            {filter === '追蹤' ? '尚未追蹤任何節目，去「節目」頁追蹤幾個吧。' : '目前沒有集數。'}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {filtered.map((ep, i) => {
                const bookmarkKey = `${ep.podcast_name}_${ep.id}`;
                return (
                  <div key={ep.id} className="float-in" style={{ animationDelay: `${220 + Math.min(i, 8) * 60}ms` }}>
                  <EpisodeCardV2
                    {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, sentimentMap.get(ep.id), priceSinceMap)}
                    isBookmarked={episodeBookmarks.includes(bookmarkKey)}
                    onBookmark={() => toggleEpisodeBookmark(ep.podcast_name, ep.id)}
                  />
                  </div>
                );
              })}
            </div>
            <div className="mt-6 py-3 text-center text-xs text-muted-foreground">— 到這邊 —</div>
          </>
        )}

      </PageContent>
    </>
  );
};
