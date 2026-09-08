import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Plus, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, PodAvatar } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { PickCard } from '@/components/financial/PickCard';
import { PodcasterFocusCard } from '@/components/podcaster/PodcasterFocusCard';
import { ConsensusTile } from '@/components/stock/ConsensusTile';
import { CountUp } from '@/components/common/CountUp';
import { cn } from '@/lib/utils';
import { getPodcastByName, getPodcastEpisodes, type Podcast, type Episode as ApiEpisode } from '@/services/api';
import { getInsightsByPodcaster } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTickerWindowReturns, windowReturnsKey } from '@/hooks/useTickerWindowReturns';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useAppStore, useSubscriptions } from '@/store/useAppStore';
import { usePlayerStore } from '@/store/usePlayerStore';
import type { TickerInsight } from '@/services/types';

// The embedded 標的走勢 (pick-performance) block is part of the dev-only /picks
// feature — surfaced on dev.tinboker.com only, hidden on staging/prod (where /picks
// itself is unregistered, so its "查看命中率 →" link would otherwise dead-link).
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

export const PodcasterPage: React.FC = () => {
  const { id } = useParams();
  const { toggleSubscription } = useAppStore();
  const subscriptions = useSubscriptions();
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [picks, setPicks] = useState<TickerInsight[]>([]);
  const playEpisode = usePlayerStore((s) => s.playEpisode);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  const rawTranslationMap = useTranslationMap(episodeTickers);
  const translationMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k, v.displayName);
    return m;
  }, [rawTranslationMap]);
  const [loading, setLoading] = useState(true);

  const name = decodeURIComponent(id || '');
  const isSubscribed = subscriptions.includes(name);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [name]);

  useEffect(() => {
    if (!name) return;
    let alive = true;
    setLoading(true);
    (async () => {
      const wideStart = new Date(Date.now() - 180 * 86_400_000).toISOString().slice(0, 10);
      const wideEnd = new Date().toISOString().slice(0, 10);
      const [meta, eps, ins] = await Promise.all([
        fetchWithFallback<Podcast | null>(() => getPodcastByName(name), null, `getPodcastByName:${name}`).catch(() => null),
        fetchWithFallback<ApiEpisode[]>(() => getPodcastEpisodes(name, { limit: 30, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }), [], `getPodcastEpisodes:${name}`).catch(() => [] as ApiEpisode[]),
        getInsightsByPodcaster(name, { start_date: wideStart, end_date: wideEnd }).catch(() => [] as TickerInsight[]),
      ]);
      if (!alive) return;
      setPodcast(meta);
      setPicks(Array.isArray(ins) ? ins : []);
      // Order by episode_number (the reliable monotonic release signal within a
      // podcast — higher = newer). Only fall back to publish time when an episode
      // has no number. Avoid created_time: it is ingestion time, so re-ingested
      // old episodes would interleave with recent ones.
      const releaseMs = (e: ApiEpisode): number => {
        const r = e.released_at_ms ?? e.spotify_release_date ?? e.created_time;
        return typeof r === 'string' ? Date.parse(r) : (r ?? e.created_time);
      };
      const list = (Array.isArray(eps) ? eps : []).slice().sort((a, b) => {
        if (a.episode_number != null && b.episode_number != null && a.episode_number !== b.episode_number) {
          return b.episode_number - a.episode_number;
        }
        return releaseMs(b) - releaseMs(a);
      });
      setEpisodes(list);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [name]);

  const episodeCount = podcast?.episode_count ?? episodes.length;
  const imageUrl = podcast?.image_url || undefined;
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    if (name && imageUrl) map.set(name, imageUrl);
    return map;
  }, [name, imageUrl]);

  // Ticker-pick scoreboard: forward returns from each mention date.
  const pickRefs = useMemo(
    () =>
      picks
        .map((p) => ({ ticker: p.ticker, reference_ms: Date.parse(p.podcast_launch_time) }))
        .filter((r) => r.ticker && Number.isFinite(r.reference_ms)),
    [picks],
  );
  const windowsMap = useTickerWindowReturns(pickRefs);
  const episodeMap = useMemo(() => {
    const m = new Map<string, ApiEpisode>();
    for (const e of episodes) m.set(e.id, e);
    return m;
  }, [episodes]);
  const onPlaySegment = (episodeId: string, startTimeMs: number) => {
    const ep = episodeMap.get(episodeId);
    const seconds = Math.floor(startTimeMs / 1000);
    if (!ep) {
      window.open(`https://open.spotify.com/search/${encodeURIComponent(episodeId)}`, '_blank');
      return;
    }
    const spotifyUri = ep.spotify_id ? `spotify:episode:${ep.spotify_id}` : undefined;
    playEpisode(
      {
        id: ep.id,
        title: ep.episode_title || ep.id,
        showName: name,
        coverUrl: ep.spotify_images?.[0] || imageUrl,
        spotifyUri,
      },
      spotifyUri ? { seekTo: seconds } : undefined,
    );
  };

  return (
    <>
      <SEO title={`${name} · Podcast 頻道`} description={`追蹤 ${name} 的最新 Podcast 摘要與相關個股分析。`} url={typeof window !== 'undefined' ? window.location.origin + window.location.pathname : undefined} />
      <PageContent>
        {/* Header row — avatar, name, count, subscribe. */}
        <div className="flex items-center gap-4 flex-wrap mb-4">
          <PodAvatar src={imageUrl} name={name} kind="solid" size={56} className="w-14 h-14 rounded-md object-cover shrink-0" />
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-[-0.02em] truncate">{name}</h1>
            <div className="text-sm text-muted-foreground mt-0.5"><strong className="font-mono text-foreground mr-1 tabular-nums">{loading ? '…' : <CountUp value={episodeCount} />}</strong>集已分析 · 由 TinBoker 結構化分析關鍵重點與提及的個股</div>
          </div>
          <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => toggleSubscription(name)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0',
                  isSubscribed ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
                )}
              >
                {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
                {isSubscribed ? '已訂閱' : '訂閱'}
              </button>
          </div>
        </div>

        {!loading && (picks.length > 0 || episodes.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3.5 mb-[18px]">
            {picks.length > 0 && <ConsensusTile key={picks.length} insights={picks} title="近 30 天立場" className="md:col-span-2 md:row-span-2" />}
            <PodcasterFocusCard insights={picks} episodes={episodes} translationMap={translationMap} />
          </div>
        )}

        {IS_DEV_ENV && picks.length > 0 && (
          <>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-muted-foreground">標的走勢（提及日起算）</h2>
              <Link to="/picks" className="text-xs text-accent-info hover:underline">查看命中率 →</Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
              {picks.slice(0, 6).map((pick) => {
                const refMs = Date.parse(pick.podcast_launch_time);
                const windows = Number.isFinite(refMs)
                  ? windowsMap.get(windowReturnsKey(pick.ticker, refMs))
                  : undefined;
                return (
                  <PickCard
                    key={`${pick.episode_id}-${pick.ticker}`}
                    pick={pick}
                    windows={windows}
                    displayName={translationMap.get(pick.ticker)}
                    podcastImage={imageUrl}
                    episodeTitle={episodeMap.get(pick.episode_id)?.episode_title || undefined}
                    shareUrl={`${window.location.origin}/episode/${encodeURIComponent(pick.episode_id)}`}
                    onPlaySegment={onPlaySegment}
                  />
                );
              })}
            </div>
          </>
        )}

        <h2 className="text-sm font-semibold text-muted-foreground mb-3">最新集數</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">此節目目前沒有可顯示的集數。</div>
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

export default PodcasterPage;
