import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'sonner';
import { AxiosError } from 'axios';
import type { NodeDisplayMode, TimeframeOption, StockEvent } from '@/services/types';
import { userApi } from '@/services/api/user';

function isAuthError(error: unknown): boolean {
  if (error instanceof AxiosError && error.response) {
    return error.response.status === 401 || error.response.status === 403;
  }
  return false;
}

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
  refreshToken: string | null;
  isAuthReady: boolean;

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
  episodeBookmarks: string[];
  stockColorMode: 'TW' | 'US';
  fontSize: 'sm' | 'base' | 'lg';
  useMockData: boolean;

  // Theme actions
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;
  setFontSize: (size: 'sm' | 'base' | 'lg') => void;

  // Auth actions
  login: (user: User, token: string, refreshToken?: string) => void;
  logout: () => void;
  setAuthReady: (ready: boolean) => void;

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
      refreshToken: null,
      isAuthReady: false,
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
      episodeBookmarks: [],
      stockColorMode: 'TW',
      fontSize: 'base',
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

      setFontSize: (size) =>
        set(() => {
          if (typeof document !== 'undefined') {
            document.documentElement.style.fontSize = { sm: '14px', base: '16px', lg: '18px' }[size];
          }
          return { fontSize: size };
        }),

      // refreshToken is only overwritten when explicitly provided, so callers
      // that re-issue just an access token (e.g. token re-validation) keep the
      // persisted refresh token intact.
      login: (user, token, refreshToken) =>
        set((state) => ({
          user,
          token,
          refreshToken: refreshToken !== undefined ? refreshToken : state.refreshToken,
        })),
      logout: () => set(() => ({ user: null, token: null, refreshToken: null })),
      setAuthReady: (ready) => set(() => ({ isAuthReady: ready })),

      toggleWatchlist: async (ticker) => {
        const { token, isAuthReady } = useAppStore.getState();
        const currentWatchlist = useAppStore.getState().watchlist;
        const isInWatchlist = currentWatchlist.includes(ticker);

        if (!isAuthReady) {
          toast.info('正在驗證登入狀態，請稍候再試');
          return;
        }

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
          if (isAuthError(error)) {
            useAppStore.getState().logout();
            toast.error('登入已過期，請重新登入', {
              action: { label: '重新登入', onClick: () => window.location.href = '/' },
            });
          } else {
            toast.error('操作失敗，請稍後再試');
          }
        }
      },

      toggleAlert: (ticker) =>
        set((state) => ({
          alerts: state.alerts.includes(ticker)
            ? state.alerts.filter((t) => t !== ticker)
            : [...state.alerts, ticker],
        })),

      toggleSubscription: async (id) => {
        const { token, isAuthReady } = useAppStore.getState();
        const currentSubscriptions = useAppStore.getState().subscriptions;
        const isSubscribed = currentSubscriptions.includes(id);

        if (!isAuthReady) {
          toast.info('正在驗證登入狀態，請稍候再試');
          return;
        }

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
          if (isAuthError(error)) {
            useAppStore.getState().logout();
            toast.error('登入已過期，請重新登入', {
              action: { label: '重新登入', onClick: () => window.location.href = '/' },
            });
          } else {
            toast.error('訂閱失敗，請稍後再試');
          }
        }
      },

      toggleEpisodeBookmark: async (podcastName: string, episodeId: string) => {
        const { token, isAuthReady } = useAppStore.getState();
        const formattedId = `${podcastName}_${episodeId}`;
        const currentBookmarks = useAppStore.getState().episodeBookmarks;
        const isBookmarked = currentBookmarks.includes(formattedId);

        if (!isAuthReady) {
          toast.info('正在驗證登入狀態，請稍候再試');
          return;
        }

        if (!token) {
          toast.info('登入後才能收藏集數', {
            action: { label: '前往登入', onClick: () => window.location.href = '/' },
          });
          return;
        }

        useAppStore.setState((state) => ({
          episodeBookmarks: isBookmarked
            ? state.episodeBookmarks.filter((id) => id !== formattedId)
            : [...state.episodeBookmarks, formattedId],
        }));

        try {
          const result = await userApi.toggleEpisodeBookmark(podcastName, episodeId);
          useAppStore.setState((state) => ({
            episodeBookmarks: result.is_bookmarked
              ? [...state.episodeBookmarks.filter((id) => id !== formattedId), formattedId]
              : state.episodeBookmarks.filter((id) => id !== formattedId),
          }));
          toast.success(result.is_bookmarked ? '已收藏此集數' : '已取消收藏');
        } catch (error) {
          console.error('Failed to toggle episode bookmark:', error);
          useAppStore.setState(() => ({ episodeBookmarks: currentBookmarks }));
          if (isAuthError(error)) {
            useAppStore.getState().logout();
            toast.error('登入已過期，請重新登入', {
              action: { label: '重新登入', onClick: () => window.location.href = '/' },
            });
          } else {
            toast.error('收藏失敗，請稍後再試');
          }
        }
      },

      toggleTagSubscription: async (tagName) => {
        const { token, isAuthReady } = useAppStore.getState();
        const currentTags = useAppStore.getState().tagSubscriptions;
        const isSubscribed = currentTags.includes(tagName);

        if (!isAuthReady) {
          toast.info('正在驗證登入狀態，請稍候再試');
          return;
        }

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
          if (isAuthError(error)) {
            useAppStore.getState().logout();
            toast.error('登入已過期，請重新登入', {
              action: { label: '重新登入', onClick: () => window.location.href = '/' },
            });
          } else {
            toast.error('訂閱失敗，請稍後再試');
          }
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
        refreshToken: state.refreshToken,
        user: state.user,
        watchlist: state.watchlist,
        alerts: state.alerts,
        subscriptions: state.subscriptions,
        tagSubscriptions: state.tagSubscriptions,
        episodeBookmarks: state.episodeBookmarks,
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
export const useEpisodeBookmarks = () => useAppStore((state) => state.episodeBookmarks);
export const useToggleWatchlist = () => useAppStore((state) => state.toggleWatchlist);
export const useToggleAlert = () => useAppStore((state) => state.toggleAlert);
export const useToggleTagSubscription = () => useAppStore((state) => state.toggleTagSubscription);
export const useToggleSubscription = () => useAppStore((state) => state.toggleSubscription);
export const useSelectedConcept = () => useAppStore((state) => state.selectedConcept);
export const useSelectedCompany = () => useAppStore((state) => state.selectedCompany);
export const useNodeDisplayMode = () => useAppStore((state) => state.nodeDisplayMode);
