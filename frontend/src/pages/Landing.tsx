import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { useAppStore } from '@/store/useAppStore';
import { Button, Skeleton } from '@/components/ui';
import { Mic, ChevronDown, ArrowDown } from 'lucide-react';
import { PopularTickersWidget, ActiveChannelsWidget } from '@/components/home/DashboardWidgets';
import { NewsletterCard } from '@/components/home/NewsletterCard';
import EpisodeCard from '@/components/home/EpisodeCard';
import { SEO } from '@/components/common/SEO';
import type { Episode as MockEpisode } from '@/data/mockData';
import { getRecentEpisodes } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { userApi } from '@/services/api/user';
import { transformApiEpisodeToMock } from '@/services/api/transformers';


export const Landing: React.FC = () => {
  const navigate = useNavigate();
  const { setHeroSearchInView, token } = useAppStore();
  const [episodes, setEpisodes] = useState<MockEpisode[]>([]);
  const [loading, setLoading] = useState(true);
  const [episodeBookmarks, setEpisodeBookmarks] = useState<Set<string>>(new Set());
  const [visibleCount, setVisibleCount] = useState(6);

  useEffect(() => {
    setHeroSearchInView(false);
  }, [setHeroSearchInView]);

  // Fetch episodes from API
  useEffect(() => {
    const fetchEpisodes = async () => {
      setLoading(true);
      try {
        const apiEpisodes = await fetchWithFallback(
          () => getRecentEpisodes({
            limit: 50,
            sortBy: 'spotify_release_date',
            order: 'desc',
            // Skip heavy content (GCS fetch) for initial page load — cards show title/image only
            includeContent: false
          }),
          [],
          'getRecentEpisodes'
        );



        if (!apiEpisodes || !Array.isArray(apiEpisodes) || apiEpisodes.length === 0) {
          setEpisodes([]);
          setLoading(false);
          return;
        }

        const transformedEpisodes = apiEpisodes
          .map(transformApiEpisodeToMock)
          .filter((ep): ep is MockEpisode => ep !== null);

        setEpisodes(transformedEpisodes);
      } catch (error) {
        console.error('[Landing] Failed to fetch episodes:', error);
        setEpisodes([]);
      } finally {
        setLoading(false);
      }
    };

    fetchEpisodes();
  }, []);

  // Fetch episode bookmarks once (only if user is logged in)
  // This prevents each EpisodeCard from making individual API calls
  const refreshBookmarks = useCallback(async () => {
    if (!token) {
      setEpisodeBookmarks(new Set());
      return;
    }

    try {
      const bookmarks = await userApi.getEpisodeBookmarks();
      setEpisodeBookmarks(new Set(bookmarks));
    } catch (error) {
      console.error('[Landing] Failed to fetch episode bookmarks:', error);
      setEpisodeBookmarks(new Set());
    }
  }, [token]);

  useEffect(() => {
    refreshBookmarks();
  }, [refreshBookmarks]);

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const handleTickerFilter = (ticker: string) => {
    navigate(`/stock/${ticker}`);
  };

  const newsletterRef = useRef<HTMLDivElement>(null);

  const scrollToNewsletter = () => {
    newsletterRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const filteredEpisodes = useMemo(() => {
    if (!selectedTicker) return episodes;
    return episodes.filter(ep => {
      // Check tags
      if (ep.tags.some(t => t.toLowerCase() === selectedTicker.toLowerCase() || t.toLowerCase() === `#${selectedTicker.toLowerCase()}`)) return true;
      // Check title or summary content matches roughly
      if (ep.title.includes(selectedTicker)) return true;
      // Check Key Insights
      if (ep.keyInsights?.some(k => k.includes(selectedTicker))) return true;
      return false;
    });
  }, [episodes, selectedTicker]);

  const visibleEpisodes = filteredEpisodes.slice(0, visibleCount);
  const hasMore = visibleCount < filteredEpisodes.length;

  const handleLoadMore = () => {
    setVisibleCount(prev => prev + 6);
  };

  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    'name': 'TinBoker',
    'url': 'https://tinboker.com',
    'potentialAction': {
      '@type': 'SearchAction',
      'target': 'https://tinboker.com/search?q={search_term_string}',
      'query-input': 'required name=search_term_string'
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-transparent">
      <SEO
        title="聽播客 - 聽見市場聲音，看見財富趨勢"
        structuredData={structuredData}
        url="https://tinboker.com"
      />
      <Header />

      <div className="flex-1">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

            {/* Hero Section - Full Width */}
            <div className="lg:col-span-12 pt-6 pb-8 sm:py-14 lg:py-20 mb-4 text-center px-4 relative overflow-hidden">
              {/* Decorative gradient orb */}
              <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-gradient-to-br from-emerald-400/15 via-amber-400/10 to-transparent rounded-full blur-3xl pointer-events-none dark:from-emerald-400/8 dark:via-amber-400/5" />

              <h1 className="relative text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter leading-[1.1] mb-4">
                <span className="text-slate-900 dark:text-slate-50 block sm:inline">最新財經 Podcast</span>
                <span className="block sm:inline sm:ml-3 bg-gradient-to-r from-emerald-600 via-teal-500 to-amber-500 dark:from-emerald-400 dark:via-teal-400 dark:to-amber-400 bg-clip-text text-transparent">
                  精華摘要
                </span>
              </h1>

              <p className="relative max-w-xl mx-auto text-sm sm:text-base text-slate-500 dark:text-slate-400 font-medium leading-relaxed">
                AI 自動分析財經 Podcast，萃取關鍵洞察與投資建議，
                <br className="hidden sm:block" />
                讓您用最短時間掌握最重要的市場資訊。
              </p>

              <div className="relative mt-10 flex justify-center animate-in fade-in slide-in-from-bottom-4 duration-700 delay-200">
                <button
                  onClick={scrollToNewsletter}
                  className="group relative inline-flex p-[1.5px] rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-emerald-500 bg-[length:200%_auto] animate-gradient shadow-lg shadow-emerald-500/15 hover:shadow-emerald-500/30 transition-all duration-300 hover:scale-105 active:scale-[0.98]"
                >
                  <span className="relative inline-flex items-center gap-2.5 px-7 py-3 rounded-full bg-white dark:bg-slate-900 transition-all duration-300">
                    <span className="text-sm font-bold bg-gradient-to-r from-slate-700 to-slate-900 dark:from-slate-100 dark:to-slate-300 bg-clip-text text-transparent group-hover:from-emerald-600 group-hover:to-amber-600 dark:group-hover:from-emerald-400 dark:group-hover:to-amber-400 transition-all">
                      想要更聰明地掌握財經資訊？
                    </span>
                    <ArrowDown className="text-slate-400 group-hover:text-emerald-500 transition-colors animate-bounce" size={16} />
                  </span>
                </button>
              </div>
            </div>

            {/* Main Content: Episode Feed */}
            <main className="lg:col-span-8 flex flex-col">

              {/* Episode Feed Header */}
              <div className="flex items-center justify-between pb-4">
                <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50">
                  <Mic className="text-amber-500 dark:text-amber-400" size={20} />
                  {selectedTicker ? `關於 ${selectedTicker} 的摘要` : '最新摘要'}
                </h2>
                {selectedTicker && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedTicker(null)}
                    className="text-slate-500 hover:text-slate-900 dark:hover:text-white"
                  >
                    Clear Filter
                  </Button>
                )}
              </div>

              {/* Episode Cards - Scrollable Area Starts Here */}
              <section
                aria-label="Latest Episodes"
                ref={scrollContainerRef}
                className="flex-1 pr-2"
              >
                {loading ? (
                  <div className="space-y-6 pb-6">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
                        <div className="flex items-center gap-4 mb-4">
                          <Skeleton className="w-12 h-12 rounded-full" />
                          <div className="space-y-2">
                            <Skeleton className="h-4 w-32" />
                            <Skeleton className="h-3 w-24" />
                          </div>
                        </div>
                        <Skeleton className="h-6 w-3/4 mb-4" />
                        <div className="space-y-2 mb-6">
                          <Skeleton className="h-4 w-full" />
                          <Skeleton className="h-4 w-full" />
                          <Skeleton className="h-4 w-5/6" />
                        </div>
                        <div className="flex gap-2">
                          <Skeleton className="h-6 w-16 rounded-full" />
                          <Skeleton className="h-6 w-16 rounded-full" />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-6 pb-6 stagger-in">
                    {visibleEpisodes.length > 0 ? (
                      <>
                        {visibleEpisodes.map((episode) => {
                          const formattedEpisodeId = `${episode.showName}_${episode.id}`;
                          const isBookmarked = token ? episodeBookmarks.has(formattedEpisodeId) : false;
                          return (
                            <EpisodeCard
                              key={episode.id}
                              episode={episode}
                              isBookmarked={isBookmarked}
                              onBookmarkToggle={refreshBookmarks}
                              variant="full"
                            />
                          );
                        })}

                        {hasMore && (
                          <div className="flex justify-center pt-4">
                            <Button
                              variant="outline"
                              onClick={handleLoadMore}
                              className="gap-2 rounded-full px-8 py-2.5 bg-white dark:bg-slate-900/80 border-slate-200/80 dark:border-slate-700/50 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white hover:border-slate-300 dark:hover:border-slate-600 transition-all duration-200 hover:shadow-sm active:scale-[0.97]"
                            >
                              載入更多 <ChevronDown size={16} />
                            </Button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-12">
                        <p className="text-slate-500 dark:text-slate-400">
                          {selectedTicker ? `找不到關於 ${selectedTicker} 的相關內容` : '目前沒有集數'}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </section>

              {/* Mobile: Secondary Widgets (Tickers & Channels) - Moved to bottom for hierarchy */}
              <div className="space-y-6 mt-8 lg:hidden">
                <div>
                  <PopularTickersWidget isMobile onTickerSelect={handleTickerFilter} />
                </div>
                <div>
                  <ActiveChannelsWidget isMobile />
                </div>
              </div>
            </main>

            {/* Right Sidebar: Popular Tickers & Active Channels - Always visible on large screens */}
            <aside className="hidden lg:flex lg:col-span-4 flex-col gap-6 sticky top-24 self-start max-h-[calc(100vh-8rem)] overflow-y-auto pr-2 no-scrollbar">
              <div className="rounded-2xl p-5">
                <PopularTickersWidget onTickerSelect={handleTickerFilter} />
              </div>
              <div className="rounded-2xl p-5">
                <ActiveChannelsWidget />
              </div>
            </aside>
          </div>

          <div ref={newsletterRef} className="mt-12 mb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 delay-300">
            <NewsletterCard />
          </div>
        </div>
      </div>

      <Footer />


    </div >
  );
};
