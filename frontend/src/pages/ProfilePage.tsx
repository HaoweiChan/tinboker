import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Star, Mail, Calendar, Search, Plus, Mic, Bookmark, Tag } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Footer } from '@/components/layout/Footer';
import { Card, CardContent } from '@/components/ui';
import { Modal } from '@/components/ui/Modal';
import EpisodeCard from '@/components/home/EpisodeCard';
import type { Episode as MockEpisode } from '@/data/mockData';
import { StockCardItem } from '@/components/home/DashboardWidgets';
import { useAppStore } from '@/store/useAppStore';
import { getSortedStocks, getStockByTicker, getPodcastByName, getEpisodeById, type Episode as ApiEpisode, type Podcast } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { authApi, type AuthResponse } from '@/services/api/auth';
import { userApi } from '@/services/api/user';

// Helper functions
const formatJoinDate = (createdAt: string): string => {
  const date = new Date(createdAt);
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  return `${year}年 ${month}月`;
};

const getUserInitials = (name: string): string => {
  return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
};

// Transform API episode to mock episode format for EpisodeCard compatibility
function transformApiEpisodeToMock(apiEpisode: ApiEpisode): MockEpisode {
  const summaryText = apiEpisode.summary_content || '';
  const summaryLines = summaryText.split('\n').filter(line => line.trim().length > 0);
  const summary: MockEpisode['summary'] = summaryLines.slice(0, 5).map(text => ({
    text: text.trim(),
    highlights: [],
  }));

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

  const podcastName = apiEpisode.podcast_name || '';
  let showAvatar = 'IMG';
  let showColorClass = 'bg-slate-200 text-slate-600';
  if (podcastName.includes('股癌')) {
    showAvatar = 'IMG';
    showColorClass = 'bg-slate-200 text-slate-600';
  } else if (podcastName.includes('財報狗')) {
    showAvatar = '狗';
    showColorClass = 'bg-indigo-100 text-indigo-600';
  }

  // Get Spotify image (use first/smallest image from array, or null if not available)
  const imageUrl = apiEpisode.spotify_images && apiEpisode.spotify_images.length > 0
    ? apiEpisode.spotify_images[0] // First image is typically the smallest
    : undefined;

  return {
    id: apiEpisode.id,
    showName: podcastName,
    showAvatar,
    showColorClass,
    title: apiEpisode.episode_title || `EP${apiEpisode.episode_number || ''}`,
    timeAgo,
    isHot: false,
    tags: apiEpisode.tags || [],
    summary,
    imageUrl,
  };
}

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const { watchlist, toggleWatchlist, token } = useAppStore();
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [savedStocks, setSavedStocks] = useState<any[]>([]);
  const [filteredStocks, setFilteredStocks] = useState<any[]>([]);
  const [stocksLoading, setStocksLoading] = useState(true);
  
  // User information state
  const [userInfo, setUserInfo] = useState<AuthResponse['user'] | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  
  // Subscription state
  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [podcastSubscriptions, setPodcastSubscriptions] = useState<string[]>([]);
  const [episodeBookmarks, setEpisodeBookmarks] = useState<string[]>([]);
  const [tagSubscriptions, setTagSubscriptions] = useState<string[]>([]);
  
  // Display data
  const [subscribedPodcasters, setSubscribedPodcasters] = useState<Podcast[]>([]);
  const [bookmarkedEpisodes, setBookmarkedEpisodes] = useState<MockEpisode[]>([]);
  const [podcastersLoading, setPodcastersLoading] = useState(false);
  const [bookmarkedEpisodesLoading, setBookmarkedEpisodesLoading] = useState(false);

  // Fetch user information
  useEffect(() => {
    const fetchUserInfo = async () => {
      if (!token) {
        setUserInfo(null);
        setUserLoading(false);
        return;
      }
      
      setUserLoading(true);
      try {
        const user = await authApi.getCurrentUser(token);
        setUserInfo(user);
      } catch (error) {
        console.error('Failed to fetch user info:', error);
        setUserInfo(null);
      } finally {
        setUserLoading(false);
      }
    };
    
    fetchUserInfo();
  }, [token]);

  // Fetch subscriptions from API
  useEffect(() => {
    const fetchSubscriptions = async () => {
      if (!token) {
        setApiWatchlist([]);
        setPodcastSubscriptions([]);
        setEpisodeBookmarks([]);
        setTagSubscriptions([]);
        return;
      }
      
      try {
        // Use subscriptions from userInfo if available, otherwise fetch separately
        if (userInfo) {
          setApiWatchlist(userInfo.watchlist || []);
          setPodcastSubscriptions(userInfo.podcast_subscriptions || []);
          setEpisodeBookmarks(userInfo.episode_bookmarks || []);
          setTagSubscriptions(userInfo.tag_subscriptions || []);
        } else {
          // Fallback: fetch separately if userInfo doesn't have it yet
          const [watchlistData, podcastsData, episodesData, tagsData] = await Promise.all([
            userApi.getWatchlist().catch(() => []),
            userApi.getPodcastSubscriptions().catch(() => []),
            userApi.getEpisodeBookmarks().catch(() => []),
            userApi.getTagSubscriptions().catch(() => [])
          ]);
          setApiWatchlist(watchlistData);
          setPodcastSubscriptions(podcastsData);
          setEpisodeBookmarks(episodesData);
          setTagSubscriptions(tagsData);
        }
      } catch (error) {
        console.error('Failed to fetch subscriptions:', error);
      }
    };
    
    fetchSubscriptions();
  }, [token, userInfo]);

  // Fetch watchlist stocks
  useEffect(() => {
    const fetchWatchlistStocks = async () => {
      // Use API watchlist if we have it (even if empty), otherwise fall back to store watchlist
      // Prefer userInfo.watchlist if available, then apiWatchlist, then store watchlist
      const watchlistToUse = userInfo?.watchlist !== undefined 
        ? (userInfo.watchlist || [])
        : (apiWatchlist.length > 0 || token ? apiWatchlist : watchlist);
      
      if (watchlistToUse.length === 0) {
        setSavedStocks([]);
        setStocksLoading(false);
        return;
      }

      setStocksLoading(true);
      try {
        // Fetch all stocks and filter by watchlist
        const allStocks = await fetchWithFallback(
          () => getSortedStocks({ limit: 200 }),
          [],
          'getSortedStocks'
        );
        
        // Normalize watchlist symbols (remove .TW, .US, etc. suffixes for matching)
        const normalizedWatchlist = watchlistToUse.map(symbol => symbol.toUpperCase().split('.')[0]);
        
        // Filter stocks that are in watchlist
        const watchlistStocks = allStocks.filter((stock: any) => {
          const ticker = (stock.ticker || stock.symbol || '').toUpperCase();
          const tickerBase = ticker.split('.')[0]; // Remove suffix if present
          
          // Check if ticker matches any watchlist symbol (exact match or base match)
          const matches = normalizedWatchlist.some(wlSymbol => 
            ticker === wlSymbol || tickerBase === wlSymbol || ticker.startsWith(wlSymbol + '.')
          );
          
          return matches;
        });
        
        // Find which watchlist symbols weren't found in the bulk list
        const foundSymbols = new Set(
          watchlistStocks.map((stock: any) => 
            (stock.ticker || stock.symbol || '').toUpperCase().split('.')[0]
          )
        );
        const missingSymbols = normalizedWatchlist.filter(symbol => !foundSymbols.has(symbol));
        
        // Fetch missing stocks individually
        const missingStocks = await Promise.all(
          missingSymbols.map(async (symbol) => {
            try {
              const stock = await fetchWithFallback(
                () => getStockByTicker(symbol),
                null,
                `getStockByTicker(${symbol})`
              );
              return stock;
            } catch (error) {
              console.error(`[ProfilePage] Failed to fetch stock ${symbol}:`, error);
              return null;
            }
          })
        );
        
        // Combine found stocks and missing stocks
        const allFoundStocks = [
          ...watchlistStocks,
          ...missingStocks.filter((stock): stock is any => stock !== null)
        ];
        
        // Transform to expected format
        const transformed = allFoundStocks.map((stock: any) => ({
          symbol: stock.ticker || stock.symbol || '',
          name: stock.name || '',
          price: stock.price || 0,
          change: stock.change || 0,
          changePercent: stock.change_percent || stock.changePercent || 0,
          mentions: undefined,
        }));
        
        setSavedStocks(transformed);
      } catch (error) {
        console.error('[ProfilePage] Failed to fetch watchlist stocks:', error);
        setSavedStocks([]);
      } finally {
        setStocksLoading(false);
      }
    };

    fetchWatchlistStocks();
  }, [watchlist, apiWatchlist, userInfo, token]);

  // Fetch stocks for search modal
  useEffect(() => {
    const fetchSearchStocks = async () => {
      if (!searchQuery.trim()) {
        setFilteredStocks([]);
        return;
      }

      try {
        const stocks = await fetchWithFallback(
          () => getSortedStocks({ q: searchQuery, limit: 50 }),
          [],
          `getSortedStocks(${searchQuery})`
        );
        
        // Transform to expected format
        const transformed = stocks.map((stock: any) => ({
          symbol: stock.ticker || stock.symbol || '',
          name: stock.name || '',
          price: stock.price || 0,
          change: stock.change || 0,
          changePercent: stock.change_percent || stock.changePercent || 0,
        }));
        
        setFilteredStocks(transformed);
      } catch (error) {
        console.error('[ProfilePage] Failed to fetch search stocks:', error);
        setFilteredStocks([]);
      }
    };

    fetchSearchStocks();
  }, [searchQuery]);

  // Fetch subscribed podcasters
  useEffect(() => {
    const fetchPodcasters = async () => {
      if (podcastSubscriptions.length === 0) {
        setSubscribedPodcasters([]);
        return;
      }
      
      setPodcastersLoading(true);
      try {
        const podcasterPromises = podcastSubscriptions.map(podcastName =>
          fetchWithFallback(
            () => getPodcastByName(podcastName),
            null,
            `getPodcastByName(${podcastName})`
          ).catch(() => null)
        );
        
        const podcasters = await Promise.all(podcasterPromises);
        setSubscribedPodcasters(podcasters.filter((p): p is Podcast => p !== null));
      } catch (error) {
        console.error('[ProfilePage] Failed to fetch podcasters:', error);
        setSubscribedPodcasters([]);
      } finally {
        setPodcastersLoading(false);
      }
    };
    
    fetchPodcasters();
  }, [podcastSubscriptions]);

  // Fetch bookmarked episodes
  useEffect(() => {
    const fetchBookmarkedEpisodes = async () => {
      if (episodeBookmarks.length === 0) {
        setBookmarkedEpisodes([]);
        setBookmarkedEpisodesLoading(false);
        return;
      }
      
      setBookmarkedEpisodesLoading(true);
      try {
        // Parse episode IDs (format: "{podcast_name}_{episode_id}")
        const episodePromises = episodeBookmarks.map(async (bookmarkId) => {
          const [podcastName, ...episodeIdParts] = bookmarkId.split('_');
          const episodeId = episodeIdParts.join('_');
          
          try {
            const episode = await fetchWithFallback(
              () => getEpisodeById(podcastName, episodeId),
              null,
              `getEpisodeById(${podcastName}, ${episodeId})`
            );
            return episode;
          } catch (error) {
            console.error(`Failed to fetch episode ${bookmarkId}:`, error);
            return null;
          }
        });
        
        const episodes = await Promise.all(episodePromises);
        const validEpisodes = episodes.filter((e): e is ApiEpisode => e !== null);
        const transformed = validEpisodes.map(transformApiEpisodeToMock);
        setBookmarkedEpisodes(transformed);
      } catch (error) {
        console.error('[ProfilePage] Failed to fetch bookmarked episodes:', error);
        setBookmarkedEpisodes([]);
      } finally {
        setBookmarkedEpisodesLoading(false);
      }
    };
    
    fetchBookmarkedEpisodes();
  }, [episodeBookmarks]);

  const handleTickerClick = (symbol: string) => {
    const ticker = symbol.split('.')[0];
    navigate(`/stock/${ticker}`);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950">
      <Header />
      
      <div className="flex-1 overflow-y-auto pb-12">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Profile Header Card */}
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 mb-8">
            <CardContent className="p-8">
              {userLoading ? (
                <div className="flex items-center gap-6">
                  <div className="w-24 h-24 rounded-full bg-slate-200 dark:bg-slate-700 animate-pulse" />
                  <div className="flex-1">
                    <div className="h-8 w-48 bg-slate-200 dark:bg-slate-700 rounded animate-pulse mb-2" />
                    <div className="h-4 w-64 bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
                  </div>
                </div>
              ) : userInfo ? (
                <div className="flex items-center gap-6">
                  {/* Avatar */}
                  {userInfo.avatar ? (
                    <img 
                      src={userInfo.avatar} 
                      alt={userInfo.name}
                      className="w-24 h-24 rounded-full object-cover shadow-lg"
                    />
                  ) : (
                    <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-amber-500 to-purple-600 flex items-center justify-center text-white text-3xl font-bold shadow-lg">
                      {getUserInitials(userInfo.name)}
                    </div>
                  )}
                  
                  {/* User Info */}
                  <div>
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-2">{userInfo.name}</h1>
                    <div className="flex items-center gap-4 text-slate-500 dark:text-slate-400 text-sm">
                      <span className="flex items-center gap-1">
                        <Mail size={14} />
                        {userInfo.email}
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Calendar size={14} />
                        {formatJoinDate(userInfo.created_at)} 加入
                      </span>
                      {userInfo.email_verified && (
                        <>
                          <span>•</span>
                          <span className="text-green-500 dark:text-green-400 text-xs">已驗證</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-slate-500 dark:text-slate-400">
                  <p className="mb-2">請先登入以查看個人資料</p>
                  <button
                    onClick={() => navigate('/')}
                    className="text-amber-500 hover:text-amber-600 dark:text-amber-400 dark:hover:text-amber-300 underline"
                  >
                    前往首頁登入
                  </button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Watchlist Section (Stocks) */}
          <div className="mb-8">
            <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50 mb-4">
              <Star className="text-amber-500" size={20} />
              自選股票
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {stocksLoading ? (
                <div className="col-span-full text-center py-8 text-slate-500">載入中...</div>
              ) : savedStocks.length > 0 ? (
                savedStocks.map((stock) => (
                  <StockCardItem 
                    key={stock.symbol}
                    stock={stock} 
                    onSelect={handleTickerClick} 
                    showMentions={true}
                    showSparkline={false}
                    variant="horizontal"
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md"
                  />
                ))
              ) : (
                <div className="col-span-full text-center py-8 text-slate-500">
                  尚未加入任何自選標的
                </div>
              )}
            </div>

            {/* Add to Watchlist Button */}
            <button 
              onClick={() => setIsSearchOpen(true)}
              className="w-full"
            >
              <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 border-dashed hover:border-amber-500 dark:hover:border-amber-500/50 transition-colors">
                <CardContent className="p-8 flex flex-col items-center justify-center text-slate-400 dark:text-slate-600 hover:text-amber-500 dark:hover:text-amber-400 cursor-pointer transition-colors">
                  <Plus size={32} className="mb-2" />
                  <span className="text-sm font-medium">新增自選</span>
                </CardContent>
              </Card>
            </button>
          </div>

          {/* Subscribed Podcasters Section */}
          <div className="mb-8">
            <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50 mb-4">
              <Mic className="text-amber-500" size={20} />
              訂閱的 Podcast
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {podcastersLoading ? (
                <div className="col-span-full text-center py-8 text-slate-500">載入中...</div>
              ) : subscribedPodcasters.length > 0 ? (
                subscribedPodcasters.map((podcaster) => {
                  const getPodcastStyle = (name: string) => {
                    if (name.includes('股癌')) {
                      return { avatar: 'IMG', colorClass: 'bg-slate-200 text-slate-600' };
                    } else if (name.includes('財報狗')) {
                      return { avatar: '狗', colorClass: 'bg-indigo-100 text-indigo-600' };
                    }
                    const initials = name.substring(0, 2).toUpperCase();
                    return { avatar: initials, colorClass: 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300' };
                  };
                  const style = getPodcastStyle(podcaster.name);
                  
                  return (
                    <Card
                      key={podcaster.name}
                      className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 cursor-pointer hover:border-amber-500 dark:hover:border-amber-500/50 transition-colors"
                      onClick={() => navigate(`/podcaster/${encodeURIComponent(podcaster.name)}`)}
                    >
                      <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                          <div className={`w-16 h-16 rounded-xl flex items-center justify-center text-xl font-bold ${style.colorClass}`}>
                            {style.avatar}
                          </div>
                          <div className="flex-1">
                            <h3 className="font-bold text-slate-900 dark:text-slate-50 mb-1">{podcaster.name}</h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400">點擊查看節目</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })
              ) : (
                <div className="col-span-full text-center py-8 text-slate-500">
                  尚未訂閱任何 Podcast
                </div>
              )}
            </div>
          </div>

          {/* Bookmarked Episodes Section */}
          <div className="mb-8">
            <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50 mb-4">
              <Bookmark className="text-amber-500" size={20} />
              收藏的集數
            </h2>
            
            <div className="space-y-4">
              {bookmarkedEpisodesLoading ? (
                <div className="text-center py-8 text-slate-500">載入中...</div>
              ) : bookmarkedEpisodes.length > 0 ? (
                bookmarkedEpisodes.map(episode => (
                  <EpisodeCard key={episode.id} episode={episode} />
                ))
              ) : (
                <div className="text-center py-8 text-slate-500">目前沒有收藏的集數</div>
              )}
            </div>
          </div>

          {/* Tag Subscriptions Section */}
          <div className="mb-8">
            <h2 className="text-xl font-bold flex items-center gap-2 text-slate-900 dark:text-slate-50 mb-4">
              <Tag className="text-amber-500" size={20} />
              訂閱的標籤
            </h2>
            
            <div className="flex flex-wrap gap-2">
              {tagSubscriptions.length > 0 ? (
                tagSubscriptions.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => navigate(`/tag/${encodeURIComponent(tag.replace('#', ''))}`)}
                    className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-500/20 hover:text-amber-600 dark:hover:text-amber-400 transition-colors font-medium"
                  >
                    {tag.startsWith('#') ? tag : `#${tag}`}
                  </button>
                ))
              ) : (
                <div className="w-full text-center py-8 text-slate-500">
                  尚未訂閱任何標籤
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Footer />

      {/* Stock Search Modal */}
      <Modal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        title="新增自選標的"
      >
        <div className="p-4 border-b border-slate-100 dark:border-slate-800">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              placeholder="搜尋台股代號或名稱..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-slate-900 dark:text-slate-50"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {filteredStocks.length > 0 ? (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {filteredStocks.map((stock) => {
                const isSelected = (apiWatchlist.length > 0 ? apiWatchlist : watchlist).includes(stock.symbol);
                return (
                  <div 
                    key={stock.symbol}
                    onClick={async () => {
                      await toggleWatchlist(stock.symbol);
                      // Refresh API watchlist after toggle
                      if (token) {
                        try {
                          const updatedWatchlist = await userApi.getWatchlist();
                          setApiWatchlist(updatedWatchlist);
                        } catch (error) {
                          console.error('Failed to refresh watchlist:', error);
                        }
                      }
                    }}
                    className="flex items-center justify-between p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                  >
                    <div>
                      <div className="font-bold text-slate-900 dark:text-slate-50">{stock.symbol}</div>
                      <div className="text-sm text-slate-500">{stock.name}</div>
                    </div>
                    <button
                      className={`p-2 rounded-full transition-colors ${
                        isSelected 
                          ? 'text-amber-500 bg-amber-50 dark:bg-amber-500/10' 
                          : 'text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                    >
                      <Star size={20} fill={isSelected ? "currentColor" : "none"} />
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-8 text-center text-slate-500">
              沒有找到符合的標的
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default ProfilePage;

