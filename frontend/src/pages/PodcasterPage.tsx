import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Plus, Check } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2, PodMark } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { cn } from '@/lib/utils';
import { getPodcastByName, getPodcastEpisodes, type Podcast, type Episode as ApiEpisode } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useAppStore, useSubscriptions } from '@/store/useAppStore';

export const PodcasterPage: React.FC = () => {
  const { id } = useParams();
  const { toggleSubscription } = useAppStore();
  const subscriptions = useSubscriptions();
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
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
      const [meta, eps] = await Promise.all([
        fetchWithFallback<Podcast | null>(() => getPodcastByName(name), null, `getPodcastByName:${name}`).catch(() => null),
        fetchWithFallback<ApiEpisode[]>(() => getPodcastEpisodes(name, { limit: 30, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }), [], `getPodcastEpisodes:${name}`).catch(() => [] as ApiEpisode[]),
      ]);
      if (!alive) return;
      setPodcast(meta);
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

  return (
    <>
      <SEO title={`${name} · Podcast 頻道`} description={`追蹤 ${name} 的最新 Podcast 摘要與相關個股分析。`} url={typeof window !== 'undefined' ? window.location.href : undefined} />
      <PageContent>
        {/* Hero */}
        <div className="flex items-start gap-5 bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
          {imageUrl ? (
            <img src={imageUrl} alt={name} className="w-[72px] h-[72px] rounded-md object-cover shrink-0" />
          ) : (
            <PodMark label={(name || '?').charAt(0)} kind="solid" size={72} />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-[22px] font-semibold tracking-[-0.02em] truncate">{name}</h1>
                <div className="flex gap-2 mt-2 flex-wrap">
                  <span className="text-[12px] px-3 py-1 rounded-full bg-muted text-muted-foreground"><strong className="font-mono text-foreground mr-1 tabular-nums">{loading ? '…' : episodeCount.toLocaleString('en-US')}</strong>集已分析</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => toggleSubscription(name)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-medium transition-colors shrink-0',
                  isSubscribed ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
                )}
              >
                {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
                {isSubscribed ? '已訂閱' : '訂閱'}
              </button>
            </div>
            <p className="text-[13px] text-muted-foreground mt-3 max-w-[60ch] leading-[1.55]">{name} 的節目摘要 — 由 TinBoker 結構化分析關鍵重點與提及的個股。</p>
          </div>
        </div>

        <h2 className="text-[13px] font-semibold text-muted-foreground mb-3">最新集數</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">此節目目前沒有可顯示的集數。</div>
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
