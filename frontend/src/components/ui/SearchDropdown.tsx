import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, TrendingUp, Mic, Hash, Clock, Tag } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useAppStore } from '@/store/useAppStore';
import { StockLogo } from '@/components/common/StockLogo';
import { PodcastAvatar } from '@/components/common/PodcastAvatar';
import { useSearchHistory } from '@/hooks/useSearchHistory';
import { useAdaptiveDebounce } from '@/hooks/useAdaptiveDebounce';
import { getSuggestions, getPopularSearches, type SearchResponse, type SearchResultItem } from '@/services/api/search';

interface SearchUIResult {
  id: string;
  type: 'stock' | 'podcast' | 'episode' | 'tag';
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  link: string;
}

interface SearchDropdownProps {
  mode?: 'desktop' | 'mobile'; // Kept for compatibility but we mainly handle responsiveness internally now
}

import { trackClick } from '@/services/api/analytics';

export const SearchDropdown: React.FC<SearchDropdownProps> = () => {
  const searchQuery = useAppStore((state) => state.searchQuery);
  const setSearchQuery = useAppStore((state) => state.setSearchQuery);

  // Use dedicated hook for search history
  const { history: recentSearches, addToHistory: addRecentSearch, clearHistory: clearRecentSearches } = useSearchHistory();

  // Adaptive debounce: 50ms for prefixes (<=2 chars), 150ms for longer queries
  const debouncedQuery = useAdaptiveDebounce(searchQuery, 50, 150);

  const [isOpen, setIsOpen] = useState(false);
  const [results, setResults] = useState<SearchUIResult[]>([]);
  const [popularData, setPopularData] = useState<SearchResponse | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      // Only close if it's NOT the mobile overlay (which covers screen)
      // Check if we are in desktop mode (md screen)
      if (window.innerWidth >= 768 && dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch popular data when overlay opens
  useEffect(() => {
    if (isOpen && !popularData) {
      getPopularSearches().then(setPopularData).catch(console.error);
    }
  }, [isOpen, popularData]);

  // Instant Search Logic (Typeahead)
  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setResults([]);
      return;
    }

    const performInstantSearch = async () => {
      try {
        // Use the lightweight suggestions API
        const data = await getSuggestions(debouncedQuery.toLowerCase().trim());
        const flatResults: SearchUIResult[] = [];

        // Stocks
        data.stocks.forEach(item => {
          flatResults.push({
            id: item.id,
            type: 'stock',
            title: item.title,
            subtitle: item.subtitle,
            icon: <StockLogo symbol={item.title} logoUrl={item.icon_url} size="sm" className="w-full h-full rounded-md" />,
            link: item.link
          });
        });

        // Podcasts
        data.podcasts.forEach(item => {
          flatResults.push({
            id: item.id,
            type: 'podcast',
            title: item.title,
            subtitle: item.subtitle,
            icon: <PodcastAvatar name={item.title} src={item.icon_url} size="sm" className="w-full h-full" />,
            link: item.link
          });
        });

        // Episodes (limit to top 2 for suggestions to keep UI clean)
        data.episodes.slice(0, 2).forEach(item => {
          flatResults.push({
            id: item.id,
            type: 'episode',
            title: item.title,
            subtitle: item.subtitle,
            icon: item.icon_url ?
              <img src={item.icon_url} alt="" className="w-4 h-4 rounded-sm object-cover" /> :
              <Mic size={16} className="text-accent-info" />,
            link: item.link
          });
        });

        // Tags
        data.tags.forEach(item => {
          flatResults.push({
            id: item.id,
            type: 'tag',
            title: item.title,
            subtitle: item.subtitle,
            icon: <Hash size={16} className="text-indigo-400" />,
            link: item.link
          });
        });

        setResults(flatResults);
      } catch (error) {
        console.error('[SearchDropdown] Search error:', error);
        // Don't clear results on error to avoid flickering (keep stale data)
      }
    };

    performInstantSearch();
  }, [debouncedQuery]);

  const handleResultClick = (result: SearchUIResult) => {
    // Analytics
    if (result.type === 'stock' || result.type === 'podcast') {
      // Extract ID properly. result.id is like "stock-2330" or "podcast-gooaye"
      const realId = result.id.replace(/^(stock|podcast)-/, '');
      trackClick({ type: result.type, id: realId });
    }

    addRecentSearch(searchQuery || result.title);
    navigate(result.link);
    setSearchQuery('');
    setIsOpen(false);
  };

  const handlePopularItemClick = (item: SearchResultItem) => {
    // Analytics
    if (item.type === 'stock' || item.type === 'podcast') {
      // Extract ID properly (item.id usually follows same convention "stock-xxx")
      const realId = item.id.replace(/^(stock|podcast)-/, '');
      trackClick({ type: item.type, id: realId });
    }

    addRecentSearch(item.title);
    navigate(item.link);
    setSearchQuery('');
    setIsOpen(false);
  };

  const handleRecentClick = (query: string) => {
    setSearchQuery(query);
    // Don't close, let the search execute
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setIsOpen(true);
  };

  const handleInputFocus = () => {
    setIsOpen(true);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (results.length > 0) {
        // If we have instant suggestions, pick the first one
        handleResultClick(results[0]);
      } else if (searchQuery.trim()) {
        // Fallback to full search / main search results page
        // For now, we just add to recent and close, 
        // but typically you'd navigate to `/search?q=...`
        addRecentSearch(searchQuery);
        setIsOpen(false);
      }
    }
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  /* -------------------------------------------------------------------------- */
  /*                            RENDER HELPER: RESULTS LIST                     */
  /* -------------------------------------------------------------------------- */
  const renderResultsList = (items: SearchUIResult[]) => (
    <div className="space-y-1">
      {items.map((result) => (
        <button
          key={result.id}
          onClick={() => handleResultClick(result)}
          className="w-full p-4 flex items-center gap-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 rounded-xl transition-colors text-left"
        >
          <div className="w-10 h-10 flex items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 overflow-hidden shrink-0">
            {result.icon}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-slate-900 dark:text-slate-50 text-base truncate">{result.title}</p>
            {result.subtitle && (
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{result.subtitle}</p>
            )}
          </div>
          <span className="text-xs text-slate-500 px-2.5 py-1 rounded-md bg-slate-100 dark:bg-slate-800">
            {result.type === 'stock' ? '股票' :
              result.type === 'podcast' ? '頻道' :
                result.type === 'episode' ? '集數' : '標籤'}
          </span>
        </button>
      ))}
    </div>
  );


  /* -------------------------------------------------------------------------- */
  /*                            RENDER HELPER: OVERLAY CONTENT                  */
  /* -------------------------------------------------------------------------- */
  // Modified to take a prop so we don't enforce scrollbar on desktop
  const renderOverlayContent = (isMobileView: boolean = false) => (
    <div className={isMobileView ? "mt-4 overflow-y-auto flex-1 pb-20" : "space-y-8 px-1"}>
      {/* SHOW RESULTS */}
      {searchQuery.trim() ? (
        results.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            <Search size={32} className="mx-auto mb-3 opacity-50" />
            <p>找不到「{searchQuery}」的相關結果</p>
          </div>
        ) : (
          renderResultsList(results)
        )
      ) : (
        /* SHOW RECENT & POPULAR CATEGORIES */
        <div className={isMobileView ? "space-y-8 px-1" : "space-y-6"}>
          {/* Recent Searches */}
          {recentSearches.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <h3 className="text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
                  <Clock size={16} /> 最近搜尋
                </h3>
                <button
                  onClick={clearRecentSearches}
                  className="text-slate-400 hover:text-red-500 text-xs transition-colors"
                >
                  清除
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {recentSearches.map((query, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleRecentClick(query)}
                    className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg text-sm text-slate-700 dark:text-slate-300 transition-colors"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Popular Categories */}
          {popularData && (
            <>
              {/* Stocks */}
              {popularData.stocks.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5 text-sm">
                    <TrendingUp size={16} /> 熱門標的
                  </h3>
                  <div className="grid grid-cols-1 gap-2">
                    {popularData.stocks.map((item) => (
                      <button key={item.id} onClick={() => handlePopularItemClick(item)} className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/30 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-left">
                        <div className="w-8 h-8 rounded-lg overflow-hidden shrink-0">
                          <StockLogo symbol={item.subtitle || item.title} logoUrl={item.icon_url} size="sm" className="w-full h-full" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-900 dark:text-slate-50">{item.title}</p>
                          <p className="text-xs text-slate-500">{item.subtitle}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Podcasts */}
              {popularData.podcasts.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5 text-sm">
                    <Mic size={16} /> 熱門頻道
                  </h3>
                  <div className="grid grid-cols-1 gap-2">
                    {popularData.podcasts.map((item) => (
                      <button key={item.id} onClick={() => handlePopularItemClick(item)} className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/30 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-left">
                        <div className="w-8 h-8 rounded-lg overflow-hidden shrink-0">
                          <PodcastAvatar name={item.title} src={item.icon_url} size="sm" className="w-full h-full" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-slate-900 dark:text-slate-50">{item.title}</p>
                          <p className="text-xs text-slate-500">{item.subtitle}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Tags */}
              {popularData.tags.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5 text-sm">
                    <Tag size={16} /> 熱門標籤
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {popularData.tags.map((item) => (
                      <button key={item.id} onClick={() => handlePopularItemClick(item)} className="px-3 py-1.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 rounded-lg text-sm font-medium hover:bg-indigo-100 dark:hover:bg-indigo-900/30 transition-colors">
                        #{item.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

        </div>
      )}
    </div>
  );


  return (
    <div className="relative w-full" ref={dropdownRef}>

      {/* 1. DESKTOP INPUT: Visible on Desktop, Standard Behavior */}
      <div className="relative w-full group hidden md:block">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search className="h-5 w-5 text-slate-400 group-focus-within:text-accent-info transition-colors" />
        </div>
        <Input
          type="text"
          value={searchQuery}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          placeholder="搜尋節目、代號 (2330)..."
          className="w-full pl-10 pr-10 py-5 rounded-full bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-200 placeholder:text-slate-500 focus:bg-white dark:focus:bg-slate-800 focus:border-accent-info focus:ring-1 focus:ring-accent-info transition-all text-base"
        />
        {searchQuery && (
          <button
            onClick={() => {
              setSearchQuery('');
              setIsOpen(false);
            }}
            className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-accent-info transition-colors z-10"
            aria-label="清除搜尋"
          >
            <X className="h-5 w-5" />
          </button>
        )}

        {/* Desktop Dropdown */}
        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden z-50 max-h-96 overflow-y-auto">
            {searchQuery.trim() ? (
              results.length === 0 ? (
                <div className="p-6 text-center text-slate-500">
                  <Search size={24} className="mx-auto mb-2 opacity-50" />
                  <p>找不到「{searchQuery}」的相關結果</p>
                </div>
              ) : (
                <div className="max-h-96 overflow-y-auto">
                  {renderResultsList(results)}
                </div>
              )
            ) : (
              <div className="p-4">
                {/* Desktop: Pass false to avoid internal scroller */}
                {renderOverlayContent(false)}
              </div>
            )}
          </div>
        )}
      </div>


      {/* 2. MOBILE FAKE INPUT: Visible on Mobile, Triggers Overlay */}
      <div className="md:hidden w-full">
        <button
          onClick={() => setIsOpen(true)}
          className="w-full flex items-center gap-3 px-2 py-2.5 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-500 dark:text-slate-400"
        >
          <Search className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm truncate">搜尋節目、代號...</span>
        </button>
      </div>


      {/* 3. MOBILE OVERLAY: Fixed Full Screen with safe area support */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] bg-white dark:bg-slate-900 animate-in fade-in slide-in-from-top-5 duration-200 flex flex-col md:hidden" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
          <div className="flex items-center gap-3 flex-shrink-0 px-4 pt-4 pb-2">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-slate-400" />
              </div>
              <Input
                autoFocus
                type="text"
                value={searchQuery}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="搜尋節目、代號 (2330)..."
                className="w-full pl-10 pr-10 py-3 rounded-xl bg-slate-100 dark:bg-slate-800 border-none text-slate-900 dark:text-slate-200 focus:ring-2 focus:ring-accent-info text-base"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 active:text-accent-info"
                >
                  <X className="h-5 w-5" />
                </button>
              )}
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-500 font-medium px-2 shrink-0"
            >
              取消
            </button>
          </div>

          {/* Mobile scrollable content area with safe bottom padding */}
          <div className="flex-1 overflow-y-auto overscroll-contain px-4" style={{ paddingBottom: 'max(env(safe-area-inset-bottom, 20px), 20px)' }}>
            {renderOverlayContent(false)}
          </div>
        </div>
      )}
    </div>
  );
};
