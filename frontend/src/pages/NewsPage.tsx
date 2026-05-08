import React, { useEffect, useMemo, useState, useRef } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, Clock, Share2, Bookmark, TrendingUp, Activity, Play, ExternalLink, Link as LinkIcon, Facebook, MessageCircle, AtSign, Check, RotateCw } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { useAppStore } from '@/store/useAppStore';
import { usePlayerStore } from '@/store/usePlayerStore';
import { userApi } from '@/services/api/user';
import { INTERACTIVE_MODELS } from '@/data/interactiveModels';
import type { InteractiveEntity } from '@/data/interactiveModels';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { generateMockPriceSeries } from '@/services/mocks';
import { StockLogo } from '@/components/common/StockLogo';
import { fetchWithFallback, getStockByTicker, getEpisodeById, getRecentEpisodes, updateEpisodeSummary, deleteEpisodeSummary } from '@/services';
import { getTranslation } from '@/services/api/translations';
import { regenerateEpisodeSummary } from '@/services/api';
import type { Episode as ApiEpisode } from '@/services/api';
import ForceGraph from '@/components/graph/visuals/ForceGraph';
import ReactMarkdown from 'react-markdown';
import { StockHoverCard } from '@/components/stock/StockHoverCard';
import { DonationCard } from '@/components/ui/DonationCard';
import { Skeleton } from '@/components/ui';
import { SEO } from '@/components/common/SEO';
import { Breadcrumbs } from '@/components/common/Breadcrumbs';
import { replaceTimeCodesWithLinks, replaceTimeCodesWithLinksAndNewline } from '@/utils/timeFormat';
import { parseTimestampedSections } from '@/utils/parseTimestampedSections';
import { SlideViewer } from '@/components/common/SlideViewer';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';


/*
const MiniChart = ({ isPositive, isDark }: { isPositive: boolean, isDark: boolean }) => {
    const series = useMemo(() => generateMockPriceSeries(20, isPositive ? 120 : 90), [isPositive]);
    return (
        <div className="w-16 h-8">
            <TradingViewChart
                data={series}
                theme={isDark ? 'dark' : 'light'}
                height={32}
                lineColor={isPositive ? '#22c55e' : '#ef4444'}
                topColor={isPositive ? 'rgba(34,197,94,0.35)' : 'rgba(239,68,68,0.35)'}
                bottomColor="transparent"
                minimal
                className="h-full w-full"
            />
        </div>
    );
};
*/

interface RelatedAssetCardProps {
  ticker: InteractiveEntity;
  isDark: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  badgeText?: string;
  insightText?: string;
}

const NewsPageSkeleton = ({ isDark }: { isDark: boolean }) => (
  <div className={`min-h-screen flex flex-col ${isDark ? 'bg-transparent' : 'bg-white'}`}>
    <Header />
    <div className="flex-1 max-w-7xl mx-auto px-6 py-8 w-full">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
        {/* Left Column */}
        <div className="lg:col-span-9">
          {/* Breadcrumbs */}
          <Skeleton className="h-4 w-48 mb-4" />
          {/* Title */}
          <Skeleton className="h-10 w-3/4 mb-4" />
          {/* Meta */}
          <div className="flex gap-4 mb-6">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-32" />
          </div>
          {/* Spotify Player */}
          <Skeleton className="h-[152px] w-full rounded-xl mb-6" />
          {/* Tabs */}
          <div className="flex gap-4 mb-6 border-b pb-2 border-slate-200 dark:border-slate-800">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-8 w-16" />
          </div>
          {/* Content */}
          <div className="space-y-4">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
          </div>
        </div>
        {/* Right Column - Narrower */}
        <div className="lg:col-span-3 space-y-6">
          <div className="space-y-2">
            <Skeleton className="h-6 w-24 mb-2" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        </div>
      </div>
    </div>
    <Footer />
  </div>
);

const RelatedAssetCardSkeleton: React.FC<{ isDark: boolean }> = ({ isDark }) => (
  <div
    className={`w-full rounded-lg p-3 ${
      isDark
        ? 'border-t border-white/15 border-b border-black/20 border-x border-white/5 bg-gradient-to-br from-slate-800/60 to-slate-900/60 backdrop-blur-md'
        : 'bg-white border border-slate-200 shadow-sm'
    }`}
  >
    <div className="flex items-center justify-between gap-3">
      {/* Left: Logo + Ticker/Name */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <Skeleton className="h-10 w-10 rounded-md shrink-0" />
        <div className="min-w-0 flex-1">
          <Skeleton className="h-4 w-16 mb-1" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
      {/* Right: Chart + Price */}
      <div className="flex items-center gap-2">
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-5 w-12" />
      </div>
    </div>
  </div>
);

const RelatedAssetCard: React.FC<RelatedAssetCardProps> = ({ ticker, isDark, isExpanded, onToggle, badgeText, insightText }) => {
  const navigate = useNavigate();
  const trendColor = useStockTrendColor(ticker.isPositive ? 1 : -1);
  const expandedSeries = useMemo(
    () => generateMockPriceSeries(40, ticker.isPositive ? 140 : 95),
    [ticker.isPositive]
  );
  const containerBase = isDark
    ? 'border-t border-white/15 border-b border-black/20 border-x border-white/5 bg-gradient-to-br from-slate-800/60 to-slate-900/60 backdrop-blur-md hover:border-white/20 hover:bg-slate-800/80 hover:shadow-lg hover:shadow-amber-900/10'
    : 'bg-white border border-slate-200 shadow-sm hover:shadow-md hover:bg-slate-50';
  const ringClass = isExpanded ? (isDark ? 'ring-1 ring-slate-500 bg-slate-800/80' : 'ring-2 ring-indigo-500/20') : '';
  const badgeClass = trendColor.badge;
  const panelClass = 'glass-panel';
  const badgeLabel = badgeText ?? (ticker.isPositive ? '多頭型態' : '空頭訊號');
  const insightCopy =
    insightText ??
    (ticker.isPositive
      ? '過去一週持續創新高，動能持續累積。'
      : '價格測試短期支撐，賣壓仍存。');

  return (
    <div
      onClick={onToggle}
      role="button"
      tabIndex={0}
      aria-expanded={isExpanded}
      className={`w-full text-left rounded-lg p-3 transition-all duration-300 cursor-pointer group ${containerBase} ${ringClass} focus:outline-none focus:ring-2 focus:ring-indigo-500`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <div className="flex items-center justify-between gap-3 pointer-events-none">
        {/* Left: Logo + Ticker/Name */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {/* Stock Logo */}
          <StockLogo symbol={ticker.symbol} size="sm" />

          {/* Ticker & Name Column */}
          <div
            className="pointer-events-auto cursor-pointer hover:opacity-80 transition-opacity min-w-0 flex-1"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/stock/${ticker.symbol}`);
            }}
          >
            <div className={`font-bold text-sm leading-tight ${isDark ? 'text-slate-200' : 'text-slate-900'} group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors truncate`}>
              {ticker.symbol.split('.')[0]}
            </div>
            <div className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} truncate`}>
              {ticker.name || ticker.symbol}
            </div>
          </div>
        </div>

        {/* Middle: Sparkline Chart - color follows user settings */}
        {!isExpanded && (
          <div className="h-6 w-16 flex items-center flex-shrink-0">
            <TradingViewChart
              data={expandedSeries}
              theme={isDark ? 'dark' : 'light'}
              height={24}
              lineColor={trendColor.lineColor}
              topColor={trendColor.topColor}
              bottomColor="transparent"
              minimal
              className="h-full w-full"
            />
          </div>
        )}

        {/* Right: Price & Change Column - color follows user settings */}
        <div className="text-right flex-shrink-0">
          <div className={`font-bold font-financial text-sm ${isDark ? 'text-slate-50' : 'text-slate-900'} leading-tight`}>
            {ticker.price}
          </div>
          <div className={`text-[10px] font-bold font-financial ${trendColor.text}`}>
            {ticker.isPositive ? '+' : ''}{ticker.change}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-3 cursor-default" onClick={(e) => e.stopPropagation()}>
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-[11px] font-semibold ${badgeClass}`}>
            {badgeLabel}
          </span>
          <div className={`h-28 rounded-xl border overflow-hidden ${panelClass}`}>
            <TradingViewChart
              data={expandedSeries}
              theme={isDark ? 'dark' : 'light'}
              height={112}
              lineColor={trendColor.lineColor}
              topColor={trendColor.topColor}
              bottomColor="transparent"
              minimal
              className="h-full w-full"
            />
          </div>
          <p className={`text-xs leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{insightCopy}</p>
        </div>
      )}
    </div>
  );
};

/*
interface ContentAssetState {
    ticker: string;
    svgUrl: string;
    articleUrl: string;
    ttlSeconds: number;
}
*/

export const NewsPage: React.FC = () => {
  const { theme, token, toggleEpisodeBookmark } = useAppStore();
  const { playEpisode } = usePlayerStore();
  const isDark = theme === 'dark';
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const [expandedAsset, setExpandedAsset] = useState<string | null>(null);
  const [expandedMacroAsset, setExpandedMacroAsset] = useState<string | null>(null);
  const [apiEpisode, setApiEpisode] = useState<ApiEpisode | null>(null);
  const [enrichedTickers, setEnrichedTickers] = useState<InteractiveEntity[]>([]);
  const [isLoadingTickers, setIsLoadingTickers] = useState(false);

  const [isLoading, setIsLoading] = useState(true);
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [activeContentTab, setActiveContentTab] = useState<'summary' | 'events' | 'sentences' | 'edit' | 'recommendations'>('summary');
  const [fontSizeLevel, setFontSizeLevel] = useState<0 | 1 | 2 | 3 | 4>(2);

  // Edit mode state
  const [editedContent, setEditedContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  
  // Recommendations data state
  const [recommendationsData, setRecommendationsData] = useState<any>(null);
  
  // Re-generate episode state
  const [isRegenerating, setIsRegenerating] = useState(false);

  // Share Menu state
  const [isShareMenuOpen, setIsShareMenuOpen] = useState(false);
  const shareMenuRef = useRef<HTMLDivElement>(null);

  // Close share menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (shareMenuRef.current && !shareMenuRef.current.contains(event.target as Node)) {
        setIsShareMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (activeModelId) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [activeModelId]);

  /*
  useEffect(() => {
    if (contentTickers.length > 0) {
      return;
    }

    const loadContentIndex = async () => {
      try {
        const index = await fetchWithFallback(
          () => getContentIndex(),
          { tickers: [] },
          'getContentIndex'
        );
        setContentTickers(index.tickers);
        if (index.tickers.length > 0) {
          const initialTicker =
            (id && index.tickers.find((ticker) => ticker.toLowerCase() === id.toLowerCase())) || index.tickers[0];
          setSelectedContentTicker(initialTicker);
        }
      } catch (error) {
        console.warn('Failed to load content index:', error);
        setContentError('Unable to load available content tickers.');
      }
    };

    loadContentIndex();
  }, [contentTickers.length, id]);

  useEffect(() => {
    if (contentTickers.length === 0) {
      return;
    }

    const desiredTicker =
      (id && contentTickers.find((ticker) => ticker.toLowerCase() === id.toLowerCase())) || contentTickers[0];

    if (desiredTicker !== selectedContentTicker) {
      setSelectedContentTicker(desiredTicker);
    }
  }, [contentTickers, id, selectedContentTicker]);

  useEffect(() => {
    if (!selectedContentTicker) {
      return;
    }

    let isCancelled = false;
    const loadContentAsset = async () => {
      setContentLoading(true);
      setContentError(null);
      try {
        const asset = await fetchWithFallback(
          () => getContentByTicker(selectedContentTicker),
          {
            ticker: selectedContentTicker,
            svg_url: '',
            article_url: '',
            ttl_seconds: 0,
          },
          `getContentByTicker(${selectedContentTicker})`
        );

        if (isCancelled) {
          return;
        }

        if (!asset.svg_url || !asset.article_url) {
          throw new Error('Missing content asset URLs');
        }

        const articleResponse = await fetch(asset.article_url);
        if (!articleResponse.ok) {
          throw new Error(`Failed to fetch article content (${articleResponse.status})`);
        }
        const markdown = await articleResponse.text();

        if (isCancelled) {
          return;
        }

        setContentAsset({
          ticker: asset.ticker,
          svgUrl: asset.svg_url,
          articleUrl: asset.article_url,
          ttlSeconds: asset.ttl_seconds,
        });
        setContentMarkdown(markdown);
        setContentFetchedAt(Date.now());
      } catch (error) {
        if (!isCancelled) {
          setContentAsset(null);
          setContentMarkdown('');
          setContentError('Unable to load content for this ticker.');
        }
      } finally {
        if (!isCancelled) {
          setContentLoading(false);
        }
      }
    };

    loadContentAsset();

    return () => {
      isCancelled = true;
    };
  }, [selectedContentTicker, contentReloadKey]);
  */

  // Get podcast name from query params
  const podcastName = searchParams.get('podcast');

  // Try to extract podcast name from episode ID if format is {podcast}_{episodeId}
  // This handles cases where podcast query param is missing or empty
  const extractPodcastFromId = (episodeId: string | undefined): string | null => {
    if (!episodeId) return null;
    // Check if ID contains underscore (format: {podcast}_{episodeId})
    const parts = episodeId.split('_');
    if (parts.length >= 2) {
      // Return the first part as potential podcast name
      // Note: This assumes the format, may need adjustment based on actual ID structure
      return parts[0];
    }
    return null;
  };

  // Use podcast name from query param, or try to extract from ID, or null
  const effectivePodcastName = podcastName || extractPodcastFromId(id || undefined);

  // Fetch episode data from podcast API if podcast name is available
  useEffect(() => {
    if (!id) return;

    const fetchEpisodeData = async () => {
      setIsLoading(true);
      try {
        let episode: ApiEpisode | null = null;

        // Strategy 1: If we have podcast name, use direct API call
        if (effectivePodcastName) {
          // If podcast name was extracted from ID, we need to handle the episode ID differently
          // The actual episode ID might be the part after the underscore
          const actualEpisodeId = id.includes('_') && !podcastName ? id.split('_').slice(1).join('_') : id;

          try {
            episode = await fetchWithFallback(
              () => getEpisodeById(effectivePodcastName, actualEpisodeId),
              null,
              `getEpisodeById(${effectivePodcastName}, ${actualEpisodeId})`
            );
          } catch (error) {
            console.warn('[NewsPage] Failed to fetch episode with extracted podcast name, trying fallback:', error);
            // If that fails, try with the full ID
            if (id !== actualEpisodeId) {
              try {
                episode = await fetchWithFallback(
                  () => getEpisodeById(effectivePodcastName, id),
                  null,
                  `getEpisodeById(${effectivePodcastName}, ${id})`
                );
              } catch (error2) {
                console.warn('[NewsPage] Failed to fetch episode with full ID:', error2);
              }
            }
          }
        }

        // Strategy 2: If we still don't have episode, search recent episodes by ID
        if (!episode) {
          try {
            const recentEpisodes = await getRecentEpisodes({ limit: 200 });
            episode = recentEpisodes.find(ep => ep.id === id) || null;

            if (episode && import.meta.env.DEV) {
              console.log('[NewsPage] Found episode in recent episodes:', {
                id: episode.id,
                podcast_name: episode.podcast_name
              });
            }
          } catch (error) {
            console.warn('[NewsPage] Failed to search recent episodes:', error);
          }
        }

        // Debug: Check if tab content fields are present
        if (import.meta.env.DEV && episode) {
          console.log('[NewsPage] Episode API response:', {
            id: episode.id,
            podcast_name: episode.podcast_name,
            hasEventsContent: !!episode.events_markdown_content,
            hasSentencesContent: !!episode.sentences_markdown_content,
            eventsContentLength: episode.events_markdown_content?.length || 0,
            sentencesContentLength: episode.sentences_markdown_content?.length || 0,
            eventsContentPreview: episode.events_markdown_content?.substring(0, 100),
            sentencesContentPreview: episode.sentences_markdown_content?.substring(0, 100),
            allFields: Object.keys(episode)
          });
        }

        setApiEpisode(episode);
      } catch (error) {
        console.error('Failed to fetch episode data:', error);
        setApiEpisode(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchEpisodeData();
  }, [id, effectivePodcastName, podcastName]);

  // Check bookmark status when episode loads
  useEffect(() => {
    const checkBookmarkStatus = async () => {
      if (!token || !id || !effectivePodcastName) {
        setIsBookmarked(false);
        return;
      }

      try {
        const bookmarks = await userApi.getEpisodeBookmarks();
        const formattedEpisodeId = `${effectivePodcastName}_${id}`;
        setIsBookmarked(bookmarks.includes(formattedEpisodeId));
      } catch (error) {
        console.error('Failed to check bookmark status:', error);
        setIsBookmarked(false);
      }
    };

    checkBookmarkStatus();
  }, [token, id, effectivePodcastName]);

  const handleBookmarkClick = async () => {
    if (!token || !id || !effectivePodcastName) {
      // Show login prompt or navigate to login
      return;
    }

    setBookmarkLoading(true);
    try {
      const actualEpisodeId = id.includes('_') && !podcastName ? id.split('_').slice(1).join('_') : id;
      await toggleEpisodeBookmark(effectivePodcastName, actualEpisodeId);
      setIsBookmarked(!isBookmarked);
    } catch (error) {
      console.error('Failed to toggle bookmark:', error);
    } finally {
      setBookmarkLoading(false);
    }
  };

  // Determine Article Source: Interactive Models OR Mock Episodes
  // Interactive Models are deprecated/disabled for now
  const staticArticle = null; // INTERACTIVE_MODELS[id || ''] || null;
  const mockEpisode = null;

  // Enrich tickers with real stock data
  useEffect(() => {
    // Collect all tickers to enrich (from API episode, API model, or Mock Episode)
    let tickersToEnrich: InteractiveEntity[] = [];

    if (apiEpisode) {
      if (apiEpisode.related_tickers && apiEpisode.related_tickers.length > 0) {
        apiEpisode.related_tickers.forEach(symbol => {
          tickersToEnrich.push({
            symbol: symbol,
            name: symbol, // Start with symbol as name, will be updated by enrichment
            price: '0.00',
            change: '0.0%',
            isPositive: true
          });
        });
      }
    } else if (mockEpisode) {
      // Extract stock symbols from highlights
      const stocks: InteractiveEntity[] = [];
      mockEpisode.summary.forEach(point => {
        if (point.highlights) {
          point.highlights.forEach(h => {
            if (h.type === 'stock' && h.symbol) {
              stocks.push({
                symbol: h.symbol,
                price: '0.00', // Placeholder
                change: '0.0%',
                isPositive: true
              });
            }
          });
        }
      });
      tickersToEnrich = stocks;
    }

    const enrichTickers = async () => {
      if (tickersToEnrich.length === 0) {
        setEnrichedTickers([]);
        setIsLoadingTickers(false);
        return;
      }

      setIsLoadingTickers(true);
      const tickerPromises = tickersToEnrich.map(async (ticker: InteractiveEntity) => {
        try {
          const stock = await fetchWithFallback(
            () => getStockByTicker(ticker.symbol, undefined, { silent: true }),
            null,
            `getStockByTicker(${ticker.symbol})`
          );
          // Skip if stock data not found (e.g., indexes like IXIC, SPX, SOX)
          if (!stock || stock.price === 0) {
            return null; // Will be filtered out
          }
          // Try to fetch translation (ZH-TW name)
          let translatedName: string | null = null;
          try {
            const market = ticker.symbol.includes('.TW') ? 'TW' : 'US';
            const cleanTicker = ticker.symbol.replace('.TW', '');
            // Pass the English name from stock API for auto-creation context
            const translation = await getTranslation(cleanTicker, market, stock?.name);
            if (translation?.name_zh_tw) {
              // Use only Chinese name, not "TICKER 中文名"
              translatedName = translation.name_zh_tw;
            }
          } catch {
            // Translation fetch failed, use default
          }
          return {
            symbol: ticker.symbol,
            // Priority: Chinese translation > English name from API > ticker name
            name: translatedName || stock.name || ticker.name,
            price: stock.price.toFixed(2),
            change: `${stock.changePercent >= 0 ? '+' : ''}${stock.changePercent.toFixed(2)}%`,
            isPositive: stock.changePercent >= 0,
          };
        } catch (error) {
          console.warn(`Failed to fetch stock data for ${ticker.symbol}:`, error);
          // Return null for failed fetches - will be filtered out
          return null;
        }
      });

      const enriched = await Promise.all(tickerPromises);
      // Deduplicate by symbol
      const uniqueEnriched = Array.from(new Map(enriched.filter(Boolean).map(item => [item!.symbol, item])).values());

      setEnrichedTickers(uniqueEnriched as InteractiveEntity[]);
      setIsLoadingTickers(false);
    };

    enrichTickers();
  }, [apiEpisode, mockEpisode]);



  // Construct Final Article Object
  let article: any = null;

  // Priority 1: API Episode data (from podcast API)
  if (apiEpisode) {
    // Convert summary_content to markdown format and replace time codes with newlines after each time tag
    const summaryMarkdown = replaceTimeCodesWithLinksAndNewline(apiEpisode.summary_content || '');

    // Apply time code replacement to modified summary as well
    const modifiedSummaryMarkdown = apiEpisode.modified_summary_content
      ? replaceTimeCodesWithLinksAndNewline(apiEpisode.modified_summary_content)
      : null;

    // Apply time code replacement to events and sentences content as well
    const eventsMarkdown = apiEpisode.events_markdown_content
      ? replaceTimeCodesWithLinks(apiEpisode.events_markdown_content)
      : null;
    const sentencesMarkdown = apiEpisode.sentences_markdown_content
      ? replaceTimeCodesWithLinks(apiEpisode.sentences_markdown_content)
      : null;

    // Calculate time ago from spotify_release_date (fallback to created_time)
    const now = Date.now();
    const releaseDate = apiEpisode.spotify_release_date || apiEpisode.created_time;
    // Handle both string (ISO date) and number (timestamp) formats
    const releaseTime = typeof releaseDate === 'string'
      ? new Date(releaseDate).getTime()
      : releaseDate;
    const diffMs = now - releaseTime;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    let timeAgo = '';
    if (diffDays > 0) {
      timeAgo = `${diffDays}天前`;
    } else if (diffHours > 0) {
      timeAgo = `${diffHours}小時前`;
    } else {
      timeAgo = '剛剛';
    }

    article = {
      id: apiEpisode.id,
      title: apiEpisode.episode_title || `EP${apiEpisode.episode_number || ''}`,
      source: apiEpisode.podcast_name,
      date: timeAgo,
      category: apiEpisode.tags?.[0] || 'Podcast',
      tags: apiEpisode.tags || [],
      summary: '詳細內容請見下方摘要',
      graphTypeLabel: '關聯圖譜',
      GraphComponent: ForceGraph,
      tickers: enrichedTickers,
      indices: [],
      content: summaryMarkdown,
      modifiedContent: modifiedSummaryMarkdown,
      eventsContent: eventsMarkdown,
      sentencesContent: sentencesMarkdown
    };

  } else if (mockEpisode) {
    // Generate Markdown Content for Mock Episode
    // Convert structured summary to markdown text with ticker links
    const summaryMarkdown = mockEpisode.summary.map(point => {
      let text = point.text;
      if (point.highlights) {
        // Sort highlights by length desc to avoid partial replacements of substrings
        const sortedHighlights = [...point.highlights].sort((a, b) => b.text.length - a.text.length);

        sortedHighlights.forEach(h => {
          if (h.type === 'stock' && h.symbol) {
            // Replace text with markdown link: [Text](#ticker:SYMBOL)
            // Escape special regex chars in text if needed
            const escapedText = h.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            text = text.replace(new RegExp(escapedText, 'g'), `[${h.text}](#ticker:${h.symbol})`);
          }
        });
      }
      return `* ${text}`;
    }).join('\n\n');

    article = {
      id: mockEpisode.id,
      title: mockEpisode.title,
      source: mockEpisode.showName,
      date: mockEpisode.timeAgo,
      category: mockEpisode.tags[0] || 'Podcast',
      tags: mockEpisode.tags || [],
      summary: '詳細內容請見下方摘要',
      graphTypeLabel: '關聯圖譜',
      GraphComponent: ForceGraph, // Use a default graph for episodes
      tickers: enrichedTickers, // Populated from highlights
      indices: [],
      content: summaryMarkdown // Use the generated markdown string
    };
  }

  // Generate Structured Data (must be called on every render to keep hook order stable)
  const structuredData = useMemo(() => {
    if (!article) return undefined;

    const isPodcast = article.category === 'Podcast';

    if (isPodcast) {
      return {
        '@context': 'https://schema.org',
        '@type': 'PodcastEpisode',
        'name': article.title,
        'description': typeof article.summary === 'string' ? article.summary : undefined,
        'partOfSeries': {
          '@type': 'PodcastSeries',
          'name': article.source
        },
        'datePublished': new Date().toISOString().split('T')[0],
        'url': window.location.href
      };
    }

    return {
      '@context': 'https://schema.org',
      '@type': 'NewsArticle',
      'headline': article.title,
      'author': [{
        '@type': 'Organization',
        'name': article.source
      }],
      'description': typeof article.summary === 'string' ? article.summary : undefined,
      'datePublished': new Date().toISOString().split('T')[0]
    };
  }, [article]);

  useEffect(() => {
    setExpandedAsset(null);
    setExpandedMacroAsset(null);
    // Reset content tab to summary when episode ID changes
    setActiveContentTab('summary');
  }, [id]);

  // Initialize edited content when switching to edit tab
  useEffect(() => {
    if (activeContentTab === 'edit' && apiEpisode) {
      // Initialize with modified content if exists, else original
      setEditedContent(
        apiEpisode.modified_summary_content || apiEpisode.summary_content || ''
      );
    }
  }, [activeContentTab, apiEpisode]);

  // Parse recommendations JSON when episode loads
  useEffect(() => {
    if (apiEpisode?.ticker_recommendations_content) {
      try {
        const parsed = JSON.parse(apiEpisode.ticker_recommendations_content);
        if (import.meta.env.DEV) {
          console.log('[NewsPage] Successfully parsed ticker recommendations:', parsed);
        }
        setRecommendationsData(parsed);
      } catch (error) {
        console.error('[NewsPage] Failed to parse ticker recommendations:', error);
        console.error('[NewsPage] Raw content:', apiEpisode.ticker_recommendations_content?.substring(0, 200));
        setRecommendationsData(null);
      }
    } else {
      if (import.meta.env.DEV && apiEpisode) {
        console.log('[NewsPage] No ticker_recommendations_content in episode:', {
          hasUrl: !!apiEpisode.ticker_recommendations_public_url,
          url: apiEpisode.ticker_recommendations_public_url
        });
      }
      setRecommendationsData(null);
    }
  }, [apiEpisode]);

  // Extract Spotify URI from episode data if available
  // Priority: apiEpisode.spotify_url/spotify_id > mockEpisode.spotifyUri > default example URI
  const hasEpisode = !!(apiEpisode || mockEpisode);

  // Helper function to convert Spotify URL to URI format
  const getSpotifyUri = (): string | null => {
    if (!hasEpisode) return null;

    // Try API episode spotify_id first (most direct)
    if (apiEpisode?.spotify_id) {
      return `spotify:episode:${apiEpisode.spotify_id}`;
    }

    // Try API episode spotify_url and convert to URI
    if (apiEpisode?.spotify_url) {
      // Extract episode ID from URL like https://open.spotify.com/episode/7makk4oTQel546B0PZlDM5
      const match = apiEpisode.spotify_url.match(/episode\/([a-zA-Z0-9]+)/);
      if (match && match[1]) {
        return `spotify:episode:${match[1]}`;
      }
      // If already in URI format, return as is
      if (apiEpisode.spotify_url.startsWith('spotify:episode:')) {
        return apiEpisode.spotify_url;
      }
    }

    // Try mock episode
    if ((mockEpisode as any)?.spotifyUri) {
      return (mockEpisode as any).spotifyUri;
    }

    // Fallback to example
    return 'spotify:episode:7makk4oTQel546B0PZlDM5';
  };

  const spotifyUri = getSpotifyUri();

  // Parse timestamped sections from summary content for player chapter list
  const timestampedSections = useMemo(() => {
    if (!apiEpisode) return [];
    // Use the raw content (before time code replacement) as it has the original format
    const rawContent = apiEpisode.modified_summary_content || apiEpisode.summary_content || '';
    return parseTimestampedSections(rawContent);
  }, [apiEpisode]);

  // Re-generate episode summarize function
  const handleRegenerateEpisode = async () => {
    if (!apiEpisode?.id || !effectivePodcastName || isRegenerating) return;
    
    setIsRegenerating(true);
    try {
      // Call backend endpoint (which handles everything)
      await regenerateEpisodeSummary(effectivePodcastName, apiEpisode.id);
      
      // Show success message
      alert('Regeneration started! The new summary will be available in a few minutes. You can refresh this page later to see the updated content.');
    } catch (error) {
      console.error('Failed to trigger regeneration:', error);
      alert(`Failed to start regeneration: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsRegenerating(false);
    }
  };

  // Extract unique tags from all content sources
  const allTags = useMemo(() => {
    if (!article) return [];



    const tags = new Set<string>();

    // Add existing metadata tags
    if (article.tags) {
      article.tags.forEach((t: string) => tags.add(t.replace(/^#/, '')));
    }

    return Array.from(tags);
  }, [article]);

  // Only show loading state if article is not found yet and we're within the timeout window
  if (!article && isLoading) {
    return <NewsPageSkeleton isDark={isDark} />;
  }

  if (!article) {
    return (
      <div className={`min-h-screen flex flex-col ${isDark ? 'bg-transparent' : 'bg-white'}`}>
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h2 className={`text-2xl font-bold mb-2 ${isDark ? 'text-slate-50' : 'text-slate-900'}`}>找不到文章</h2>
            <p className="text-slate-500 mb-4">您請求的新聞文章或 Podcast 不存在。</p>
            <Link
              to="/"
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 inline-block"
            >
              返回首頁
            </Link>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  // const Graph = article.GraphComponent;

  // Custom Markdown Components for ReactMarkdown
  const MarkdownComponents = {
    a: ({ href, children, ...props }: any) => {
      // Check if href is a ticker link (e.g. #ticker:2330)
      if (href && href.startsWith('#ticker:')) {
        const symbol = href.replace('#ticker:', '');
        return (
          <StockHoverCard
            symbol={symbol}
            onClick={() => navigate(`/stock/${symbol}`)}
            className="inline text-amber-600 dark:text-amber-400 font-medium cursor-pointer hover:underline transition-all"
          >
            {children}
          </StockHoverCard>
        );
      }
      // Check if href is a tag link (e.g. #tag:AI)
      if (href && href.startsWith('#tag:')) {
        const tag = href.replace('#tag:', '');
        return (
          <span
            onClick={() => navigate(`/tag/${encodeURIComponent(tag)}`)}
            className="inline mx-1 text-indigo-600 dark:text-indigo-300 font-medium cursor-pointer hover:underline transition-colors"
          >
            {children}
          </span>
        );
      }
      // Check if href is a time link (e.g. #time:65) - seek Global Player to timestamp
      if (href && href.startsWith('#time:')) {
        const seconds = parseInt(href.replace('#time:', ''), 10);
        return (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (article && (apiEpisode || mockEpisode)) {
                // Always use playEpisode with seekTo - this ensures consistent behavior
                // The SpotifyEmbed handles the play-then-seek internally
                const episodeData = {
                  id: article.id,
                  title: article.title,
                  showName: article.source,
                  coverUrl: undefined,
                  spotifyUri: spotifyUri || undefined,
                  timestampedSections: timestampedSections
                };
                playEpisode(episodeData, { seekTo: seconds });
              }
            }}
            className="inline-flex mx-1 ml-2 px-2.5 py-0.5 rounded-full border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 text-xs font-financial cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-50 transition-colors items-center gap-1 align-middle translate-y-[-3px]"
            title={`跳轉至 ${children}`}
          >
            <Play size={10} className="fill-current" />
            {children}
          </button>
        );
      }
      // Default link behavior
      return (
        <a
          href={href}
          className="text-indigo-600 dark:text-indigo-400 hover:underline"
          target="_blank"
          rel="noopener noreferrer"
          {...props}
        >
          {children}
        </a>
      );
    },
    // Customize other elements if needed
    p: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-xs' : fontSizeLevel === 1 ? 'text-sm' : fontSizeLevel === 2 ? 'text-base' : fontSizeLevel === 3 ? 'text-lg' : 'text-xl';
      return <p className={`mb-4 leading-relaxed ${sizeClass}`}>{children}</p>;
    },
    h1: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-lg' : fontSizeLevel === 1 ? 'text-xl' : fontSizeLevel === 2 ? 'text-2xl' : fontSizeLevel === 3 ? 'text-3xl' : 'text-4xl';
      return <h1 className={`font-bold mt-8 mb-4 ${sizeClass}`}>{children}</h1>;
    },
    h2: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-base' : fontSizeLevel === 1 ? 'text-lg' : fontSizeLevel === 2 ? 'text-xl' : fontSizeLevel === 3 ? 'text-2xl' : 'text-3xl';
      return <h2 className={`font-bold mt-6 mb-3 ${sizeClass}`}>{children}</h2>;
    },
    h3: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-sm' : fontSizeLevel === 1 ? 'text-base' : fontSizeLevel === 2 ? 'text-lg' : fontSizeLevel === 3 ? 'text-xl' : 'text-2xl';
      return <h3 className={`font-bold mt-5 mb-2 ${sizeClass}`}>{children}</h3>;
    },
    ul: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-xs' : fontSizeLevel === 1 ? 'text-sm' : fontSizeLevel === 2 ? 'text-base' : fontSizeLevel === 3 ? 'text-lg' : 'text-xl';
      return <ul className={`list-disc pl-6 mb-4 space-y-2 ${sizeClass}`}>{children}</ul>;
    },
    ol: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-xs' : fontSizeLevel === 1 ? 'text-sm' : fontSizeLevel === 2 ? 'text-base' : fontSizeLevel === 3 ? 'text-lg' : 'text-xl';
      return <ol className={`list-decimal pl-6 mb-4 space-y-2 ${sizeClass}`}>{children}</ol>;
    },
    li: ({ children }: any) => <li className="pl-1">{children}</li>,
    blockquote: ({ children }: any) => {
      const sizeClass = fontSizeLevel === 0 ? 'text-xs' : fontSizeLevel === 1 ? 'text-sm' : fontSizeLevel === 2 ? 'text-base' : fontSizeLevel === 3 ? 'text-lg' : 'text-xl';
      return (
        <blockquote className={`border-l-4 pl-4 py-1 my-4 italic ${sizeClass} ${isDark ? 'border-slate-600 text-slate-400' : 'border-slate-300 text-slate-500'}`}>
          {children}
        </blockquote>
      );
    },
    img: ({ src, alt, ...props }: any) => (
      <img
        src={src}
        alt={alt}
        className="rounded-lg border border-slate-200 dark:border-slate-800 my-4 max-w-full h-auto"
        loading="lazy"
        {...props}
      />
    ),
  };

  return (
    <div className={`min-h-screen flex flex-col transition-colors duration-300 ${isDark ? 'bg-transparent text-slate-200' : 'bg-white text-slate-800'}`}>
      <SEO
        title={article.title}
        description={typeof article.summary === 'string' ? article.summary : undefined}
        structuredData={structuredData}
        url={window.location.href}
        type={article.category === 'Podcast' ? 'podcast' : 'article'}
      />
      <Header />

      {/* Navigation Header */}
      <nav className={`sticky top-0 z-20 border-b px-6 py-3 flex justify-between items-center backdrop-blur-md ${isDark ? 'bg-slate-950/90 border-slate-800' : 'bg-white/90 border-slate-200'}`}>
        <Link
          to="/"
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${isDark ? 'hover:bg-slate-800 text-slate-400 hover:text-white' : 'hover:bg-slate-100 text-slate-600 hover:text-slate-900'}`}
        >
          <ArrowLeft size={16} /> 返回儀表板
        </Link>

        {/* User Menu or other actions could go here */}
        <div />
      </nav>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">

            {/* Left Column: Article Content (9 Cols) */}
            <article className="lg:col-span-9">
              <header className="mb-6">
                <Breadcrumbs
                  items={[
                    { label: article.source, href: `/podcaster/${encodeURIComponent(article.source)}` },
                    { label: article.title }
                  ]}
                  className="mb-4"
                />
                <h1 className={`text-2xl md:text-3xl font-bold mt-4 mb-3 leading-tight ${isDark ? 'text-slate-50' : 'text-slate-900'}`}>
                  {article.title}
                </h1>
                <div className="flex items-center gap-3 text-sm text-slate-500 h-5">
                  <Link
                    to={`/podcaster/${encodeURIComponent(article.source)}`}
                    className="font-bold text-slate-500 dark:text-slate-400 hover:text-amber-600 dark:hover:text-amber-500 transition-colors flex items-center h-full"
                  >
                    {article.source}
                  </Link>
                  <span className="w-px h-3 bg-slate-300 dark:bg-slate-700" aria-hidden="true" />
                  <span className="flex items-center gap-1.5 h-full"><Clock size={14} className="stroke-[2.5px]" /> {article.date}</span>
                </div>

                {/* Action Toolbar */}
                <div className="flex flex-wrap items-center gap-3 mt-6">
                  {/* Play Button */}
                  {spotifyUri && (
                    <button
                      onClick={() => {
                        playEpisode({
                          id: article.id,
                          title: article.title,
                          showName: article.source,
                          coverUrl: undefined,
                          spotifyUri: spotifyUri,
                          timestampedSections: timestampedSections
                        });
                      }}
                      className="h-10 px-4 flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white rounded-full text-sm font-medium transition-all shadow-sm hover:shadow hover:-translate-y-0.5"
                    >
                      <Play size={16} className="fill-current" />
                      播放本集 {(apiEpisode as any)?.duration_ms ? `(${Math.round((apiEpisode as any).duration_ms / 60000)}m)` : ''}
                    </button>
                  )}

                  {/* Source Button */}
                  <button
                    onClick={() => {
                      const url = apiEpisode?.spotify_url || `https://open.spotify.com/episode/${article.id}`;
                      window.open(url, '_blank');
                    }}
                    className="h-10 px-4 flex items-center gap-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-full text-sm font-medium transition-colors"
                  >
                    <ExternalLink size={16} />
                    收聽來源
                  </button>

                  {/* Utility Buttons & Socials */}
                  <div className="flex flex-wrap gap-2 ml-auto sm:ml-0 items-center">
                    {/* Font Size Controls - Unified Segmented Group */}
                    <div className="flex items-center bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-full p-0.5">
                      <button
                        onClick={() => setFontSizeLevel(Math.max(0, fontSizeLevel - 1) as 0 | 1 | 2 | 3 | 4)}
                        disabled={fontSizeLevel === 0}
                        className={`h-8 px-3 flex items-center justify-center rounded-full text-xs font-bold transition-all ${fontSizeLevel === 0
                          ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
                          : 'text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:shadow-sm'
                          }`}
                        title="縮小字體"
                      >
                        A-
                      </button>
                      <div className="w-px h-4 bg-slate-200 dark:bg-slate-700" />
                      <button
                        onClick={() => setFontSizeLevel(Math.min(4, fontSizeLevel + 1) as 0 | 1 | 2 | 3 | 4)}
                        disabled={fontSizeLevel === 4}
                        className={`h-8 px-3 flex items-center justify-center rounded-full text-xs font-bold transition-all ${fontSizeLevel === 4
                          ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
                          : 'text-slate-700 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800 hover:shadow-sm'
                          }`}
                        title="放大字體"
                      >
                        A+
                      </button>
                    </div>

                    <div className="w-px h-6 bg-slate-200 dark:bg-slate-700" />

                    {/* Bookmark */}
                    {token && effectivePodcastName && id && (
                      <button
                        onClick={handleBookmarkClick}
                        disabled={bookmarkLoading}
                        className={`w-10 h-10 flex items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 transition-colors ${isBookmarked
                          ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 border-amber-200 dark:border-amber-800'
                          : 'text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800'
                          }`}
                        title={isBookmarked ? "取消收藏" : "收藏"}
                      >
                        <Bookmark size={18} fill={isBookmarked ? "currentColor" : "none"} />
                      </button>
                    )}

                    <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 hidden sm:block" />

                    {/* Social Share Buttons - Hidden on mobile */}
                    {/* LINE */}
                    <button
                      onClick={() => window.open(`https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(window.location.href)}`, '_blank')}
                      className="hidden sm:flex w-10 h-10 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-[#06C755] hover:bg-[#06C755]/10 dark:hover:bg-[#06C755]/20 transition-colors"
                      title="分享到 LINE"
                    >
                      <MessageCircle size={18} />
                    </button>

                    {/* Facebook */}
                    <button
                      onClick={() => window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(window.location.href)}`, '_blank')}
                      className="hidden sm:flex w-10 h-10 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-[#1877F2] hover:bg-[#1877F2]/10 dark:hover:bg-[#1877F2]/20 transition-colors"
                      title="分享到 Facebook"
                    >
                      <Facebook size={18} />
                    </button>

                    {/* Threads */}
                    <button
                      onClick={() => window.open(`https://www.threads.net/intent/post?text=${encodeURIComponent(article.title)}&url=${encodeURIComponent(window.location.href)}`, '_blank')}
                      className="hidden sm:flex w-10 h-10 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-black dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="分享到 Threads"
                    >
                      <AtSign size={18} />
                    </button>

                    {/* Copy Link */}
                    <button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(window.location.href);
                          setCopySuccess(true);
                          setTimeout(() => setCopySuccess(false), 2000);
                        } catch (err) {
                          console.error('Failed to copy', err);
                        }
                      }}
                      className="hidden sm:flex w-10 h-10 items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors relative"
                      title="複製連結"
                    >
                      {copySuccess ? <Check size={18} className="text-emerald-500" /> : <LinkIcon size={18} />}
                    </button>

                    {/* Share Menu - Mobile */}
                    <div className="relative sm:hidden" ref={shareMenuRef}>
                      <button
                        onClick={() => setIsShareMenuOpen(!isShareMenuOpen)}
                        className={`w-10 h-10 flex items-center justify-center rounded-full border border-slate-200 dark:border-slate-700 transition-colors ${isShareMenuOpen
                            ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white'
                            : 'text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800'
                          }`}
                        title="分享"
                      >
                        <Share2 size={18} />
                      </button>

                      {/* Dropdown Menu */}
                      {isShareMenuOpen && (
                        <div className="absolute top-12 right-0 w-max flex gap-2 p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                          {/* LINE */}
                          <button
                            onClick={() => window.open(`https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(window.location.href)}`, '_blank')}
                            className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-50 dark:bg-slate-800 text-slate-500 hover:text-[#06C755] hover:bg-[#06C755]/10 dark:hover:bg-[#06C755]/20 transition-colors"
                            title="分享到 LINE"
                          >
                            <MessageCircle size={18} />
                          </button>
                          {/* Facebook */}
                          <button
                            onClick={() => window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(window.location.href)}`, '_blank')}
                            className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-50 dark:bg-slate-800 text-slate-500 hover:text-[#1877F2] hover:bg-[#1877F2]/10 dark:hover:bg-[#1877F2]/20 transition-colors"
                            title="分享到 Facebook"
                          >
                            <Facebook size={18} />
                          </button>
                          {/* Threads */}
                          <button
                            onClick={() => window.open(`https://www.threads.net/intent/post?text=${encodeURIComponent(article.title)}&url=${encodeURIComponent(window.location.href)}`, '_blank')}
                            className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-50 dark:bg-slate-800 text-slate-500 hover:text-black dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                            title="分享到 Threads"
                          >
                            <AtSign size={18} />
                          </button>
                          {/* Copy Link */}
                          <button
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(window.location.href);
                                setCopySuccess(true);
                                setTimeout(() => setCopySuccess(false), 2000);
                                setIsShareMenuOpen(false);
                              } catch (err) {
                                console.error('Failed to copy', err);
                              }
                            }}
                            className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-50 dark:bg-slate-800 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors relative"
                            title="複製連結"
                          >
                            {copySuccess ? <Check size={18} className="text-emerald-500" /> : <LinkIcon size={18} />}
                          </button>
                        </div>
                      )}
                    </div>

                  </div>
                </div>
              </header>

              {/* Marp Slides Viewer - only show in non-production (developer feature) */}
              {import.meta.env.VITE_STAGE !== 'PRODUCTION' && (apiEpisode?.ticker_marp_markdown_content || apiEpisode?.marp_markdown_content) && (
                <div className="mb-8">
                  <SlideViewer
                    content={(apiEpisode.ticker_marp_markdown_content || apiEpisode.marp_markdown_content) as string}
                    isDark={isDark}
                  />
                </div>
              )}

              {/* Content Type Tabs - only show in non-production (developer feature) */}
              {/* On production, users only see the summary content directly without tabs */}
              {import.meta.env.VITE_STAGE !== 'PRODUCTION' && apiEpisode && (article.eventsContent || article.sentencesContent || recommendationsData || true) && (
                <div className={`mb-6 border-b ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                  <nav className="flex gap-1" aria-label="Content type tabs">
                    <button
                      onClick={() => setActiveContentTab('summary')}
                      className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeContentTab === 'summary'
                        ? isDark
                          ? 'border-amber-500 text-amber-500'
                          : 'border-indigo-600 text-indigo-600'
                        : isDark
                          ? 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-600'
                          : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        }`}
                    >
                      摘要
                    </button>
                    {article.eventsContent && (
                      <button
                        onClick={() => setActiveContentTab('events')}
                        className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeContentTab === 'events'
                          ? isDark
                            ? 'border-amber-500 text-amber-500'
                            : 'border-indigo-600 text-indigo-600'
                          : isDark
                            ? 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-600'
                            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                          }`}
                      >
                        事件
                      </button>
                    )}
                    {article.sentencesContent && (
                      <button
                        onClick={() => setActiveContentTab('sentences')}
                        className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeContentTab === 'sentences'
                          ? isDark
                            ? 'border-amber-500 text-amber-500'
                            : 'border-indigo-600 text-indigo-600'
                          : isDark
                            ? 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-600'
                            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                          }`}
                      >
                        逐字稿
                      </button>
                    )}
                    {recommendationsData && (
                      <button
                        onClick={() => setActiveContentTab('recommendations')}
                        className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeContentTab === 'recommendations'
                          ? isDark
                            ? 'border-amber-500 text-amber-500'
                            : 'border-indigo-600 text-indigo-600'
                          : isDark
                            ? 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-600'
                            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                          }`}
                      >
                        推薦資訊
                      </button>
                    )}
                    <button
                      onClick={() => setActiveContentTab('edit')}
                      className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeContentTab === 'edit'
                        ? isDark
                          ? 'border-amber-500 text-amber-500'
                          : 'border-indigo-600 text-indigo-600'
                        : isDark
                          ? 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-600'
                          : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        }`}
                    >
                      編輯摘要
                    </button>
                    {apiEpisode?.id && (
                      <button
                        onClick={handleRegenerateEpisode}
                        disabled={isRegenerating}
                        className={`ml-2 p-2 rounded transition-colors ${
                          isRegenerating
                            ? 'opacity-50 cursor-not-allowed'
                            : isDark
                              ? 'text-slate-400 hover:text-slate-300 hover:bg-slate-800'
                              : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                        }`}
                        title="重新生成摘要"
                      >
                        <RotateCw 
                          size={18} 
                          className={isRegenerating ? 'animate-spin' : ''} 
                        />
                      </button>
                    )}
                  </nav>
                </div>
              )}

              {/* Main Article Image/Graph (Mobile/Inline view) - Optional, we stick to text here mostly */}

              <div className={`prose max-w-none ${isDark ? 'prose-invert text-slate-300' : 'text-slate-700'}`}>
                {(() => {
                  // Edit mode - show textarea and buttons
                  if (activeContentTab === 'edit') {
                    return (
                      <div className="space-y-4 not-prose">
                        {/* Show indicator if modified version exists */}
                        {apiEpisode?.modified_summary_content && (
                          <div className={`p-3 rounded-lg ${isDark ? 'bg-amber-900/20 text-amber-400' : 'bg-amber-100 text-amber-700'}`}>
                            📝 Currently showing modified version. Original summary is preserved.
                          </div>
                        )}

                        {/* Textarea for editing */}
                        <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          placeholder="Enter markdown content here..."
                          className={`w-full h-96 font-mono text-sm p-4 border rounded-lg resize-y ${isDark
                            ? 'bg-slate-800 border-slate-700 text-slate-200 placeholder-slate-500'
                            : 'bg-white border-slate-300 text-slate-900 placeholder-slate-400'
                            }`}
                        />

                        {/* Action buttons */}
                        <div className="flex gap-2 items-center">
                          <button
                            onClick={async () => {
                              setIsSaving(true);
                              try {
                                await updateEpisodeSummary(
                                  effectivePodcastName || '',
                                  id || '',
                                  editedContent,
                                  'dev-user'
                                );
                                // Reload page to show updated content
                                window.location.reload();
                              } catch (error) {
                                console.error('Failed to save:', error);
                                alert('Failed to save modified summary. Please try again.');
                              } finally {
                                setIsSaving(false);
                              }
                            }}
                            disabled={isSaving}
                            className={`px-4 py-2 rounded-lg font-medium transition-colors ${isSaving
                              ? 'bg-slate-400 text-white cursor-not-allowed'
                              : isDark
                                ? 'bg-amber-600 hover:bg-amber-700 text-white'
                                : 'bg-indigo-600 hover:bg-indigo-700 text-white'
                              }`}
                          >
                            {isSaving ? 'Saving...' : 'Save Modified Summary'}
                          </button>
                          {apiEpisode?.modified_summary_url && (
                            <button
                              onClick={async () => {
                                if (!confirm('Are you sure you want to revert to the original summary? This will delete the modified version.')) return;
                                try {
                                  await deleteEpisodeSummary(
                                    effectivePodcastName || '',
                                    id || ''
                                  );
                                  // Reload page to show original content
                                  window.location.reload();
                                } catch (error) {
                                  console.error('Failed to revert:', error);
                                  alert('Failed to revert to original. Please try again.');
                                }
                              }}
                              className={`px-4 py-2 rounded-lg font-medium transition-colors ${isDark
                                ? 'bg-slate-700 hover:bg-slate-600 text-slate-200'
                                : 'bg-slate-200 hover:bg-slate-300 text-slate-700'
                                }`}
                            >
                              Revert to Original
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  }

                  // Recommendations tab - show JSON data
                  if (activeContentTab === 'recommendations' && recommendationsData) {
                    return (
                      <div className="not-prose">
                        <pre className={`p-4 rounded-lg overflow-auto text-sm ${
                          isDark 
                            ? 'bg-slate-800 text-slate-200' 
                            : 'bg-slate-100 text-slate-900'
                        }`}>
                          <code>{JSON.stringify(recommendationsData, null, 2)}</code>
                        </pre>
                      </div>
                    );
                  }

                  // Determine which content to display based on active tab
                  let contentToDisplay: string | null = null;

                  if (apiEpisode && (article.eventsContent || article.sentencesContent)) {
                    // Use tab-based content selection
                    if (activeContentTab === 'events' && article.eventsContent) {
                      contentToDisplay = article.eventsContent;
                    } else if (activeContentTab === 'sentences' && article.sentencesContent) {
                      contentToDisplay = article.sentencesContent;
                    } else {
                      // Default to summary (prioritize modified summary if exists)
                      contentToDisplay = article.modifiedContent || article.content;
                    }
                  } else {
                    // Fallback to modified or original content
                    contentToDisplay = article.modifiedContent || (typeof article.content === 'string' ? article.content : null);
                  }

                  if (contentToDisplay && typeof contentToDisplay === 'string') {
                    return (
                      <>
                        {/* Show indicator when displaying modified summary */}
                        {activeContentTab === 'summary' && article.modifiedContent && import.meta.env.VITE_STAGE !== 'PRODUCTION' && (
                          <div className={`mb-4 text-sm ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                            📝 Showing modified summary
                          </div>
                        )}
                        <ReactMarkdown components={MarkdownComponents}>
                          {contentToDisplay}
                        </ReactMarkdown>
                      </>
                    );
                  } else if (contentToDisplay === null && apiEpisode && activeContentTab !== 'summary') {
                    // Show message if selected content doesn't exist
                    return (
                      <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        {activeContentTab === 'events' ? '事件內容暫無資料' : '逐字稿內容暫無資料'}
                      </p>
                    );
                  } else if (typeof article.content === 'string') {
                    return (
                      <ReactMarkdown components={MarkdownComponents}>
                        {article.content}
                      </ReactMarkdown>
                    );
                  } else {
                    // For JSX content (like from INTERACTIVE_MODELS), render directly
                    return article.content;
                  }
                })()}
              </div>

              {/* Related Topics (Extracted Tags) */}
              {allTags.length > 0 && (
                <div className="mt-12 pt-8 border-t border-slate-200 dark:border-slate-800/50">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-4">相關關鍵字</h3>
                  <div className="flex flex-wrap gap-2">
                    {allTags.map((tag: string) => (
                      <button
                        key={tag}
                        onClick={() => navigate(`/tag/${encodeURIComponent(tag)}`)}
                        className="text-sm bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 px-4 py-1.5 rounded-full transition-colors font-medium"
                      >
                        #{tag}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <DonationCard />
            </article>

            {/* Right Column: Sidebar Widgets (3 Cols - Narrower) */}
            <aside className="lg:col-span-3 space-y-6">

              {/* Widget 1: The Main Visualization (Deprecated/Hidden) */}
              {/* {article.GraphComponent && (
                <div className={`rounded-xl border overflow-hidden shadow-lg ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'}`}>
                  <div className={`px-4 py-3 border-b text-xs font-bold uppercase tracking-wider ${isDark ? 'bg-slate-800 border-slate-700 text-slate-300' : 'bg-slate-50 border-slate-100 text-slate-500'}`}>
                    互動模型
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveModelId(article.id)}
                    className={`group relative h-[350px] w-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(77,107,148,0.5)] ${isDark ? 'bg-slate-900/60' : 'bg-slate-50'
                      }`}
                  >
                    <Graph isWidget={true} />
                    <span className="absolute bottom-4 right-4 text-xs font-semibold bg-black/60 text-slate-50 px-3 py-1 rounded-full flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      開啟沉浸式檢視
                    </span>
                  </button>
                  <div className={`px-4 py-2 text-xs text-center italic ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    點擊節點探索關聯性
                  </div>
                </div>
              )} */}

              {/* Widget 2: Mentioned Assets */}
              {(isLoadingTickers || article.tickers.length > 0) && (
                <div>
                  <h3 className={`text-sm font-bold uppercase tracking-wider mb-3 flex items-center gap-2 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    <Activity size={14} /> 相關標的
                  </h3>
                  <div className="space-y-4">
                    {isLoadingTickers ? (
                      <>
                        <RelatedAssetCardSkeleton isDark={isDark} />
                        <RelatedAssetCardSkeleton isDark={isDark} />
                        <RelatedAssetCardSkeleton isDark={isDark} />
                      </>
                    ) : (
                      article.tickers.map((t: any) => (
                        <RelatedAssetCard
                          key={t.symbol}
                          ticker={t}
                          isDark={isDark}
                          isExpanded={expandedAsset === t.symbol}
                          onToggle={() => setExpandedAsset(expandedAsset === t.symbol ? null : t.symbol)}
                        />
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* Widget 3: Macro Context */}
              {article.indices.length > 0 && (
                <div>
                  <h3 className={`text-sm font-bold uppercase tracking-wider mb-3 flex items-center gap-2 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    <TrendingUp size={14} /> 總經背景
                  </h3>
                  <div className="space-y-4">
                    {article.indices.map((t: any) => (
                      <RelatedAssetCard
                        key={t.symbol}
                        ticker={t}
                        isDark={isDark}
                        isExpanded={expandedMacroAsset === t.symbol}
                        onToggle={() => setExpandedMacroAsset(expandedMacroAsset === t.symbol ? null : t.symbol)}
                        badgeText="總經訊號"
                      />
                    ))}
                  </div>
                </div>
              )}

            </aside>
          </div>
        </div>
      </main>

      <Footer />
      {activeModelId && (
        <InteractiveModelModal
          modelId={activeModelId}
          onClose={() => setActiveModelId(null)}
          isDark={isDark}
        />
      )}
    </div>
  );
};

export default NewsPage;

interface InteractiveModelModalProps {
  modelId: string;
  onClose: () => void;
  isDark: boolean;
}

const InteractiveModelModal: React.FC<InteractiveModelModalProps> = ({ modelId, onClose, isDark }) => {
  const model = INTERACTIVE_MODELS[modelId];
  // Fallback for mock episode modals if needed, though they generally don't have detailed interactive models defined.
  // For now we just return null or basic graph if not in INTERACTIVE_MODELS
  if (!model) return null;

  const Graph = model.GraphComponent;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/80 px-4 py-6 backdrop-blur">
      <div
        className={`relative flex h-[85vh] w-full max-w-[1200px] flex-col rounded-[36px] border shadow-[0_45px_100px_rgba(2,6,23,0.55)] overflow-hidden ${isDark ? 'bg-slate-950 border-slate-800' : 'bg-white border-slate-200'
          }`}
      >
        <div
          className={`flex items-center justify-between border-b px-6 py-4 ${isDark ? 'border-slate-800 bg-slate-950/70' : 'border-slate-200 bg-white/80'
            }`}
        >
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-brand-yellow">互動模型</p>
            <h3 className={`text-2xl font-bold ${isDark ? 'text-slate-50' : 'text-slate-900'}`}>{model.title}</h3>
            <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {model.graphTypeLabel} • {model.source}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${isDark ? 'border-slate-700 text-slate-50 hover:bg-white/10' : 'border-slate-300 text-slate-700 hover:bg-slate-100'
              }`}
          >
            關閉
          </button>
        </div>
        <div className="flex-1 min-h-0">
          <div className="h-full w-full">
            <Graph />
          </div>
        </div>
      </div>
    </div>
  );
};
