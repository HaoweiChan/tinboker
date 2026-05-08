import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Star, Bell, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { Card, CardContent, Button } from '@/components/ui';
import EpisodeCard from '@/components/home/EpisodeCard';
import { useAppStore } from '@/store/useAppStore';
import { SEO } from '@/components/common/SEO';
import type { Episode as MockEpisode } from '@/data/mockData';
import { getStockByTicker, getEpisodesByTicker } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { mockCompanyDetails, generateMockPriceSeries } from '@/services/mocks';
import type { CompanyDetail, RealTimePriceUpdate, TimeframeOption } from '@/services/types';
import { priceWebSocketClient } from '@/services/websocket/priceWebSocket';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { ChartControls } from '@/components/charts/ChartControls';
import { transformApiEpisodeToMock } from '@/services/api/transformers';
import { recommendationService } from '@/services/recommendationService';
import { TickerInsightCard } from '@/components/financial/TickerInsightCard';
import type { TickerRecommendation } from '@/services/types';




const StockHeaderCard: React.FC<{ symbol: string }> = ({ symbol }) => {
  const [stockData, setStockData] = useState<CompanyDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const { watchlist, alerts, toggleWatchlist, toggleAlert, theme } = useAppStore();

  // Chart Configuration
  const [timeframe, setTimeframe] = useState<TimeframeOption>('1D');
  const [activeIndicators, setActiveIndicators] = useState<string[]>(['MA5', 'MA20', 'MA60']);
  const [subChart, setSubChart] = useState<string>('Volume');


  const isWatchlisted = watchlist.includes(symbol);
  const isAlertSet = alerts.includes(symbol);

  // Fetch stock data
  const fetchStockData = useCallback(async (ticker: string, tf: TimeframeOption) => {
    setIsLoading(true);
    try {
      // Ensure ticker is uppercase for stock API (episodes API uses lowercase)
      const stockTicker = ticker.toUpperCase();
      const data = await fetchWithFallback(
        () => getStockByTicker(stockTicker, tf),
        mockCompanyDetails[ticker] || null,
        `GET /api/stocks/${stockTicker}?timeframe=${tf}`
      );

      setStockData(data);
    } catch (error) {
      console.error('[StockHeaderCard] Failed to fetch stock data:', error);
      setStockData(mockCompanyDetails[ticker] || null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (symbol) {
      fetchStockData(symbol, timeframe);
    }
  }, [symbol, timeframe, fetchStockData]);

  // Handle infinite scroll - load more historical data
  const handleLoadMore = useCallback(async (beforeTimestamp: number) => {
    if (isLoadingMore) return;

    setIsLoadingMore(true);
    try {
      const stockTicker = symbol.toUpperCase();
      const moreData = await getStockByTicker(stockTicker, timeframe, { before: beforeTimestamp });

      if (moreData?.chartData && moreData.chartData.length > 0) {
        // Merge with existing data
        setStockData(prev => {
          if (!prev) return moreData;

          // Combine old (new fetch) and existing data
          const existingData = prev.chartData || [];
          const newData = moreData.chartData || [];

          // Create a map to deduplicate by timestamp
          const dataMap = new Map<number, typeof existingData[0]>();

          // Helper to safely get timestamp
          const getSafeTimestamp = (p: any): number | null => {
            if (typeof p.timestamp === 'number' && !isNaN(p.timestamp)) {
              return p.timestamp;
            }
            if (p.date) {
              const t = new Date(p.date).getTime();
              if (!isNaN(t)) return t;
            }
            return null;
          };

          // Add new (older) data first
          for (const point of newData) {
            const ts = getSafeTimestamp(point);
            if (ts !== null) {
              // Ensure timestamp is set on the object we store
              dataMap.set(ts, { ...point, timestamp: ts });
            }
          }

          // Add existing data (will not overwrite if timestamp already exists)
          for (const point of existingData) {
            const ts = getSafeTimestamp(point);
            if (ts !== null) {
              if (!dataMap.has(ts)) {
                dataMap.set(ts, { ...point, timestamp: ts });
              }
            }
          }

          // Convert back to array and sort by time
          const mergedData = Array.from(dataMap.values()).sort((a, b) => {
            // We know timestamp is valid here due to the check above
            return (a.timestamp as number) - (b.timestamp as number);
          });

          return {
            ...prev,
            chartData: mergedData,
          };
        });
      }
    } catch (error) {
      console.error('[StockHeaderCard] Failed to load more data:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [symbol, timeframe, isLoadingMore]);

  // WebSocket integration
  useEffect(() => {
    if (!symbol) return;

    const unsubscribeConnection = priceWebSocketClient.onConnectionChange(() => {
      // Connection status changed
    });

    const unsubscribePrice = priceWebSocketClient.onPriceUpdate((update: RealTimePriceUpdate) => {
      if (update.ticker === symbol) {
        setStockData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            price: update.price,
            change: update.change,
            changePercent: update.changePercent,
          };
        });
      }
    });

    priceWebSocketClient.connect();
    priceWebSocketClient.subscribe([symbol]);

    return () => {
      priceWebSocketClient.unsubscribe([symbol]);
      unsubscribeConnection();
      unsubscribePrice();
    };
  }, [symbol]);

  // Use stock data from API (fallback to symbol if not available)
  const displayName = stockData?.name ?? symbol;
  const displaySymbol = `${symbol}.TW`;
  const displayPrice = stockData?.price ?? 0;
  const displayChange = stockData?.change ?? 0;
  const displayChangePercent = stockData?.changePercent ?? 0;
  const isPositive = displayChange >= 0;

  const chartData = useMemo(() => {
    // If we have API chart data, use it
    if (stockData?.chartData && stockData.chartData.length > 0) {
      // Helper to safely get timestamp (same logic as above)
      const getSafeTimestamp = (p: any): number | null => {
        if (typeof p.timestamp === 'number' && !isNaN(p.timestamp)) {
          return p.timestamp;
        }
        if (p.date) {
          const t = new Date(p.date).getTime();
          if (!isNaN(t)) return t;
        }
        return null;
      };

      // Filter and map to ensure valid timestamps
      const validData = stockData.chartData
        .reduce((acc: any[], point) => {
          const ts = getSafeTimestamp(point);
          if (ts !== null) {
            acc.push({ ...point, timestamp: ts });
          }
          return acc;
        }, [])
        .sort((a: any, b: any) => a.timestamp - b.timestamp);

      return validData;
    }
    // Fallback to mock data
    return generateMockPriceSeries(100, displayPrice || 100);
  }, [stockData?.chartData, displayPrice]);

  // Mock key statistics (replace with real data when available)
  const keyStats = {
    open: displayPrice * 0.98,
    high: displayPrice * 1.02,
    low: displayPrice * 0.96,
    marketCap: stockData?.marketCap || 0,
    peRatio: 15.4,
    volume: stockData?.stats?.volume || 0,
  };

  return (
    <div className="mx-4 sm:mx-8 mt-8">
      {/* Header Section - Full Width */}
      <div className="mb-6">
        {/* Top Row: Name/Symbol + Action Buttons */}
        <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4 mb-6">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-slate-50">{displayName}</h1>
            <span className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-3 py-1 rounded font-financial text-sm">
              {displaySymbol}
            </span>
          </div>

          {/* Action Buttons - Secondary Style */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={async () => {
                await toggleWatchlist(symbol);
              }}
              className={`gap-2 px-4 py-2 text-sm border-slate-300 dark:border-slate-700 ${isWatchlisted
                ? 'text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
            >
              <Star size={16} className={isWatchlisted ? "fill-current" : ""} />
              {isWatchlisted ? "已加入" : "加入自選"}
            </Button>
            <Button
              variant="outline"
              onClick={() => toggleAlert(symbol)}
              className={`gap-2 px-4 py-2 text-sm border-slate-300 dark:border-slate-700 ${isAlertSet
                ? 'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-500/10'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
            >
              <Bell size={16} className={isAlertSet ? "fill-current" : ""} />
              {isAlertSet ? "已開啟" : "設定警示"}
            </Button>
          </div>
        </div>

        {/* Price Section - HUGE */}
        <div className="mb-2">
          <span className={`text-5xl sm:text-6xl font-bold font-financial ${isPositive ? 'text-red-500 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
            {isLoading ? '...' : displayPrice.toLocaleString()}
          </span>
        </div>

        {/* Change Badge */}
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1 text-base font-bold px-3 py-1.5 rounded-md ${isPositive
            ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400'
            : 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400'
            }`}>
            {isPositive ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
            {isPositive ? '+' : ''}{displayChange.toLocaleString()} ({displayChangePercent.toFixed(2)}%)
          </span>
          <span className="text-slate-500 dark:text-slate-400 text-sm">即時行情 • 延遲 15 分鐘</span>
        </div>
      </div>

      {/* Split Grid: Chart + Stats Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Left Column: Chart (Span 2) */}
        <div className="lg:col-span-2">
          <ChartControls
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            subChart={subChart}
            onSubChartChange={setSubChart}
            activeIndicators={activeIndicators}
            onToggleIndicator={(ind, active) => {
              setActiveIndicators(prev => active ? [...prev, ind] : prev.filter(i => i !== ind));
            }}
          />
          <div className="h-[400px] w-full">
            <TradingViewChart
              data={chartData}
              theme={theme === 'dark' ? 'dark' : 'light'}
              lineColor={isPositive ? '#22c55e' : '#ef4444'}
              topColor={isPositive ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}
              bottomColor="transparent"
              height={400}
              className="w-full"
              activeIndicators={activeIndicators}
              activeSubChart={subChart}
              onLoadMore={handleLoadMore}
              isLoadingMore={isLoadingMore}

            />
          </div>
        </div>

        {/* Right Column: Key Statistics Sidebar (Span 1) */}
        <div className="lg:col-span-1">
          <div className="glass-card rounded-lg p-4 h-full flex flex-col justify-between">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-50 mb-4">關鍵數據</h3>
            <div className="space-y-4 flex-1 flex flex-col justify-center">
              <div className="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-800">
                <span className="text-sm text-slate-500 dark:text-slate-400">開盤</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{keyStats.open.toLocaleString()}</span>
              </div>
              <div className="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-800">
                <span className="text-sm text-slate-500 dark:text-slate-400">最高</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{keyStats.high.toLocaleString()}</span>
              </div>
              <div className="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-800">
                <span className="text-sm text-slate-500 dark:text-slate-400">最低</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{keyStats.low.toLocaleString()}</span>
              </div>
              <div className="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-800">
                <span className="text-sm text-slate-500 dark:text-slate-400">成交量</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{(keyStats.volume / 1000).toFixed(1)}K</span>
              </div>
              <div className="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-800">
                <span className="text-sm text-slate-500 dark:text-slate-400">市值</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{(keyStats.marketCap / 1000000000).toFixed(2)}B</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-500 dark:text-slate-400">本益比</span>
                <span className="text-lg font-medium font-financial text-slate-900 dark:text-slate-50">{keyStats.peRatio}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const StockDashboard: React.FC = () => {
  const { ticker } = useParams();
  const symbol = (ticker ?? '3017').toUpperCase();
  const [relatedEpisodes, setRelatedEpisodes] = useState<MockEpisode[]>([]);
  const [recommendations, setRecommendations] = useState<TickerRecommendation[]>([]);
  const [episodesLoading, setEpisodesLoading] = useState(true);

  // Fetch recommendations from API
  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    (async () => {
      try {
        const recs = await recommendationService.getRecommendationsByTicker(symbol);
        if (!cancelled) setRecommendations(recs);
      } catch (e) {
        if (!cancelled) setRecommendations([]);
      }
    })();
    return () => { cancelled = true; };
  }, [symbol]);

  // Fetch related episodes from API
  useEffect(() => {
    const fetchEpisodes = async () => {
      setEpisodesLoading(true);
      try {
        const apiEpisodes = await fetchWithFallback(
          () => getEpisodesByTicker(symbol, { limit: 50, sortBy: 'spotify_release_date', order: 'desc', includeContent: false }),
          [],
          `getEpisodesByTicker(${symbol})`
        );

        // Transform API episodes to mock format, filtering out those without summary
        const transformedEpisodes = apiEpisodes
          .map(transformApiEpisodeToMock)
          .filter((ep): ep is MockEpisode => ep !== null);

        // Sort by spotify_release_date (descending - newest first)
        // Since API might not sort correctly, we sort client-side as well
        transformedEpisodes.sort((a, b) => {
          // Find original API episodes to get release dates
          const apiA = apiEpisodes.find(ep => ep.id === a.id);
          const apiB = apiEpisodes.find(ep => ep.id === b.id);

          if (!apiA || !apiB) return 0;

          // Get release dates (prefer spotify_release_date, fallback to created_time)
          const dateA = apiA.spotify_release_date || apiA.created_time;
          const dateB = apiB.spotify_release_date || apiB.created_time;

          // Convert to timestamps for comparison
          const timeA = typeof dateA === 'string' ? new Date(dateA).getTime() : dateA;
          const timeB = typeof dateB === 'string' ? new Date(dateB).getTime() : dateB;

          // Descending order (newest first)
          return timeB - timeA;
        });

        setRelatedEpisodes(transformedEpisodes);
      } catch (error) {
        console.error('[StockDashboard] Failed to fetch episodes:', error);
        setRelatedEpisodes([]);
      } finally {
        setEpisodesLoading(false);
      }
    };

    if (symbol) {
      fetchEpisodes();
    }
  }, [symbol]);

  const name = stockData?.name || symbol;

  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    'name': name,
    'tickerSymbol': symbol,
    'url': window.location.href
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-transparent">
      <SEO
        title={`${name} (${symbol}) - 股價表現與相關 Podcast | TinBoker`}
        description={`查看 ${name} (${symbol}) 的即時股價走勢，以及最新提到此標的的 Podcast 節目與分析。`}
        structuredData={structuredData}
        url={window.location.href}
      />
      <Header />

      <main className="flex-1 overflow-y-auto pb-12">
        <div className="max-w-7xl mx-auto">
          {/* Stock Header Card */}
          <StockHeaderCard symbol={symbol} />



          {/* Analyst Insights Section */}
          <section className="px-4 sm:px-8 py-8 border-t border-slate-200 dark:border-slate-800" aria-label="Analyst Insights">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50 mb-6">
              分析師觀點 & 投資摘要
            </h2>

            {recommendations.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {recommendations.map(rec => (
                  <TickerInsightCard key={rec.id} recommendation={rec} episodes={relatedEpisodes} />
                ))}
              </div>
            ) : (
              <div className="text-center py-8 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                <p className="text-slate-500">此標的暫無詳細分析觀點。</p>
              </div>
            )}
          </section>

          {/* Related Episodes Section */}
          <section className="px-4 sm:px-8 py-8 border-t border-slate-200 dark:border-slate-800" aria-label="Related Episodes">
            <div className="flex items-center justify-between mb-6 pt-4">
              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-50 mb-1">
                  相關 Podcast 集數
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  提及 {name} 的節目與分析
                </p>
              </div>
              <span className="text-sm text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-full font-medium">
                {relatedEpisodes.length} 集
              </span>
            </div>

            {episodesLoading ? (
              <div className="flex items-center justify-center py-12">
                <p className="text-slate-500 dark:text-slate-400">載入中...</p>
              </div>
            ) : relatedEpisodes.length > 0 ? (
              <div className="space-y-6">
                {relatedEpisodes.map(episode => (
                  <EpisodeCard key={episode.id} episode={episode} />
                ))}
              </div>
            ) : (
              <Card className="border-slate-200 dark:border-slate-800 glass-card text-center py-12">
                <CardContent>
                  <p className="text-slate-500">目前沒有 Podcast 提到此標的。</p>
                </CardContent>
              </Card>
            )}
          </section>
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default StockDashboard;
