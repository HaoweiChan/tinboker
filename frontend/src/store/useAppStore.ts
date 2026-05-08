import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'sonner';
import type { NodeDisplayMode, TimeframeOption } from '@/services/types';
import type { StockEvent } from '@/services/types';
import { userApi } from '@/services/api/user';
import { playerBroadcast } from '@/services/PlayerBroadcast';
import type { PlayerBroadcastMessage } from '@/services/PlayerBroadcast';

interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  initials?: string;
}

interface TimestampedSection {
  title: string;
  timestampSeconds: number;
  formattedTime: string;
}

interface PlayerState {
  currentEpisodeId: string | null;
  isPlaying: boolean;
  isPlayerVisible: boolean;
  currentEpisodeData: {
    id: string;
    title: string;
    showName: string;
    coverUrl?: string;
    spotifyUri?: string;
    timestampedSections?: TimestampedSection[];
  } | null;
  seekRequest: number | null;

  // Confirmation State
  pendingEpisode: {
    id: string;
    title: string;
    showName: string;
    coverUrl?: string;
    spotifyUri?: string;
  } | null;
  pendingSeek: number | null;
  showPlayerConfirmation: boolean;
}

interface AppState {
  // Theme state
  theme: 'dark' | 'light';
  heroSearchInView: boolean;

  // Player State
  player: PlayerState;
  // Player Actions
  playEpisode: (
    data: { id: string; title: string; showName: string; coverUrl?: string; spotifyUri?: string; timestampedSections?: TimestampedSection[] },
    options?: { seekTo?: number }
  ) => void;
  requestSeek: (seconds: number) => void;
  clearSeekRequest: () => void;
  closePlayer: () => void;

  // Confirmation Actions
  confirmPlay: () => void;
  cancelPlay: () => void;
  closePlayerConfirmation: () => void;

  // Auth state
  user: User | null;
  token: string | null;

  // Selected concept (robotics, ai, energy)
  selectedConcept: string | null;

  // Selected company ticker
  selectedCompany: string | null;

  // Node display mode
  nodeDisplayMode: NodeDisplayMode;

  // Node style (ghost or solid)
  nodeStyle: 'ghost' | 'solid';

  // Node color mode (company icon color or industry color)
  nodeColorMode: 'company' | 'industry';

  // View mode (graph or table)
  viewMode: 'graph' | 'table';

  // Search query
  searchQuery: string;
  recentSearches: string[];

  // Stock Overlay State
  selectedStocksForOverlay: string[];
  overlayOpen: boolean;
  overlayFullscreen: boolean;
  selectedEvent: string | null;
  overlayTimeframe: TimeframeOption;
  hoveredEvent: StockEvent | null;

  // User Preferences
  watchlist: string[];
  alerts: string[];
  subscriptions: string[];
  tagSubscriptions: string[];
  stockColorMode: 'TW' | 'US';
  useMockData: boolean;

  // Actions
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;

  // Auth Actions
  login: (user: User, token: string) => void;
  logout: () => void;

  // User Actions
  toggleWatchlist: (ticker: string) => Promise<void>;
  toggleAlert: (ticker: string) => void;
  toggleSubscription: (id: string) => Promise<void>;
  toggleEpisodeBookmark: (podcastName: string, episodeId: string) => Promise<void>;
  toggleTagSubscription: (tagName: string) => Promise<void>;
  setStockColorMode: (mode: 'TW' | 'US') => void;
  toggleUseMockData: () => void;

  setSelectedConcept: (concept: string | null) => void;
  setSelectedCompany: (ticker: string | null) => void;
  setNodeDisplayMode: (mode: NodeDisplayMode) => void;
  toggleNodeDisplayMode: () => void;
  setNodeStyle: (style: 'ghost' | 'solid') => void;
  setNodeColorMode: (mode: 'company' | 'industry') => void;
  setViewMode: (mode: 'graph' | 'table') => void;
  toggleViewMode: () => void;
  setSearchQuery: (query: string) => void;
  addRecentSearch: (query: string) => void;
  clearRecentSearches: () => void;
  setHeroSearchInView: (visible: boolean) => void;
  resetSelections: () => void;

  // Overlay Actions
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

/**
 * Global application store using Zustand
 * Persists theme preference to localStorage
 */
export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Initial state
      theme: 'dark',
      heroSearchInView: false,

      // Player Initial State
      player: {
        currentEpisodeId: null,
        isPlaying: false,
        isPlayerVisible: false,
        currentEpisodeData: null,
        seekRequest: null,
        pendingEpisode: null,
        pendingSeek: null,
        showPlayerConfirmation: false,
      },
      playEpisode: (data, options) => {
        const currentState = useAppStore.getState();
        
        // Check for conflict: Playing AND different episode
        if (currentState.player.isPlaying && currentState.player.currentEpisodeId !== data.id) {
          set({
            player: {
              ...currentState.player,
              pendingEpisode: data,
              pendingSeek: options?.seekTo || null,
              showPlayerConfirmation: true
            }
          });
          return;
        }

        // No conflict or same episode: Play immediately
        set({
          player: {
            ...currentState.player,
            currentEpisodeId: data.id,
            isPlaying: true,
            isPlayerVisible: true,
            currentEpisodeData: data,
            // If options.seekTo is present, request seek (use ?? to handle seekTo=0 correctly)
            seekRequest: options?.seekTo ?? null,
            // Clear any pending state
            pendingEpisode: null,
            pendingSeek: null,
            showPlayerConfirmation: false
          }
        });

        // Broadcast player open/episode change to other tabs
        playerBroadcast.broadcastPlayerOpen(data);
        
        // If there's a seek request, broadcast it
        if (options?.seekTo !== undefined) {
          playerBroadcast.broadcastSeekRequest(options.seekTo);
        }
      },
      confirmPlay: () => set((state) => {
        const { pendingEpisode, pendingSeek } = state.player;
        if (!pendingEpisode) return state;

        return {
          player: {
            ...state.player,
            currentEpisodeId: pendingEpisode.id,
            isPlaying: true,
            isPlayerVisible: true,
            currentEpisodeData: pendingEpisode,
            seekRequest: pendingSeek,
            pendingEpisode: null,
            pendingSeek: null,
            showPlayerConfirmation: false
          }
        };
      }),
      cancelPlay: () => set((state) => ({
        player: {
          ...state.player,
          pendingEpisode: null,
          pendingSeek: null,
          showPlayerConfirmation: false
        }
      })),
      closePlayerConfirmation: () => set((state) => ({
        player: {
          ...state.player,
          pendingEpisode: null,
          pendingSeek: null,
          showPlayerConfirmation: false
        }
      })),
      requestSeek: (seconds) => {
        set((state) => ({
          player: {
            ...state.player,
            seekRequest: seconds
          }
        }));
        
        // Broadcast seek request to other tabs
        playerBroadcast.broadcastSeekRequest(seconds);
      },
      clearSeekRequest: () => set((state) => ({
        player: {
          ...state.player,
          seekRequest: null
        }
      })),
      closePlayer: () => {
        set((state) => ({
          player: {
            ...state.player,
            isPlaying: false,
            isPlayerVisible: false,
            currentEpisodeData: null,
            seekRequest: null
          }
        }));
        
        // Broadcast player close to other tabs
        playerBroadcast.broadcastPlayerClose();
      },

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

      // Overlay initial state
      selectedStocksForOverlay: [],
      overlayOpen: false,
      overlayFullscreen: false,
      selectedEvent: null,
      overlayTimeframe: '6M',
      hoveredEvent: null,

      // User Preferences initial state
      watchlist: [],
      alerts: [],
      subscriptions: [],
      tagSubscriptions: [],
      stockColorMode: 'TW',
      useMockData: false,

      // Theme actions
      toggleTheme: () =>
        set((state) => {
          const newTheme = state.theme === 'dark' ? 'light' : 'dark';
          // Update HTML class for Tailwind dark mode
          if (typeof document !== 'undefined') {
            if (newTheme === 'dark') {
              document.documentElement.classList.add('dark');
            } else {
              document.documentElement.classList.remove('dark');
            }
          }
          return { theme: newTheme };
        }),

      setTheme: (theme) =>
        set(() => {
          // Update HTML class for Tailwind dark mode
          if (typeof document !== 'undefined') {
            if (theme === 'dark') {
              document.documentElement.classList.add('dark');
            } else {
              document.documentElement.classList.remove('dark');
            }
          }
          return { theme };
        }),

      // Auth actions
      login: (user, token) => set(() => ({ user, token })),
      logout: () => set(() => ({ user: null, token: null })),

      // User Actions
      toggleWatchlist: async (ticker) => {
        const token = useAppStore.getState().token;
        const currentWatchlist = useAppStore.getState().watchlist;
        const isInWatchlist = currentWatchlist.includes(ticker);

        // Optimistic update - immediately update UI
        useAppStore.setState((state) => ({
          watchlist: isInWatchlist
            ? state.watchlist.filter((t) => t !== ticker)
            : [...state.watchlist, ticker],
        }));

        if (!token) {
          // Not authenticated - show prompt to login
          toast.info('登入後可跨裝置同步自選清單', {
            action: {
              label: '前往登入',
              onClick: () => window.location.href = '/',
            },
          });
          return;
        }

        try {
          const result = await userApi.toggleWatchlist(ticker);
          // Ensure state matches backend result
          useAppStore.setState((state) => ({
            watchlist: result.is_in_watchlist
              ? [...state.watchlist.filter(t => t !== ticker), ticker]
              : state.watchlist.filter(t => t !== ticker)
          }));
          // Show success feedback
          toast.success(result.is_in_watchlist ? '已加入自選清單' : '已從自選清單移除');
        } catch (error) {
          console.error('Failed to toggle watchlist:', error);
          // Rollback optimistic update on error
          useAppStore.setState(() => ({
            watchlist: currentWatchlist,
          }));
          toast.error('操作失敗，請稍後再試');
        }
      },

      toggleAlert: (ticker) =>
        set((state) => {
          const inList = state.alerts.includes(ticker);
          return {
            alerts: inList
              ? state.alerts.filter((t) => t !== ticker)
              : [...state.alerts, ticker],
          };
        }),

      toggleSubscription: async (id) => {
        const token = useAppStore.getState().token;
        const currentSubscriptions = useAppStore.getState().subscriptions;
        const isSubscribed = currentSubscriptions.includes(id);

        // Optimistic update
        useAppStore.setState((state) => ({
          subscriptions: isSubscribed
            ? state.subscriptions.filter((i) => i !== id)
            : [...state.subscriptions, id],
        }));

        if (!token) {
          toast.info('登入後可接收訂閱通知', {
            action: {
              label: '前往登入',
              onClick: () => window.location.href = '/',
            },
          });
          return;
        }

        try {
          const result = await userApi.togglePodcastSubscription(id);
          useAppStore.setState((state) => ({
            subscriptions: result.is_subscribed
              ? [...state.subscriptions.filter(s => s !== id), id]
              : state.subscriptions.filter(s => s !== id)
          }));
          toast.success(result.is_subscribed ? '已訂閱 Podcast' : '已取消訂閱');
        } catch (error) {
          console.error('Failed to toggle subscription:', error);
          // Rollback on error
          useAppStore.setState(() => ({
            subscriptions: currentSubscriptions,
          }));
          toast.error('訂閱失敗，請稍後再試');
        }
      },

      toggleEpisodeBookmark: async (podcastName: string, episodeId: string) => {
        const token = useAppStore.getState().token;
        if (!token) {
          toast.info('登入後才能收藏集數', {
            action: {
              label: '前往登入',
              onClick: () => window.location.href = '/',
            },
          });
          return;
        }

        try {
          const result = await userApi.toggleEpisodeBookmark(podcastName, episodeId);
          toast.success(result.is_bookmarked ? '已收藏此集數' : '已取消收藏');
        } catch (error) {
          console.error('Failed to toggle episode bookmark:', error);

          // Dev mode fallback: Use localStorage to simulate bookmarks
          if (import.meta.env.DEV) {
            console.warn('[DEV] Using localStorage fallback for bookmarks');
            const storageKey = 'dev-episode-bookmarks';
            const formattedId = `${podcastName}_${episodeId}`;
            const existingBookmarks = JSON.parse(localStorage.getItem(storageKey) || '[]');
            const index = existingBookmarks.indexOf(formattedId);

            if (index > -1) {
              existingBookmarks.splice(index, 1);
              toast.success('已取消收藏 (本地)');
            } else {
              existingBookmarks.push(formattedId);
              toast.success('已收藏此集數 (本地)');
            }

            localStorage.setItem(storageKey, JSON.stringify(existingBookmarks));
            console.log('[DEV] Bookmark toggled locally:', formattedId);
            return;
          }

          toast.error('收藏失敗，請稍後再試');
        }
      },

      toggleTagSubscription: async (tagName) => {
        const token = useAppStore.getState().token;
        const currentTags = useAppStore.getState().tagSubscriptions;
        const isSubscribed = currentTags.includes(tagName);

        // Optimistic update
        useAppStore.setState((state) => ({
          tagSubscriptions: isSubscribed
            ? state.tagSubscriptions.filter((t) => t !== tagName)
            : [...state.tagSubscriptions, tagName],
        }));

        if (!token) {
          toast.info('登入後可接收標籤相關通知', {
            action: {
              label: '前往登入',
              onClick: () => window.location.href = '/',
            },
          });
          return;
        }

        try {
          const result = await userApi.toggleTagSubscription(tagName);
          useAppStore.setState((state) => ({
            tagSubscriptions: result.is_subscribed
              ? [...state.tagSubscriptions.filter(t => t !== tagName), tagName]
              : state.tagSubscriptions.filter(t => t !== tagName)
          }));
          toast.success(result.is_subscribed ? '已訂閱此標籤' : '已取消訂閱');
        } catch (error) {
          console.error('Failed to toggle tag subscription:', error);
          // Rollback on error
          useAppStore.setState(() => ({
            tagSubscriptions: currentTags,
          }));
          toast.error('訂閱失敗，請稍後再試');
        }
      },

      setStockColorMode: (mode) =>
        set(() => ({ stockColorMode: mode })),

      toggleUseMockData: () =>
        set((state) => ({ useMockData: !state.useMockData })),

      // Selection actions
      setSelectedConcept: (concept) =>
        set(() => ({ selectedConcept: concept })),

      setSelectedCompany: (ticker) =>
        set(() => ({ selectedCompany: ticker })),

      setNodeDisplayMode: (mode) =>
        set(() => ({ nodeDisplayMode: mode })),

      toggleNodeDisplayMode: () =>
        set((state) => {
          const modes: NodeDisplayMode[] = ['default', 'marketCap', 'revenue'];
          const currentIndex = modes.indexOf(state.nodeDisplayMode);
          const nextIndex = (currentIndex + 1) % modes.length;
          return { nodeDisplayMode: modes[nextIndex] };
        }),

      setNodeStyle: (style) =>
        set(() => ({ nodeStyle: style })),

      setNodeColorMode: (mode) =>
        set(() => ({ nodeColorMode: mode })),

      setViewMode: (mode) =>
        set(() => ({ viewMode: mode })),

      toggleViewMode: () =>
        set((state) => ({
          viewMode: state.viewMode === 'graph' ? 'table' : 'graph',
        })),

      setSearchQuery: (query) =>
        set(() => ({ searchQuery: query })),

      addRecentSearch: (query) =>
        set((state) => {
          if (!query.trim()) return state;
          const newRecent = [
            query,
            ...state.recentSearches.filter((q) => q !== query),
          ].slice(0, 5); // Keep max 5
          return { recentSearches: newRecent };
        }),

      clearRecentSearches: () =>
        set(() => ({ recentSearches: [] })),

      setHeroSearchInView: (visible) =>
        set(() => ({ heroSearchInView: visible })),

      resetSelections: () =>
        set(() => ({
          selectedConcept: null,
          selectedCompany: null,
        })),

      // Overlay actions
      setSelectedStocksForOverlay: (tickers) =>
        set(() => ({ selectedStocksForOverlay: tickers })),

      addStockToOverlay: (ticker) =>
        set((state) => {
          if (!state.selectedStocksForOverlay.includes(ticker)) {
            return {
              selectedStocksForOverlay: [...state.selectedStocksForOverlay, ticker],
            };
          }
          return state;
        }),

      removeStockFromOverlay: (ticker) =>
        set((state) => ({
          selectedStocksForOverlay: state.selectedStocksForOverlay.filter((t) => t !== ticker),
        })),

      setOverlayOpen: (open) =>
        set(() => ({ overlayOpen: open })),

      setOverlayFullscreen: (fullscreen) =>
        set(() => ({ overlayFullscreen: fullscreen })),

      setSelectedEvent: (eventId) =>
        set(() => ({ selectedEvent: eventId })),

      setOverlayTimeframe: (timeframe) =>
        set(() => ({ overlayTimeframe: timeframe })),

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
      name: 'tinboker-storage', // localStorage key
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
        recentSearches: state.recentSearches
      }), // Persist auth and user preferences
    }
  )
);


// Setup broadcast listener for cross-tab synchronization
const handleBroadcastMessage = (message: PlayerBroadcastMessage) => {
  const { type, payload } = message;
  
  switch (type) {
    case 'PLAYER_OPEN':
    case 'EPISODE_CHANGE':
      if (payload?.episodeData) {
        useAppStore.setState((state) => ({
          player: {
            ...state.player,
            currentEpisodeId: payload.episodeData!.id,
            isPlaying: true,
            isPlayerVisible: true,
            currentEpisodeData: payload.episodeData!,
            seekRequest: null,
            pendingEpisode: null,
            pendingSeek: null,
            showPlayerConfirmation: false,
          },
        }));
      }
      break;
    
    case 'PLAYER_CLOSE':
      useAppStore.setState((state) => ({
        player: {
          ...state.player,
          isPlaying: false,
          isPlayerVisible: false,
          currentEpisodeData: null,
          seekRequest: null,
        },
      }));
      break;
    
    case 'SEEK_REQUEST':
      if (payload?.seekTo !== undefined) {
        useAppStore.setState((state) => ({
          player: {
            ...state.player,
            seekRequest: payload.seekTo!,
          },
        }));
      }
      break;
  }
};

// Add listener for broadcast messages
playerBroadcast.addListener(handleBroadcastMessage);


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
