import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2 } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import {
  getEpisodesBySector,
  getSortedPodcasts,
  getBatchPricesTrailing,
  type EpisodesBySectorResponse,
  type Episode as ApiEpisode,
  type Podcast,
  type SectorResolvedTicker,
  type TrailingPerf,
} from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { SectorTickerCard, type Timeframe } from '@/components/topics/SectorTickerCard';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { SectorHeatCard } from '@/components/topics/SectorHeatCard';
import { CoMentionGraph } from '@/components/topics/CoMentionGraph';
import { WhoTalksTile } from '@/components/stock/WhoTalksTile';
import { Tile } from '@/components/redesign/Tile';
import { Plus, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAppStore, useTagSubscriptions } from '@/store/useAppStore';

function resolvedTickerName(t: SectorResolvedTicker, translationMap: Map<string, string>): string {
  const upper = t.ticker.toUpperCase();
  const bare = upper.replace(/\.[A-Z]+$/i, '');
  for (const key of [upper, bare, `${bare}.TW`, `${bare}.KS`]) {
    const n = translationMap.get(key);
    if (n) return n;
  }
  return t.name || t.ticker;
}

const TIMEFRAMES: { key: Timeframe; label: string }[] = [
  { key: 'd1', label: '1天' },
  { key: 'd7', label: '7天' },
  { key: 'd30', label: '30天' },
  { key: 'd90', label: '90天' },
];

function TimeframeToggle({ value, onChange }: { value: Timeframe; onChange: (t: Timeframe) => void }) {
  return (
    <div className="flex items-center gap-0.5 bg-muted/50 border border-border rounded-lg p-0.5 shrink-0">
      {TIMEFRAMES.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={`px-2.5 py-1 rounded-md text-xs font-medium tabular-nums transition-all duration-150
            ${value === opt.key
              ? 'bg-card text-foreground shadow-sm border border-border/60'
              : 'text-muted-foreground hover:text-foreground'
            }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export const SectorPage: React.FC = () => {
  const { exposureId } = useParams<{ exposureId: string }>();
  const [data, setData] = useState<EpisodesBySectorResponse | null>(null);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<Timeframe>('d1');
  const [perfMap, setPerfMap] = useState<Record<string, TrailingPerf>>({});
  const [perfLoading, setPerfLoading] = useState(false);

  const episodes = useMemo<ApiEpisode[]>(() => data?.episodes ?? [], [data]);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const resolvedTickers = useMemo<SectorResolvedTicker[]>(() => data?.resolved_tickers ?? [], [data]);
  const allTickers = useMemo(
    () => [...new Set([...episodeTickers, ...resolvedTickers.map((t) => t.ticker)])],
    [episodeTickers, resolvedTickers],
  );

  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  const rawTranslationMap = useTranslationMap(allTickers);
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
    if (!exposureId) return;
    let alive = true;
    setLoading(true);
    (async () => {
      const [res, podcastList] = await Promise.all([
        fetchWithFallback<EpisodesBySectorResponse>(
          () => getEpisodesBySector(exposureId, 50, 0),
          { exposure_id: exposureId, display_name: '', exposure_type: 'industry', description: null, resolved_tickers: [], episodes: [], total: 0 },
          `getEpisodesBySector:${exposureId}`,
        ).catch(() => null),
        fetchWithFallback<Podcast[]>(
          () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }),
          [],
          'getSortedPodcasts',
        ).catch(() => [] as Podcast[]),
      ]);
      if (!alive) return;
      if (res) {
        const sorted = [...res.episodes].sort((a, b) => {
          const da = typeof a.spotify_release_date === 'string' ? Date.parse(a.spotify_release_date) : (a.spotify_release_date ?? a.created_time);
          const db = typeof b.spotify_release_date === 'string' ? Date.parse(b.spotify_release_date) : (b.spotify_release_date ?? b.created_time);
          return (db as number) - (da as number);
        });
        setData({ ...res, episodes: sorted });
      }
      setPodcasts(Array.isArray(podcastList) ? podcastList : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [exposureId]);

  // Members shown in the performance grid (resolved constituents, capped at 12).
  const members = useMemo(() => resolvedTickers.slice(0, 12), [resolvedTickers]);
  const memberKey = useMemo(() => members.map((t) => t.ticker).join(','), [members]);

  // Fetch trailing 1/7/30/90D performance for the member tickers.
  useEffect(() => {
    if (!memberKey) {
      setPerfMap({});
      return;
    }
    let alive = true;
    setPerfLoading(true);
    getBatchPricesTrailing(memberKey.split(','))
      .then((m) => { if (alive) setPerfMap(m || {}); })
      .catch(() => { if (alive) setPerfMap({}); })
      .finally(() => { if (alive) setPerfLoading(false); });
    return () => { alive = false; };
  }, [memberKey]);

  const displayName = data?.display_name || '';
  const sectorDescription = data?.description?.trim() || '';
  // Never flash the raw exposure id (e.g. "sector_passive_components") while the
  // request is in flight or if it fails — show a skeleton, then the resolved name
  // (or a generic label as a last resort).
  const titleText = displayName || '產業 / 題材';

  // A sector is a special kind of tag — follow it by its display name so it unifies with
  // the namesake topic (and shows up under 追蹤話題 like any other tag subscription).
  const { toggleTagSubscription } = useAppStore();
  const tagSubs = useTagSubscriptions();
  const isSubscribed = !!displayName && (tagSubs.includes(displayName) || tagSubs.includes(`#${displayName}`));

  return (
    <>
      {/* The sector's own description is the paragraph rendered under the H1 below —
          unique per sector, so it makes a far better meta description than the
          template did (81 sector pages otherwise read as near-identical to Google). */}
      <SEO
        title={titleText}
        description={sectorDescription || `所有關於「${titleText}」產業 / 題材的 Podcast 摘要與市場討論。`}
        url={typeof window !== 'undefined' ? window.location.origin + window.location.pathname : undefined}
      />
      <PageContent>
        {/* Header row — icon, name, follow; the description sits under it as prose. */}
        <div className="flex items-center gap-3 flex-wrap mb-2">
          {loading ? (
            <div className="w-9 h-9 rounded-md bg-muted animate-pulse shrink-0" />
          ) : (
            <SectorIcon
              exposureId={exposureId ?? ''}
              iconId={data?.icon_id}
              color={data?.color_hex}
              size={22}
              variant="chip"
            />
          )}
          {loading ? (
            <div className="h-7 w-40 bg-muted rounded animate-pulse" />
          ) : (
            <h1 className="text-2xl font-semibold tracking-[-0.02em]">{titleText}</h1>
          )}
          {!loading && <span className="text-sm text-muted-foreground tabular-nums">{episodes.length} 集</span>}
          <span className="flex-1" />
          {!loading && displayName && (
            <button
              type="button"
              onClick={() => toggleTagSubscription(displayName)}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0',
                isSubscribed ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
              )}
            >
              {isSubscribed ? <Check size={14} /> : <Plus size={14} />}
              {isSubscribed ? '已追蹤' : '追蹤話題'}
            </button>
          )}
        </div>
        <p className="text-sm text-muted-foreground max-w-[72ch] leading-[1.6] mb-4">
          {loading
            ? '載入中…'
            : sectorDescription || `瀏覽所有關於「${titleText}」的 Podcast 摘要與市場討論 · ${episodes.length} 集。`}
        </p>

        {/* Bento: heat + constituents lead, co-mention graph + who talks below. */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3.5 mb-[18px]">
            <div className="md:col-span-2 md:row-span-2 bg-card border border-border rounded-[10px] h-[300px] animate-pulse" />
            <div className="md:col-span-4 md:row-span-2 bg-card border border-border rounded-[10px] h-[300px] animate-pulse" />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-6 gap-3.5 mb-[18px]">
            {exposureId && <SectorHeatCard exposureId={exposureId} className="md:col-span-2" />}
            {members.length > 0 && (
              <Tile title="成分股表現" aside={<TimeframeToggle value={timeframe} onChange={setTimeframe} />} className="md:col-span-4 md:row-span-2">
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {members.map((t) => (
                    <SectorTickerCard
                      key={t.ticker}
                      ticker={t.ticker}
                      name={resolvedTickerName(t, translationMap)}
                      perf={perfMap[t.ticker.toUpperCase()]}
                      timeframe={timeframe}
                      loading={perfLoading}
                      reason={t.reason}
                    />
                  ))}
                </div>
              </Tile>
            )}
            {episodes.length > 0 && (
              <WhoTalksTile
                rows={episodes.map((ep) => ({ name: ep.podcast_name, n: 1 }))}
                title="誰在談這個題材"
                unit=" 集"
                max={6}
                className="md:col-span-2"
              />
            )}
            {episodes.length > 0 && <CoMentionGraph episodes={episodes} names={translationMap} className="md:col-span-6" />}
          </div>
        )}

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

export default SectorPage;
