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
          { exposure_id: exposureId, display_name: '', exposure_type: 'sector', resolved_tickers: [], episodes: [], total: 0 },
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
  // Never flash the raw exposure id (e.g. "sector_passive_components") while the
  // request is in flight or if it fails — show a skeleton, then the resolved name
  // (or a generic label as a last resort).
  const titleText = displayName || '產業 / 主題';

  // A sector is a special kind of tag — follow it by its display name so it unifies with
  // the namesake topic (and shows up under 追蹤話題 like any other tag subscription).
  const { toggleTagSubscription } = useAppStore();
  const tagSubs = useTagSubscriptions();
  const isSubscribed = !!displayName && (tagSubs.includes(displayName) || tagSubs.includes(`#${displayName}`));

  return (
    <>
      <SEO
        title={titleText}
        description={`所有關於「${titleText}」產業 / 主題的 Podcast 摘要與市場討論。`}
      />
      <PageContent>
        <div className="flex items-start gap-5 bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
          {loading ? (
            <div className="w-11 h-11 rounded-md bg-muted animate-pulse shrink-0" />
          ) : (
            <SectorIcon
              exposureId={exposureId ?? ''}
              iconId={data?.icon_id}
              color={data?.color_hex}
              size={26}
              variant="chip"
            />
          )}
          <div className="flex-1 min-w-0">
            {loading ? (
              <div className="h-7 w-40 bg-muted rounded animate-pulse" />
            ) : (
              <h1 className="text-2xl font-semibold tracking-[-0.02em]">{titleText}</h1>
            )}
            <p className="text-sm text-muted-foreground mt-1 max-w-[56ch] leading-[1.55]">
              {loading
                ? '載入中…'
                : `瀏覽所有關於「${titleText}」的 Podcast 摘要與市場討論 · ${episodes.length} 集。`}
            </p>
          </div>
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

        {/* ── Constituent performance — one timeframe at a time via the toggle ── */}
        {loading ? (
          <div className="mb-7">
            <div className="h-4 w-24 bg-muted rounded animate-pulse mb-3" />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="bg-card border border-border dark:border-white/[0.08] rounded-lg h-[72px] animate-pulse" />
              ))}
            </div>
          </div>
        ) : members.length > 0 ? (
          <div className="mb-7">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="text-sm font-semibold text-muted-foreground">成分股表現</h2>
              <TimeframeToggle value={timeframe} onChange={setTimeframe} />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
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
          </div>
        ) : null}

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
