import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Star, Plus } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Change, StatGroup, SentBar, SentimentChip, EpisodeCardV2, type StatItem } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { TickerInsightCard } from '@/components/financial/TickerInsightCard';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { aggregateSentiment, dominantSentiment } from '@/lib/sentiment';
import { getStockByTicker, getEpisodesByTicker, type Episode as ApiEpisode } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import type { CompanyDetail, RealTimePriceUpdate, TimeframeOption } from '@/services/types';
import { priceWebSocketClient } from '@/services/websocket/priceWebSocket';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { ChartControls } from '@/components/charts/ChartControls';
import { getInsightsByTicker } from '@/services/api/podcasts';
import { transformApiEpisodeToMock } from '@/services/api/transformers';
import type { TickerInsight } from '@/services/types';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { getStockLabel, inferStockMarket } from '@/utils/stockDisplay';

const StockHeaderCard: React.FC<{ symbol: string; episodeCount: number }> = ({ symbol, episodeCount }) => {
  const [stockData, setStockData] = useState<CompanyDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const { watchlist, toggleWatchlist, theme } = useAppStore();
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

  const displayName = stockData?.name ?? symbol;
  const displayPrice = stockData?.price ?? 0;
  const displayChange = stockData?.change ?? 0;
  const displayChangePercent = stockData?.changePercent ?? 0;
  const trend = useStockTrendColor(displayChange);

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

  const latest = (chartData.length > 0 ? chartData[chartData.length - 1] : null) as { open?: number; high?: number; low?: number; volume?: number } | null;
  const keyStats: { label: string; value: string }[] = [
    { label: '開盤', value: (latest?.open ?? displayPrice).toLocaleString() },
    { label: '最高', value: (latest?.high ?? displayPrice).toLocaleString() },
    { label: '最低', value: (latest?.low ?? displayPrice).toLocaleString() },
    { label: '成交量', value: latest?.volume || stockData?.stats?.volume ? `${(((latest?.volume ?? stockData?.stats?.volume) || 0) / 1000).toFixed(1)}K` : '—' },
    { label: '市值', value: stockData?.marketCap ? `${(stockData.marketCap / 1e9).toFixed(2)}B` : '—' },
    { label: '本益比', value: stockData?.pe ? stockData.pe.toFixed(1) : '—' },
  ];

  const { primary: primaryLabel, secondary: secondaryLabel } = getStockLabel({
    ticker: symbol,
    name: stockData?.name,
    market: inferStockMarket(symbol),
  });

  return (
    <>
      {/* Hero */}
      <div className="flex items-start gap-5 bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap mb-1.5">
            <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{isLoading ? displayName : primaryLabel}</h1>
            <span className={cn('text-[12px] px-3 py-1 rounded-full', marketBadge.cls)}>{marketBadge.label}</span>
          </div>
          {secondaryLabel && (
            <p className="text-[13px] text-muted-foreground font-mono mb-1.5">{secondaryLabel}</p>
          )}
          <div className="flex items-baseline gap-3.5 flex-wrap">
            <span className={cn('font-mono tabular-nums text-[32px] font-semibold tracking-[-0.02em]', trend.text)}>{isLoading ? '…' : displayPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
            <Change value={displayChangePercent} big />
            <span className="text-[12px] text-muted-foreground">即時行情 · 延遲 15 分鐘</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => toggleWatchlist(symbol)}
          className={cn(
            'inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-medium transition-colors shrink-0',
            isWatchlisted ? 'bg-card border border-border text-foreground hover:bg-muted' : 'bg-foreground text-background hover:opacity-90',
          )}
        >
          {isWatchlisted ? <Star size={14} className="fill-current" /> : <Plus size={14} />}
          {isWatchlisted ? '已加入' : '加入自選'}
        </button>
      </div>

      {/* Chart + key stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-[18px]">
        <div className="lg:col-span-2 bg-card border border-border rounded-md p-4">
          <ChartControls
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            subChart={subChart}
            onSubChartChange={setSubChart}
            activeIndicators={activeIndicators}
            onToggleIndicator={(ind, active) => setActiveIndicators((prev) => (active ? [...prev, ind] : prev.filter((i) => i !== ind)))}
          />
          <div className="h-[380px] w-full mt-3">
            <TradingViewChart
              data={chartData}
              theme={theme === 'dark' ? 'dark' : 'light'}
              lineColor={trend.lineColor}
              topColor={trend.topColor}
              bottomColor="transparent"
              height={380}
              className="w-full"
              activeIndicators={activeIndicators}
              activeSubChart={subChart}
              onLoadMore={handleLoadMore}
              isLoadingMore={isLoadingMore}
            />
          </div>
        </div>
        <div className="bg-card border border-border rounded-md p-5">
          <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground mb-3.5">關鍵數據</h3>
          <div className="divide-y divide-border">
            {keyStats.map((s) => (
              <div key={s.label} className="flex justify-between items-center py-2.5">
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{s.label}</span>
                <span className="text-[13px] font-mono tabular-nums font-semibold">{s.value}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">{episodeCount} 集 podcast 提到此標的</p>
        </div>
      </div>
    </>
  );
};

export const StockDashboard: React.FC = () => {
  const { ticker } = useParams();
  const symbol = (ticker ?? '2330.TW').toUpperCase();
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
  const [episodesLoading, setEpisodesLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    getInsightsByTicker(symbol)
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

  const breakdown = useMemo(
    () => aggregateSentiment(insights.map((r) => ({ sentiment_label: r.sentiment_label }))),
    [insights],
  );
  const relatedTags = useMemo(() => {
    const set = new Set<string>();
    for (const e of episodes) for (const t of e.tags ?? []) set.add(t);
    return [...set];
  }, [episodes]);
  const newestEp = episodes[0];

  const stats: StatItem[] = [
    {
      label: '提及集數',
      value: <>{episodes.length}<span className="text-[14px] text-muted-foreground ml-1">集</span></>,
    },
    {
      label: '情緒比例',
      textValue: true,
      value: breakdown.total > 0 ? <SentBar bull={breakdown.bull} neutral={breakdown.neutral} bear={breakdown.bear} width={88} /> : <span className="text-muted-foreground text-[14px]">—</span>,
      sub:
        breakdown.total > 0 ? (
          <span>
            <span className="text-sentiment-bull">多 {breakdown.bull}</span> · <span className="text-muted-foreground">中 {breakdown.neutral}</span> · <span className="text-sentiment-bear">空 {breakdown.bear}</span>
          </span>
        ) : (
          '尚無分析'
        ),
    },
    {
      label: '整體情緒',
      textValue: true,
      value: breakdown.total > 0 ? <SentimentChip sentiment={dominantSentiment(breakdown)} /> : <span className="text-muted-foreground text-[14px]">—</span>,
      sub: newestEp ? `最新：${newestEp.podcast_name}${newestEp.episode_number != null ? ` EP ${newestEp.episode_number}` : ''}` : '無資料',
    },
    {
      label: '相關話題',
      value: relatedTags.length,
      sub: relatedTags.length ? relatedTags.slice(0, 3).map((t) => `#${t}`).join(' ') + (relatedTags.length > 3 ? ` +${relatedTags.length - 3}` : '') : '—',
    },
  ];

  return (
    <>
      <SEO
        title={`${symbol} · 股價與相關 Podcast`}
        description={`查看 ${symbol} 的即時股價走勢，以及最新提到此標的的 Podcast 摘要與分析。`}
        url={typeof window !== 'undefined' ? window.location.href : undefined}
      />
      <PageContent>
        <StockHeaderCard symbol={symbol} episodeCount={episodes.length} />

        <div className="mb-[18px]">
          <StatGroup items={stats} />
        </div>

        {insights.length > 0 && (
          <section className="mb-[18px]">
            <h2 className="text-[13px] font-semibold text-muted-foreground mb-3">分析師觀點 & 投資摘要</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {insights.map((rec) => (
                <TickerInsightCard
                  key={`${rec.episode_id}-${rec.ticker}`}
                  insight={rec}
                  episodes={episodes.map(transformApiEpisodeToMock).filter((e): e is NonNullable<typeof e> => e != null)}
                />
              ))}
            </div>
          </section>
        )}

        <h2 className="text-[13px] font-semibold text-muted-foreground mb-3">這檔被哪些集數聊到</h2>
        {episodesLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有 Podcast 提到此標的。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {episodes.map((ep) => (
              <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, undefined, undefined, sentimentMap.get(ep.id), priceSinceMap)} />
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};

export default StockDashboard;
