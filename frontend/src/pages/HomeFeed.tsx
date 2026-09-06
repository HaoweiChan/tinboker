import { useEffect, useMemo, useState } from 'react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, FilterPills } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { NarrativeHero } from '@/components/home/NarrativeHero';
import { BuzzRank } from '@/components/home/BuzzRank';
import { RisingTable } from '@/components/home/RisingTable';
import type { Focus } from '@/components/home/attention';
import { getEpisodesByTag, getEpisodesByTicker, getRecentEpisodes, getSortedPodcasts, type Episode as ApiEpisode, type Podcast } from '@/services/api/podcasts';
import { getAttention } from '@/services/api/attention';
import { normalizeTagSlug } from '@/hooks/useTagLabels';
import type { Attention } from '@/validation/schemas';
import { fetchWithFallback } from '@/services/api/migration';
import { useSubscriptions, useEpisodeBookmarks, useAppStore } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';

const FILTERS = ['最新', '熱門', '追蹤'] as const;
type Filter = (typeof FILTERS)[number];

// Session snapshot of the last successful feed so returning to "/" paints instantly
// (no skeleton flash) and revalidates in the background. Mirrors the module-level
// caches in useStockPriceMap / useEpisodeSentimentMap / fetchWithFallback.
// ponytail: in-memory only; SWR self-heals, no persistence needed.
let homeSnapshot: { episodes: ApiEpisode[]; podcasts: Podcast[]; attention: Attention | null } | null = null;

/** Does this episode belong to the focused narrative / ticker? */
function matchesFocus(ep: ApiEpisode, focus: Focus): boolean {
  if (focus.kind === 'ticker') return (ep.related_tickers ?? []).some((t) => t.toUpperCase().split('.')[0] === focus.key);
  return (ep.tags ?? []).some((t) => normalizeTagSlug(t) === focus.key);
}

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
  const [episodes, setEpisodes] = useState<ApiEpisode[]>(() => homeSnapshot?.episodes ?? []);
  const [podcasts, setPodcasts] = useState<Podcast[]>(() => homeSnapshot?.podcasts ?? []);
  const [attention, setAttention] = useState<Attention | null>(() => homeSnapshot?.attention ?? null);
  const [loading, setLoading] = useState(() => !homeSnapshot);
  const [filter, setFilter] = useState<Filter>('最新');
  // A narrative / ticker picked in the attention blocks narrows the feed below.
  const [focus, setFocus] = useState<Focus | null>(null);
  // Episodes fetched for a focus the loaded feed can't satisfy (older than the last 60).
  const [focusExtra, setFocusExtra] = useState<ApiEpisode[]>([]);
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

  // Top up a focus the last-60 feed can't fill: the by-tag / by-ticker endpoints reach
  // further back. Only when the local hit count is thin, so most clicks stay client-side.
  useEffect(() => {
    setFocusExtra([]);
    if (!focus) return;
    if (episodes.filter((e) => matchesFocus(e, focus)).length >= 4) return;
    let alive = true;
    const req = focus.kind === 'tag'
      ? getEpisodesByTag(focus.key, 10, 0, false).then((r) => r.episodes)
      : getEpisodesByTicker(focus.key, { limit: 10, includeContent: false });
    req.then((extra) => { if (alive) setFocusExtra(extra); }).catch(() => {});
    return () => { alive = false; };
  }, [focus, episodes]);

  const filtered = useMemo(() => {
    let list = episodes;
    if (focus) {
      const seen = new Set(episodes.map((e) => e.id));
      list = [...episodes, ...focusExtra.filter((e) => !seen.has(e.id))].filter((e) => matchesFocus(e, focus));
    }
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
  }, [episodes, filter, subscriptions, focus, focusExtra]);

  // Per-(episode, ticker) sentiment for the visible cards (async; chips populate after render).
  const visibleEpisodeIds = useMemo(() => filtered.map((e) => e.id), [filtered]);
  const sentimentMap = useEpisodeSentimentMap(visibleEpisodeIds);

  return (
    <>
      <SEO description="聽播客 TinBoker — 最新的財經 Podcast 摘要、情緒與相關個股。" />
      <PageContent>
        {/* ① what the market is talking about → ② which tickers → ③ what to listen to.
            Each block floats in after the previous one; the bars/lines grow once landed. */}
        <div className="float-in" style={{ animationDelay: '0ms' }}>
          <NarrativeHero data={attention} focus={focus} onFocus={setFocus} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 mt-3.5">
          <div className="float-in" style={{ animationDelay: '90ms' }}><BuzzRank rows={attention?.tickers ?? []} focus={focus} onFocus={setFocus} /></div>
          <div className="float-in" style={{ animationDelay: '160ms' }}><RisingTable rows={attention?.rising ?? []} focus={focus} onFocus={setFocus} /></div>
        </div>

        <div className="flex items-center gap-3 flex-wrap mt-6 mb-3.5">
          <h2 className="text-lg font-semibold tracking-[-0.02em]">今天聽什麼</h2>
          {focus && (
            <button type="button" onClick={() => setFocus(null)} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border border-primary text-primary hover:bg-primary/10 transition-colors">
              {focus.label} 相關 · <span className="font-mono tabular-nums">{filtered.length}</span> 集<span className="opacity-70">✕</span>
            </button>
          )}
        </div>
        <FilterPills items={FILTERS} value={filter} onChange={setFilter} meta={loading ? null : <span>整理了 <span className="font-mono tabular-nums">{filtered.length}</span> 集</span>} />

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
            {focus ? `最近沒有提到「${focus.label}」的集數。` : filter === '追蹤' ? '尚未追蹤任何節目，去「節目」頁追蹤幾個吧。' : '目前沒有集數。'}
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
