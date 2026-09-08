import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Star, Plus } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Change, EpisodeCardV2 } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { TickerInsightCard } from '@/components/financial/TickerInsightCard';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { getStockByTicker, getEpisodesByTicker, type Episode as ApiEpisode } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import type { CompanyDetail, RealTimePriceUpdate, TimeframeOption, TickerInsight } from '@/services/types';
import { priceWebSocketClient } from '@/services/websocket/priceWebSocket';
import TradingViewChart, { type MentionSeries } from '@/components/charts/TradingViewChart';
import { ConsensusTile } from '@/components/stock/ConsensusTile';
import { WhoTalksTile } from '@/components/stock/WhoTalksTile';
import { CoMentionTile } from '@/components/stock/CoMentionTile';
import { InstitutionalFlowCard } from '@/components/stock/InstitutionalFlowCard';
import { ChartControls } from '@/components/charts/ChartControls';
import { getInsightsByTicker, getSortedPodcasts, type Podcast } from '@/services/api/podcasts';
import { getMentionHeat, getTickerMentions, type MentionHeatResponse, type TickerMentionsResponse } from '@/services/api/mentions';
import { transformApiEpisodeToMock } from '@/services/api/transformers';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { useIsDesktop } from '@/hooks/useIsDesktop';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { getStockLabel, inferStockMarket } from '@/utils/stockDisplay';
import { Tile } from '@/components/redesign/Tile';
import { SectorIcon } from '@/components/topics/SectorIcon';
import { getSectorsByTicker } from '@/services/api/stocks';
import type { SectorByTickerItem } from '@/validation/schemas';


// Semantic sentiment colours (green bull / red bear), matching the chart dots and
// the SentBar rather than the market price convention.

const StockHeaderCard: React.FC<{ symbol: string; insights: TickerInsight[]; episodes: ApiEpisode[] }> = ({ symbol, insights, episodes }) => {
  const [stockData, setStockData] = useState<CompanyDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const { watchlist, toggleWatchlist, theme } = useAppStore();
  // Sector membership drives both the chips tile and the row layout below.
  const [sectors, setSectors] = useState<SectorByTickerItem[]>([]);
  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setSectors([]);
    getSectorsByTicker(symbol)
      .then((r) => { if (!cancelled) setSectors(r.items); })
      .catch(() => { if (!cancelled) setSectors([]); });
    return () => { cancelled = true; };
  }, [symbol]);
  const { guard } = useRequireAuth();
  // A phone is tall and narrow; a chart that keeps its desktop height there pushes
  // everything else off the screen. The value is a number the canvas needs, so it comes
  // from matchMedia rather than a CSS class.
  const isDesktop = useIsDesktop();
  const chartHeight = isDesktop ? 420 : 300;
  const [timeframe, setTimeframe] = useState<TimeframeOption>('1D');
  const [activeIndicators, setActiveIndicators] = useState<string[]>(['MA5', 'MA20', 'MA60']);
  const [subChart, setSubChart] = useState<string>('Volume');

  const isWatchlisted = watchlist.includes(symbol);
  // Tickers are bare codes (e.g. "2330"), not ".TW"-suffixed — infer from the code shape.
  const market = inferStockMarket(symbol);
  const marketBadge =
    market === 'TW'
      ? { label: '台股 上市', cls: 'bg-sentiment-bull-soft text-sentiment-bull' }
      : market === 'KR'
        ? { label: '韓股', cls: 'bg-muted text-muted-foreground' }
        : { label: '美股', cls: 'bg-accent-info-soft text-accent-info' };

  const fetchStockData = useCallback(async (ticker: string, tf: TimeframeOption) => {
    setIsLoading(true);
    try {
      // Real-or-empty: never fall back to fabricated company data (BUG-7). On
      // failure stockData is null and key stats render as '—'.
      const data = await fetchWithFallback(() => getStockByTicker(ticker.toUpperCase(), tf), null, `GET /api/stocks/${ticker.toUpperCase()}?timeframe=${tf}`);
      setStockData(data);
    } catch (e) {
      console.error('[StockHeaderCard] Failed to fetch stock data:', e);
      setStockData(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (symbol) fetchStockData(symbol, timeframe);
  }, [symbol, timeframe, fetchStockData]);

  const handleLoadMore = useCallback(
    async (beforeTimestamp: number) => {
      if (isLoadingMore) return;
      setIsLoadingMore(true);
      try {
        const moreData = await getStockByTicker(symbol.toUpperCase(), timeframe, { before: beforeTimestamp });
        if (moreData?.chartData && moreData.chartData.length > 0) {
          setStockData((prev) => {
            if (!prev) return moreData;
            const getTs = (p: { timestamp?: number; date?: string }): number | null => {
              if (typeof p.timestamp === 'number' && !Number.isNaN(p.timestamp)) return p.timestamp;
              if (p.date) {
                const t = new Date(p.date).getTime();
                if (!Number.isNaN(t)) return t;
              }
              return null;
            };
            const map = new Map<number, (typeof prev.chartData)[number]>();
            for (const pt of moreData.chartData || []) {
              const ts = getTs(pt);
              if (ts != null) map.set(ts, { ...pt, timestamp: ts });
            }
            for (const pt of prev.chartData || []) {
              const ts = getTs(pt);
              if (ts != null && !map.has(ts)) map.set(ts, { ...pt, timestamp: ts });
            }
            return { ...prev, chartData: Array.from(map.values()).sort((a, b) => (a.timestamp as number) - (b.timestamp as number)) };
          });
        }
      } catch (e) {
        console.error('[StockHeaderCard] Failed to load more data:', e);
      } finally {
        setIsLoadingMore(false);
      }
    },
    [symbol, timeframe, isLoadingMore],
  );

  useEffect(() => {
    if (!symbol) return;
    const offConn = priceWebSocketClient.onConnectionChange(() => {});
    const offPrice = priceWebSocketClient.onPriceUpdate((u: RealTimePriceUpdate) => {
      if (u.ticker === symbol) setStockData((prev) => (prev ? { ...prev, price: u.price, change: u.change, changePercent: u.changePercent } : prev));
    });
    priceWebSocketClient.connect();
    priceWebSocketClient.subscribe([symbol]);
    return () => {
      priceWebSocketClient.unsubscribe([symbol]);
      offConn();
      offPrice();
    };
  }, [symbol]);

  const displayPrice = stockData?.price ?? null;
  const displayChange = stockData?.change ?? 0;
  const displayChangePercent = stockData?.changePercent ?? 0;
  const trend = useStockTrendColor(displayChange);

  // One dot per day a podcast discussed this ticker, coloured by that day's dominant
  // The chart's attention pane. Two things it deliberately is NOT:
  //
  //  · not dots on the candles — a mark on a bar reads as a claim that the talk moved
  //    that bar, and measured over 40 heavily-discussed tickers, mention volume
  //    correlates -0.02 with the next day's return;
  //  · not a raw count — most shows publish weekly, so a daily count is a comb, and the
  //    level mostly tracks how many shows we had ingested. The pane plots a decayed
  //    SHARE of all podcast attention; the chart does the decay, this just supplies the
  //    counts.
  //
  // Fetched separately from `insights`, which is a fixed 90-day window feeding the
  // consensus and 誰在談 cards whose labels say 30/90 天. Widening that would quietly
  // change what those cards mean, and a strip that stops 90 days from the right edge on
  // a multi-year chart looks broken.
  const [mentionHeat, setMentionHeat] = useState<MentionHeatResponse | null>(null);
  useEffect(() => {
    if (!symbol) return;
    let alive = true;
    getMentionHeat(symbol)
      .then((res) => { if (alive) setMentionHeat(res); })
      .catch(() => { if (alive) setMentionHeat(null); });
    return () => { alive = false; };
  }, [symbol]);

  const mentionSeries = useMemo<MentionSeries | undefined>(() => {
    if (!mentionHeat || mentionHeat.series.length === 0) return undefined;
    const secs = (d: string) => Date.parse(d) / 1000;
    return {
      halfLifeDays: mentionHeat.half_life_days || 7,
      ticker: mentionHeat.series.map((r) => ({
        time: secs(r.d),
        bull: r.bull,
        bear: r.bear,
        neutral: Math.max(0, r.n - r.bull - r.bear),
      })),
      market: mentionHeat.market.map((r) => ({ time: secs(r.d), n: r.n })),
    };
  }, [mentionHeat]);

  const rawChart = stockData?.chartData;
  const chartData = useMemo(() => {
    if (rawChart && rawChart.length > 0) {
      const getTs = (p: { timestamp?: number; date?: string }): number | null => {
        if (typeof p.timestamp === 'number' && !Number.isNaN(p.timestamp)) return p.timestamp;
        if (p.date) {
          const t = new Date(p.date).getTime();
          if (!Number.isNaN(t)) return t;
        }
        return null;
      };
      return rawChart
        .reduce<Array<(typeof rawChart)[number]>>((acc, pt) => {
          const ts = getTs(pt);
          if (ts != null) acc.push({ ...pt, timestamp: ts });
          return acc;
        }, [])
        .sort((a, b) => (a.timestamp as number) - (b.timestamp as number));
    }
    // No fabricated price series (BUG-7): render an empty chart when there's no real data.
    return [];
  }, [rawChart]);

  const formatPositiveNumber = (value: number | null | undefined, options?: Intl.NumberFormatOptions) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '—';
    return value.toLocaleString('en-US', options);
  };
  const hasDisplayPrice = typeof displayPrice === 'number' && Number.isFinite(displayPrice) && displayPrice > 0;
  // Period stats from the close history, not the day's open/high/low: the feed is
  // delayed, so intraday numbers read as live when they are not, and a 1-year window
  // is what the chart shows anyway.

  // Resolve names independently of the price API so labels still show when price
  // data is rate-limited / unavailable (stockData is null).
  const translationMap = useTranslationMap([symbol]);
  const translatedName = translationMap.get(symbol.toUpperCase());
  const zhName = translatedName?.hasZhName ? translatedName.displayName : undefined;
  const enName = translatedName?.nameEn?.trim() || stockData?.name?.trim() || undefined;

  // US stocks read top-down as: zh name → English full name → ticker.
  // TW/KR keep the localized name as primary with the ticker as secondary.
  let primaryLabel: string;
  const subLines: { text: string; mono: boolean }[] = [];
  if (market === 'US') {
    primaryLabel = zhName || enName || symbol;
    if (enName && enName !== primaryLabel) subLines.push({ text: enName, mono: false });
    if (primaryLabel !== symbol) subLines.push({ text: symbol, mono: true });
  } else {
    const label = getStockLabel({ ticker: symbol, name: zhName || enName, market });
    primaryLabel = label.primary;
    if (label.secondary) subLines.push({ text: label.secondary, mono: label.secondary === symbol });
  }

  const periodStats = useMemo(() => {
    const closes = chartData.map((p) => ({ t: p.timestamp as number, c: (('close' in p ? p.close : undefined) ?? ('price' in p ? p.price : undefined) ?? 0) as number, v: ('volume' in p ? p.volume : undefined) as number | undefined }))
      .filter((p) => p.c > 0);
    if (closes.length === 0) return null;
    const last = closes[closes.length - 1];
    const pctSince = (days: number): number | null => {
      const cutoff = last.t - days * 86400e3;
      let base: typeof last | null = null;
      for (const p of closes) { if (p.t <= cutoff) base = p; else break; }
      return base ? ((last.c - base.c) / base.c) * 100 : null;
    };
    const year = closes.filter((p) => p.t >= last.t - 365 * 86400e3);
    const hi = Math.max(...year.map((p) => p.c)), lo = Math.min(...year.map((p) => p.c));
    const vols = closes.slice(-20).map((p) => p.v).filter((v): v is number => typeof v === 'number' && v > 0);
    return {
      w1: pctSince(7), m1: pctSince(30), m3: pctSince(90),
      hi, lo, pos: hi > lo ? ((last.c - lo) / (hi - lo)) * 100 : null,
      avgVol: vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : null,
    };
  }, [chartData]);
  const fmtVol = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : `${(v / 1e3).toFixed(0)}K`);
  const keyStats: { label: string; value: React.ReactNode }[] = [
    { label: '近 1 週', value: periodStats?.w1 != null ? <Change value={periodStats.w1} /> : '—' },
    { label: '近 1 月', value: periodStats?.m1 != null ? <Change value={periodStats.m1} /> : '—' },
    { label: '近 3 月', value: periodStats?.m3 != null ? <Change value={periodStats.m3} /> : '—' },
    { label: '52 週區間', value: periodStats ? `${periodStats.lo.toLocaleString('en-US')} – ${periodStats.hi.toLocaleString('en-US')}` : '—' },
    { label: '距 52 週高點', value: periodStats?.pos != null && periodStats.hi > 0 ? <Change value={((displayPrice ?? periodStats.hi) - periodStats.hi) / periodStats.hi * 100} /> : '—' },
    { label: '20 日均量', value: periodStats?.avgVol ? fmtVol(periodStats.avgVol) : '—' },
    { label: '本益比', value: stockData?.pe ? stockData.pe.toFixed(1) : '—' },
  ];

  const stat = (label: string) => keyStats.find((k) => k.label === label)?.value ?? '—';

  return (
    <>
      {/* Header — identity and the action on one line, price on its own beneath it.
          The watchlist button used to trail the price group, so on a phone it wrapped
          onto a line of its own below the price. Pinning it top-right costs no vertical
          space at any width and puts the only action on the page where actions live. */}
      <div className="mb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex items-baseline gap-3 flex-wrap">
            <h1 className="text-2xl font-semibold tracking-[-0.02em]">{primaryLabel}</h1>
            {subLines.map((line) => (
              <span key={line.text} className={cn('text-sm text-muted-foreground', line.mono && 'font-mono')}>{line.text}</span>
            ))}
            <span className={cn('text-xs px-2.5 py-0.5 rounded-full', marketBadge.cls)}>{marketBadge.label}</span>
          </div>
          <button
            type="button"
            onClick={() => guard(() => toggleWatchlist(symbol))}
            className={cn(
              'inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium transition-colors shrink-0',
              isWatchlisted ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
            )}
          >
            {isWatchlisted ? <Star size={14} className="fill-current" /> : <Plus size={14} />}
            {isWatchlisted ? '已自選' : '自選'}
          </button>
        </div>
        <div className="flex items-baseline gap-3 flex-wrap mt-1.5">
          <span className={cn('font-mono tabular-nums text-2xl font-semibold tracking-[-0.02em]', hasDisplayPrice ? trend.text : 'text-muted-foreground')}>
            {isLoading ? '…' : formatPositiveNumber(displayPrice, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          {hasDisplayPrice && <Change value={displayChangePercent} />}
          <span className="text-xs text-muted-foreground">{hasDisplayPrice ? '延遲 15 分鐘' : '行情資料暫無'}</span>
        </div>
      </div>

      {/* Bento: unequal tiles. The CHART leads — it is first in the DOM, so it sits left
          on desktop (where reading starts) and first on a phone (where anything below the
          fold costs a scroll). People arrive at a stock page to see the price; the podcast
          consensus is our differentiator but it is not what they came for, and putting it
          first made them scroll past it to reach the thing they wanted.

          Colours stay on the site's tokens: card/border surfaces, amber primary for
          emphasis, semantic sentiment green/red, cyan only on sector chips. */}
      <div className="grid grid-cols-1 md:grid-cols-10 gap-3.5 mb-[18px]">
        <div className="md:col-span-7 md:row-span-2 md:bg-card md:border md:border-border md:rounded-[10px] md:p-4 flex flex-col">
          <ChartControls
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            subChart={subChart}
            onSubChartChange={setSubChart}
            activeIndicators={activeIndicators}
            onToggleIndicator={(ind, active) => setActiveIndicators((prev) => (active ? [...prev, ind] : prev.filter((i) => i !== ind)))}
          />
          {isLoading ? (
            <div style={{ height: chartHeight }} className="w-full mt-1 rounded-md bg-muted/30 animate-pulse" />
          ) : chartData.length > 0 ? (
            <div style={{ height: chartHeight }} className="w-full mt-1">
              <TradingViewChart
                data={chartData}
                theme={theme === 'dark' ? 'dark' : 'light'}
                lineColor={trend.lineColor}
                topColor={trend.topColor}
                bottomColor="transparent"
                height={chartHeight}
                className="w-full"
                activeIndicators={activeIndicators}
                activeSubChart={subChart}
                onLoadMore={handleLoadMore}
                isLoadingMore={isLoadingMore}
                mentions={mentionSeries}
              />
            </div>
          ) : market !== 'TW' && market !== 'US' ? (
            // We only have price feeds for TW (FinMind) and US (Massive). KR/other foreign
            // tickers surface from podcasts but have no chart source — say so plainly rather
            // than show the generic "try a longer range" hint that will never resolve.
            <div className="h-[260px] w-full mt-3 rounded-md border border-dashed border-border bg-muted/20 flex flex-col items-center justify-center text-center px-6">
              <p className="text-sm font-medium text-foreground">{marketBadge.label}暫不提供股價走勢</p>
              <p className="text-xs text-muted-foreground mt-1">目前股價圖表僅支援台股與美股，{marketBadge.label}個股的行情資料尚未串接。</p>
            </div>
          ) : (
            <div className="h-[260px] w-full mt-3 rounded-md border border-dashed border-border bg-muted/20 flex flex-col items-center justify-center text-center px-6">
              <p className="text-sm font-medium text-foreground">目前沒有可顯示的股價走勢</p>
              <p className="text-xs text-muted-foreground mt-1">資料供應暫時沒有回傳有效價格，請改用較長區間或稍後再試。</p>
            </div>
          )}
        </div>

        {/* key: remount (and re-animate) when the insight list arrives or changes. */}
        <ConsensusTile key={insights.length} insights={insights} className="md:col-span-3 md:row-span-2" />

        {/* Range tile */}
        <div className="md:col-span-2 bg-card border border-border rounded-[10px] p-5 flex flex-col justify-between gap-3">
          <div className="text-xs text-muted-foreground">區間表現</div>
          <div className="grid grid-cols-3 gap-2">
            {['近 1 週', '近 1 月', '近 3 月'].map((l) => (
              <div key={l}>
                <div className="text-2xs text-muted-foreground mb-0.5">{l.replace('近 ', '')}</div>
                <div className="text-xl font-mono tabular-nums font-semibold">{stat(l)}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-muted-foreground tabular-nums flex flex-wrap gap-x-3 gap-y-1">
            <span>52 週 <span className="text-foreground font-mono">{stat('52 週區間')}</span></span>
            <span>距高點 <span className="font-mono">{stat('距 52 週高點')}</span></span>
            <span>均量 <span className="text-foreground font-mono">{stat('20 日均量')}</span></span>
            <span>本益比 <span className="text-foreground font-mono">{stat('本益比')}</span></span>
          </div>
        </div>

        {/* Spans adapt so a US ticker (no 三大法人) or a ticker outside every sector still
            fills its rows. */}
        {market === 'TW' && <InstitutionalFlowCard symbol={symbol} compact className="md:col-span-2" />}
        <WhoTalksTile insights={insights} className={market === 'TW' ? 'md:col-span-2' : 'md:col-span-4'} />
        {sectors.length > 0 && (
          <Tile title="所屬題材" className="md:col-span-2">
            <div className="flex flex-wrap gap-2">
              {sectors.map((item) => (
                <Link
                  key={item.exposure_id}
                  to={`/sector/${encodeURIComponent(item.exposure_id)}`}
                  title={item.reason || undefined}
                  className="inline-flex items-center gap-1.5 rounded-md bg-accent-info-soft text-accent-info px-2.5 py-1 text-xs font-medium hover:opacity-80 transition-opacity"
                >
                  <SectorIcon exposureId={item.exposure_id} iconId={item.icon_id} color={item.color_hex} size={12} variant="chip" />
                  {item.display_name}
                </Link>
              ))}
            </div>
          </Tile>
        )}
        <CoMentionTile symbol={symbol} episodes={episodes} className={sectors.length > 0 ? 'md:col-span-4' : 'md:col-span-6'} max={sectors.length > 0 ? 10 : 14} />
      </div>
    </>
  );
};

export const StockDashboard: React.FC = () => {
  const { ticker } = useParams();
  const symbol = (ticker ?? '2330').toUpperCase().split('.')[0];
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  // Per-(episode, ticker) sentiment for the chips on each related-episode card —
  // sourced from the working /api/episodes/ticker-sentiments endpoint (same as HomeFeed),
  // not the ticker-insights query that powers the 情緒比例/整體情緒 widgets.
  const episodeIds = useMemo(() => episodes.map((e) => e.id), [episodes]);
  const sentimentMap = useEpisodeSentimentMap(episodeIds);
  const [insights, setInsights] = useState<TickerInsight[]>([]);
  // The 觀點 list is long on popular tickers (200+ over 90 days); page it.
  const [insightLimit, setInsightLimit] = useState(8);
  const mockEpisodes = useMemo(
    () => episodes.map(transformApiEpisodeToMock).filter((e): e is NonNullable<typeof e> => e != null),
    [episodes],
  );
  // Post-mention 1/5/20/60 trading-day performance (TKB-001), shown inline on the 觀點 rows.
  const [tickerMentions, setTickerMentions] = useState<TickerMentionsResponse | null>(null);
  const perfByEpisode = useMemo(() => {
    const m = new Map<string, TickerMentionsResponse['mentions'][number]['performance']>();
    for (const x of tickerMentions?.mentions ?? []) if (x.performance) m.set(x.episode_id, x.performance);
    return m;
  }, [tickerMentions]);
  const anyReturns = useMemo(() => [...perfByEpisode.values()].some((p) => p && [p.r1d, p.r5d, p.r20d, p.r60d].some((v) => typeof v === 'number')), [perfByEpisode]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [episodesLoading, setEpisodesLoading] = useState(true);
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of podcasts) {
      if (p.name && p.image_url) map.set(p.name, p.image_url);
    }
    return map;
  }, [podcasts]);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    // The API defaults to the last 7 days; the chart markers and the 30/90-day split
    // need the same 90-day window the crawler description is built from.
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    setInsightLimit(8);
    getInsightsByTicker(symbol, { start_date: iso(new Date(Date.now() - 90 * 86400e3)), end_date: iso(new Date()) })
      .then((recs) => {
        if (!cancelled) setInsights(Array.isArray(recs) ? recs : []);
      })
      .catch(() => {
        if (!cancelled) setInsights([]);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setTickerMentions(null);
    getTickerMentions(symbol)
      .then((res) => {
        if (!cancelled) setTickerMentions(res.mentions.length > 0 ? res : null);
      })
      .catch(() => {
        if (!cancelled) setTickerMentions(null);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  useEffect(() => {
    getSortedPodcasts({ limit: 50 }).then(setPodcasts).catch(() => {});
  }, []);

  useEffect(() => {
    if (!symbol) return;
    let alive = true;
    setEpisodesLoading(true);
    (async () => {
      const eps = await fetchWithFallback<ApiEpisode[]>(
        () => getEpisodesByTicker(symbol, { limit: 50, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }),
        [],
        `getEpisodesByTicker:${symbol}`,
      ).catch(() => [] as ApiEpisode[]);
      if (!alive) return;
      const list = (Array.isArray(eps) ? eps : []).slice().sort((a, b) => {
        const da = typeof a.spotify_release_date === 'string' ? Date.parse(a.spotify_release_date) : (a.spotify_release_date ?? a.created_time);
        const db = typeof b.spotify_release_date === 'string' ? Date.parse(b.spotify_release_date) : (b.spotify_release_date ?? b.created_time);
        return (db as number) - (da as number);
      });
      setEpisodes(list);
      setEpisodesLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [symbol]);

  // The stat tile is labelled as a 30-day figure; `insights` spans 90 days for the
  // chart markers and the split card, so narrow it here.

  return (
    <>
      <SEO
        title={`${symbol} · 股價與相關 Podcast`}
        description={`查看 ${symbol} 的即時股價走勢，以及最新提到此標的的 Podcast 摘要與分析。`}
        url={typeof window !== 'undefined' ? window.location.href : undefined}
      />
      <PageContent>
        <StockHeaderCard symbol={symbol} insights={insights} episodes={episodes} />

        {insights.length > 0 && (
          <section className="mb-[18px]">
            <div className="flex items-baseline justify-between gap-3 mb-3">
              <h2 className="text-sm font-semibold text-muted-foreground">Podcast 觀點</h2>
              <span className="text-xs text-muted-foreground tabular-nums">近 90 天 · {insights.length} 則</span>
            </div>
            <div className="bg-card border border-border rounded-md divide-y divide-border overflow-hidden">
              {insights.slice(0, insightLimit).map((rec) => (
                <TickerInsightCard
                  key={`${rec.episode_id}-${rec.ticker}-${rec.podcaster ?? ''}`}
                  insight={rec}
                  episodes={mockEpisodes}
                  performance={perfByEpisode.get(rec.episode_id) ?? null}
                />
              ))}
            </div>
            {insights.length > insightLimit && (
              <button
                type="button"
                onClick={() => setInsightLimit((n) => n + 12)}
                className="mt-2 w-full rounded-md border border-border bg-card py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
              >
                顯示更多（還有 {insights.length - insightLimit} 則）
              </button>
            )}
            {anyReturns && tickerMentions?.disclaimer && (
              <p className="text-2xs text-muted-foreground/70 leading-relaxed mt-2">{tickerMentions.disclaimer}</p>
            )}
          </section>
        )}

        <h2 className="text-sm font-semibold text-muted-foreground mb-3">這檔被哪些集數聊到</h2>
        {episodesLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">目前沒有 Podcast 提到此標的。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {episodes.map((ep) => (
              <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, undefined, sentimentMap.get(ep.id), priceSinceMap)} />
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};

export default StockDashboard;
