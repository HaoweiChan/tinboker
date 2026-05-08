import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'sonner';
import type { NodeDisplayMode, TimeframeOption, StockEvent } from '@/services/types';
import { userApi } from '@/services/api/user';

interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  initials?: string;
}

interface AppState {
  // Theme
  theme: 'dark' | 'light';
  heroSearchInView: boolean;

  // Auth
  user: User | null;
  token: string | null;

  // Graph visualization
  selectedConcept: string | null;
  selectedCompany: string | null;
  nodeDisplayMode: NodeDisplayMode;
  nodeStyle: 'ghost' | 'solid';
  nodeColorMode: 'company' | 'industry';
  viewMode: 'graph' | 'table';

  // Search
  searchQuery: string;
  recentSearches: string[];

  // Stock overlay
  selectedStocksForOverlay: string[];
  overlayOpen: boolean;
  overlayFullscreen: boolean;
  selectedEvent: string | null;
  overlayTimeframe: TimeframeOption;
  hoveredEvent: StockEvent | null;

  // User preferences
  watchlist: string[];
  alerts: string[];
  subscriptions: string[];
  tagSubscriptions: string[];
  stockColorMode: 'TW' | 'US';
  useMockData: boolean;

  // Theme actions
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;

  // Auth actions
  login: (user: User, token: string) => void;
  logout: () => void;

  // User preference actions
  toggleWatchlist: (ticker: string) => Promise<void>;
  toggleAlert: (ticker: string) => void;
  toggleSubscription: (id: string) => Promise<void>;
  toggleEpisodeBookmark: (podcastName: string, episodeId: string) => Promise<void>;
  toggleTagSubscription: (tagName: string) => Promise<void>;
  setStockColorMode: (mode: 'TW' | 'US') => void;
  toggleUseMockData: () => void;

  // Graph viz actions
  setSelectedConcept: (concept: string | null) => void;
  setSelectedCompany: (ticker: string | null) => void;
  setNodeDisplayMode: (mode: NodeDisplayMode) => void;
  toggleNodeDisplayMode: () => void;
  setNodeStyle: (style: 'ghost' | 'solid') => void;
  setNodeColorMode: (mode: 'company' | 'industry') => void;
  setViewMode: (mode: 'graph' | 'table') => void;
  toggleViewMode: () => void;

  // Search actions
  setSearchQuery: (query: string) => void;
  addRecentSearch: (query: string) => void;
  clearRecentSearches: () => void;
  setHeroSearchInView: (visible: boolean) => void;
  resetSelections: () => void;

  // Overlay actions
  setSelectedStocksForOverlay: (tickers: string[]) => void;
  addStockToOverlay: (ticker: string) => void;
  removeStockFromOverlay: (ticker: string) => void;
  setOverlayOpen: (open: boolean) => void;
  setOverlayFullscreen: (fullscreen: boolean) => void;
  setSelectedEvent: (eventId: string | null) => void;
  setOverlayTimeframe: (timeframe: TimeframeOption) => void;
  setHoveredEvent: (event: StockEvent | null) => void;
  closeOverlay: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'dark',
      heroSearchInView: false,
      user: null,
      token: null,
      selectedConcept: null,
      selectedCompany: null,
      nodeDisplayMode: 'default',
      nodeStyle: 'ghost',
      nodeColorMode: 'company',
      viewMode: 'graph',
      searchQuery: '',
      recentSearches: [],
      selectedStocksForOverlay: [],
      overlayOpen: false,
      overlayFullscreen: false,
      selectedEvent: null,
      overlayTimeframe: '6M',
      hoveredEvent: null,
      watchlist: [],
      alerts: [],
      subscriptions: [],
      tagSubscriptions: [],
      stockColorMode: 'TW',
      useMockData: false,

      toggleTheme: () =>
        set((state) => {
          const newTheme = state.theme === 'dark' ? 'light' : 'dark';
          if (typeof document !== 'undefined') {
            document.documentElement.classList.toggle('dark', newTheme === 'dark');
          }
          return { theme: newTheme };
        }),

      setTheme: (theme) =>
        set(() => {
          if (typeof document !== 'undefined') {
            document.documentElement.classList.toggle('dark', theme === 'dark');
          }
          return { theme };
        }),

      login: (user, token) => set(() => ({ user, token })),
      logout: () => set(() => ({ user: null, token: null })),

      toggleWatchlist: async (ticker) => {
        const token = useAppStore.getState().token;
        const currentWatchlist = useAppStore.getState().watchlist;
        const isInWatchlist = currentWatchlist.includes(ticker);

        useAppStore.setState((state) => ({
          watchlist: isInWatchlist
            ? state.watchlist.filter((t) => t !== ticker)
            : [...state.watchlist, ticker],
        }));

        if (!token) {
          toast.info('登入後可跨裝置同步自選清單', {
            action: { label: '前往登入', onClick: () => window.location.href = '/' },
          });
          return;
        }

        try {
          const result = await userApi.toggleWatchlist(ticker);
          useAppStore.setState((state) => ({
            watchlist: result.is_in_watchlist
              ? [...state.watchlist.filter(t => t !== ticker), ticker]
              : state.watchlist.filter(t => t !== ticker),
          }));
          toast.success(result.is_in_watchlist ? '已加入自選清單' : '已從自選清單移除');
        } catch (error) {
          console.error('Failed to toggle watchlist:', error);
          useAppStore.setState(() => ({ watchlist: currentWatchlist }));
          toast.error('操作失敗，請稍後再試');
        }
      },

      toggleAlert: (ticker) =>
        set((state) => ({
          alerts: state.alerts.includes(ticker)
            ? state.alerts.filter((t) => t !== ticker)
            : [...state.alerts, ticker],
        })),

      toggleSubscription: async (id) => {
        const token = useAppStore.getState().token;
        const currentSubscriptions = useAppStore.getState().subscriptions;
        const isSubscribed = currentSubscriptions.includes(id);

        useAppStore.setState((state) => ({
          subscriptions: isSubscribed
            ? state.subscriptions.filter((i) => i !== id)
            : [...state.subscriptions, id],
        }));

        if (!token) {
          toast.info('登入後可接收訂閱通知', {
            action: { label: '前往登入', onClick: () => window.location.href = '/' },
          });
          return;
        }

        try {
          const result = await userApi.togglePodcastSubscription(id);
          useAppStore.setState((state) => ({
            subscriptions: result.is_subscribed
              ? [...state.subscriptions.filter(s => s !== id), id]
              : state.subscriptions.filter(s => s !== id),
          }));
          toast.success(result.is_subscribed ? '已訂閱 Podcast' : '已取消訂閱');
        } catch (error) {
          console.error('Failed to toggle subscription:', error);
          useAppStore.setState(() => ({ subscriptions: currentSubscriptions }));
          toast.error('訂閱失敗，請稍後再試');
        }
      },

      toggleEpisodeBookmark: async (podcastName: string, episodeId: string) => {
        const token = useAppStore.getState().token;
        if (!token) {
          toast.info('登入後才能收藏集數', {
            action: { label: '前往登入', onClick: () => window.location.href = '/' },
          });
          return;
        }

        try {
          const result = await userApi.toggleEpisodeBookmark(podcastName, episodeId);
          toast.success(result.is_bookmarked ? '已收藏此集數' : '已取消收藏');
        } catch (error) {
          console.error('Failed to toggle episode bookmark:', error);
          if (import.meta.env.DEV) {
            console.warn('[DEV] Using localStorage fallback for bookmarks');
            const storageKey = 'dev-episode-bookmarks';
            const formattedId = `${podcastName}_${episodeId}`;
            const existing = JSON.parse(localStorage.getItem(storageKey) || '[]');
            const idx = existing.indexOf(formattedId);
            if (idx > -1) {
              existing.splice(idx, 1);
              toast.success('已取消收藏 (本地)');
            } else {
              existing.push(formattedId);
              toast.success('已收藏此集數 (本地)');
            }
            localStorage.setItem(storageKey, JSON.stringify(existing));
            return;
          }
          toast.error('收藏失敗，請稍後再試');
        }
      },

      toggleTagSubscription: async (tagName) => {
        const token = useAppStore.getState().token;
        const currentTags = useAppStore.getState().tagSubscriptions;
        const isSubscribed = currentTags.includes(tagName);

        useAppStore.setState((state) => ({
          tagSubscriptions: isSubscribed
            ? state.tagSubscriptions.filter((t) => t !== tagName)
            : [...state.tagSubscriptions, tagName],
        }));

        if (!token) {
          toast.info('登入後可接收標籤相關通知', {
            action: { label: '前往登入', onClick: () => window.location.href = '/' },
          });
          return;
        }

        try {
          const result = await userApi.toggleTagSubscription(tagName);
          useAppStore.setState((state) => ({
            tagSubscriptions: result.is_subscribed
              ? [...state.tagSubscriptions.filter(t => t !== tagName), tagName]
              : state.tagSubscriptions.filter(t => t !== tagName),
          }));
          toast.success(result.is_subscribed ? '已訂閱此標籤' : '已取消訂閱');
        } catch (error) {
          console.error('Failed to toggle tag subscription:', error);
          useAppStore.setState(() => ({ tagSubscriptions: currentTags }));
          toast.error('訂閱失敗，請稍後再試');
        }
      },

      setStockColorMode: (mode) => set(() => ({ stockColorMode: mode })),
      toggleUseMockData: () => set((state) => ({ useMockData: !state.useMockData })),

      setSelectedConcept: (concept) => set(() => ({ selectedConcept: concept })),
      setSelectedCompany: (ticker) => set(() => ({ selectedCompany: ticker })),
      setNodeDisplayMode: (mode) => set(() => ({ nodeDisplayMode: mode })),
      toggleNodeDisplayMode: () =>
        set((state) => {
          const modes: NodeDisplayMode[] = ['default', 'marketCap', 'revenue'];
          const nextIndex = (modes.indexOf(state.nodeDisplayMode) + 1) % modes.length;
          return { nodeDisplayMode: modes[nextIndex] };
        }),
      setNodeStyle: (style) => set(() => ({ nodeStyle: style })),
      setNodeColorMode: (mode) => set(() => ({ nodeColorMode: mode })),
      setViewMode: (mode) => set(() => ({ viewMode: mode })),
      toggleViewMode: () =>
        set((state) => ({ viewMode: state.viewMode === 'graph' ? 'table' : 'graph' })),

      setSearchQuery: (query) => set(() => ({ searchQuery: query })),
      addRecentSearch: (query) =>
        set((state) => {
          if (!query.trim()) return state;
          const newRecent = [query, ...state.recentSearches.filter((q) => q !== query)].slice(0, 5);
          return { recentSearches: newRecent };
        }),
      clearRecentSearches: () => set(() => ({ recentSearches: [] })),
      setHeroSearchInView: (visible) => set(() => ({ heroSearchInView: visible })),
      resetSelections: () => set(() => ({ selectedConcept: null, selectedCompany: null })),

      setSelectedStocksForOverlay: (tickers) => set(() => ({ selectedStocksForOverlay: tickers })),
      addStockToOverlay: (ticker) =>
        set((state) => {
          if (state.selectedStocksForOverlay.includes(ticker)) return state;
          return { selectedStocksForOverlay: [...state.selectedStocksForOverlay, ticker] };
        }),
      removeStockFromOverlay: (ticker) =>
        set((state) => ({
          selectedStocksForOverlay: state.selectedStocksForOverlay.filter((t) => t !== ticker),
        })),
      setOverlayOpen: (open) => set(() => ({ overlayOpen: open })),
      setOverlayFullscreen: (fullscreen) => set(() => ({ overlayFullscreen: fullscreen })),
      setSelectedEvent: (eventId) => set(() => ({ selectedEvent: eventId })),
      setOverlayTimeframe: (timeframe) => set(() => ({ overlayTimeframe: timeframe })),
      setHoveredEvent: (event) => set(() => ({ hoveredEvent: event })),
      closeOverlay: () =>
        set(() => ({
          overlayOpen: false,
          overlayFullscreen: false,
          selectedEvent: null,
          selectedStocksForOverlay: [],
          hoveredEvent: null,
        })),
    }),
    {
      name: 'tinboker-storage',
      partialize: (state) => ({
        theme: state.theme,
        token: state.token,
        user: state.user,
        watchlist: state.watchlist,
        alerts: state.alerts,
        subscriptions: state.subscriptions,
        tagSubscriptions: state.tagSubscriptions,
        stockColorMode: state.stockColorMode,
        useMockData: state.useMockData,
        recentSearches: state.recentSearches,
      }),
    }
  )
);

// Selector hooks for better performance
export const useTheme = () => useAppStore((state) => state.theme);
export const useUser = () => useAppStore((state) => state.user);
export const useLogin = () => useAppStore((state) => state.login);
export const useLogout = () => useAppStore((state) => state.logout);
export const useWatchlist = () => useAppStore((state) => state.watchlist);
export const useAlerts = () => useAppStore((state) => state.alerts);
export const useSubscriptions = () => useAppStore((state) => state.subscriptions);
export const useTagSubscriptions = () => useAppStore((state) => state.tagSubscriptions);
export const useToggleWatchlist = () => useAppStore((state) => state.toggleWatchlist);
export const useToggleAlert = () => useAppStore((state) => state.toggleAlert);
export const useToggleTagSubscription = () => useAppStore((state) => state.toggleTagSubscription);
export const useToggleSubscription = () => useAppStore((state) => state.toggleSubscription);
export const useSelectedConcept = () => useAppStore((state) => state.selectedConcept);
export const useSelectedCompany = () => useAppStore((state) => state.selectedCompany);
export const useNodeDisplayMode = () => useAppStore((state) => state.nodeDisplayMode);
