import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, TrendingUp, Mic, Hash, Clock, Tag } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useAppStore } from '@/store/useAppStore';
import { PodcastAvatar } from '@/components/common/PodcastAvatar';
import { useSearchHistory } from '@/hooks/useSearchHistory';
import { useAdaptiveDebounce } from '@/hooks/useAdaptiveDebounce';
import { getSuggestions, getPopularSearches, type SearchResponse, type SearchResultItem } from '@/services/api/search';
import { getStockLabel } from '@/utils/stockDisplay';

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

const SEARCH_PLACEHOLDER = '搜尋節目、代號…';

const searchInputClass =
  'w-full h-9 pl-9 pr-9 rounded-full bg-muted/50 border border-border text-sm text-foreground placeholder:text-muted-foreground focus:bg-background focus:border-foreground/20 focus-visible:ring-1 focus-visible:ring-foreground/10 focus-visible:ring-offset-0 transition-colors';

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

        // Stocks (no icon — labels only)
        data.stocks.forEach(item => {
          const { primary, secondary } = getStockLabel({
            ticker: item.title,
            name: item.subtitle,
            market: item.market,
          });
          flatResults.push({
            id: item.id,
            type: 'stock',
            title: primary,
            subtitle: secondary,
            icon: null,
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
            icon: <Hash size={16} className="text-accent-info" />,
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
    <div className="space-y-0.5">
      {items.map((result) => (
        <button
          key={result.id}
          onClick={() => handleResultClick(result)}
          className="w-full px-3 py-2 flex items-center gap-2.5 hover:bg-muted/60 rounded-lg transition-colors text-left"
        >
          {result.icon && (
            <div className="w-8 h-8 flex items-center justify-center rounded-md bg-muted text-muted-foreground overflow-hidden shrink-0">
              {result.icon}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="font-medium text-foreground text-sm truncate">{result.title}</p>
            {result.subtitle && (
              <p className="text-2xs text-muted-foreground mt-0.5 truncate">{result.subtitle}</p>
            )}
          </div>
          <span className="text-2xs text-muted-foreground px-2 py-0.5 rounded-md bg-muted shrink-0">
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
    <div className={isMobileView ? "py-2 overflow-y-auto flex-1" : "space-y-5 px-1"}>
      {searchQuery.trim() ? (
        results.length === 0 ? (
          <div className="py-6 text-center text-muted-foreground">
            <Search size={24} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm">找不到「{searchQuery}」的相關結果</p>
          </div>
        ) : (
          renderResultsList(results)
        )
      ) : (
        <div className={isMobileView ? "space-y-5" : "space-y-5"}>
          {recentSearches.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-2xs font-semibold tracking-[0.06em] uppercase text-muted-foreground flex items-center gap-1.5">
                  <Clock size={14} /> 最近搜尋
                </h3>
                <button
                  onClick={clearRecentSearches}
                  className="text-muted-foreground hover:text-destructive text-2xs transition-colors"
                >
                  清除
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {recentSearches.map((query, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleRecentClick(query)}
                    className="px-2.5 py-1 bg-muted hover:bg-muted/80 rounded-full text-xs text-foreground transition-colors"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          )}

          {popularData && (
            <>
              {popularData.stocks.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-2xs font-semibold tracking-[0.06em] uppercase text-muted-foreground flex items-center gap-1.5">
                    <TrendingUp size={14} /> 熱門標的
                  </h3>
                  <div className="grid grid-cols-1 gap-1">
                    {popularData.stocks.map((item) => {
                      const { primary, secondary } = getStockLabel({
                        ticker: item.title,
                        name: item.subtitle,
                        market: item.market,
                      });
                      return (
                        <button key={item.id} onClick={() => handlePopularItemClick(item)} className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-muted/60 transition-colors text-left">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">{primary}</p>
                            {secondary && (
                              <p className="text-2xs text-muted-foreground truncate">{secondary}</p>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {popularData.podcasts.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-2xs font-semibold tracking-[0.06em] uppercase text-muted-foreground flex items-center gap-1.5">
                    <Mic size={14} /> 熱門頻道
                  </h3>
                  <div className="grid grid-cols-1 gap-1">
                    {popularData.podcasts.map((item) => (
                      <button key={item.id} onClick={() => handlePopularItemClick(item)} className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-muted/60 transition-colors text-left">
                        <div className="w-7 h-7 rounded-md overflow-hidden shrink-0">
                          <PodcastAvatar name={item.title} src={item.icon_url} size="sm" className="w-full h-full" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{item.title}</p>
                          <p className="text-2xs text-muted-foreground truncate">{item.subtitle}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {popularData.tags.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-2xs font-semibold tracking-[0.06em] uppercase text-muted-foreground flex items-center gap-1.5">
                    <Tag size={14} /> 熱門標籤
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {popularData.tags.map((item) => (
                      <button key={item.id} onClick={() => handlePopularItemClick(item)} className="px-2.5 py-1 bg-accent-info-soft text-accent-info rounded-full text-xs font-medium hover:opacity-80 transition-opacity">
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

      {/* 1. DESKTOP INPUT */}
      <div className="relative w-full group hidden md:block">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search className="h-4 w-4 text-muted-foreground group-focus-within:text-foreground transition-colors" />
        </div>
        <Input
          type="text"
          value={searchQuery}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          placeholder={SEARCH_PLACEHOLDER}
          className={searchInputClass}
        />
        {searchQuery && (
          <button
            onClick={() => {
              setSearchQuery('');
              setIsOpen(false);
            }}
            className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground hover:text-foreground transition-colors z-10"
            aria-label="清除搜尋"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-1.5 bg-card border border-border rounded-lg shadow-lg overflow-hidden z-50 max-h-80 overflow-y-auto">
            {searchQuery.trim() ? (
              results.length === 0 ? (
                <div className="py-6 text-center text-muted-foreground">
                  <Search size={20} className="mx-auto mb-2 opacity-50" />
                  <p className="text-sm">找不到「{searchQuery}」的相關結果</p>
                </div>
              ) : (
                <div className="p-1.5 max-h-80 overflow-y-auto">
                  {renderResultsList(results)}
                </div>
              )
            ) : (
              <div className="p-3">
                {renderOverlayContent(false)}
              </div>
            )}
          </div>
        )}
      </div>


      {/* 2. MOBILE TRIGGER */}
      <div className="md:hidden w-full">
        <button
          onClick={() => setIsOpen(true)}
          className="w-full flex items-center gap-2 px-3 h-9 bg-muted/50 border border-border rounded-full text-muted-foreground"
        >
          <Search className="h-4 w-4 shrink-0" />
          <span className="text-sm truncate">{SEARCH_PLACEHOLDER}</span>
        </button>
      </div>


      {/* 3. MOBILE PANEL — slide-down below header, not full-screen */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] md:hidden">
          <button
            type="button"
            aria-label="關閉搜尋"
            className="absolute inset-0 bg-background/70 backdrop-blur-[2px]"
            onClick={() => setIsOpen(false)}
          />
          <div
            className="relative bg-background border-b border-border shadow-lg animate-in fade-in slide-in-from-top-2 duration-150"
            style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
          >
            <div className="flex items-center gap-2 px-4 py-2.5">
              <div className="relative flex-1 min-w-0">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-4 w-4 text-muted-foreground" />
                </div>
                <Input
                  autoFocus
                  type="text"
                  value={searchQuery}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={SEARCH_PLACEHOLDER}
                  className={searchInputClass}
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground active:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-sm text-muted-foreground hover:text-foreground px-1 shrink-0 transition-colors"
              >
                取消
              </button>
            </div>
            <div
              className="max-h-[min(60vh,480px)] overflow-y-auto overscroll-contain px-4 pb-4 border-t border-border/60"
              style={{ paddingBottom: 'max(env(safe-area-inset-bottom, 16px), 16px)' }}
            >
              {renderOverlayContent(true)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
