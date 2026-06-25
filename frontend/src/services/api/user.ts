import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';
import type { AuthResponse } from './auth';

export const userApi = {
  // Profile — update display name and/or avatar (omit a field to leave it unchanged).
  updateProfile: async (patch: { name?: string; avatar?: string }): Promise<AuthResponse['user']> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    const response = await apiClient.patch<AuthResponse['user']>(
      '/api/user/me',
      patch,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    return response.data;
  },

  // Watchlist
  getWatchlist: async (): Promise<string[]> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.get<{watchlist: string[]}>(
      '/api/user/watchlist',
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data.watchlist;
  },

  toggleWatchlist: async (ticker: string): Promise<{ticker: string, is_in_watchlist: boolean}> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.post<{ticker: string, is_in_watchlist: boolean}>(
      `/api/user/watchlist/${ticker}/toggle`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  // Podcast Subscriptions
  getPodcastSubscriptions: async (): Promise<string[]> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.get<{podcasts: string[]}>(
      '/api/user/subscriptions/podcasts',
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data.podcasts;
  },

  togglePodcastSubscription: async (podcastName: string): Promise<{podcast_name: string, is_subscribed: boolean}> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.post<{podcast_name: string, is_subscribed: boolean}>(
      `/api/user/subscriptions/podcasts/${encodeURIComponent(podcastName)}/toggle`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  // Episode Bookmarks
  getEpisodeBookmarks: async (): Promise<string[]> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    try {
      const response = await apiClient.get<{episodes: string[]}>(
        '/api/user/subscriptions/episodes',
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data.episodes;
    } catch (error) {
      // Dev mode fallback: Use localStorage
      if (import.meta.env.DEV) {
        console.warn('[DEV] API failed, using localStorage fallback for getEpisodeBookmarks');
        const storageKey = 'dev-episode-bookmarks';
        return JSON.parse(localStorage.getItem(storageKey) || '[]');
      }
      throw error;
    }
  },

  toggleEpisodeBookmark: async (podcastName: string, episodeId: string): Promise<{episode_id: string, is_bookmarked: boolean}> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    try {
      const response = await apiClient.post<{episode_id: string, is_bookmarked: boolean}>(
        '/api/user/subscriptions/episodes/toggle',
        { podcast_name: podcastName, episode_id: episodeId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data;
    } catch (error) {
      // Dev mode fallback: Use localStorage
      if (import.meta.env.DEV) {
        console.warn('[DEV] API failed, using localStorage fallback for toggleEpisodeBookmark');
        const storageKey = 'dev-episode-bookmarks';
        const formattedId = `${podcastName}_${episodeId}`;
        const existingBookmarks = JSON.parse(localStorage.getItem(storageKey) || '[]');
        const index = existingBookmarks.indexOf(formattedId);
        
        const isBookmarked = index > -1;
        if (isBookmarked) {
          existingBookmarks.splice(index, 1);
        } else {
          existingBookmarks.push(formattedId);
        }
        
        localStorage.setItem(storageKey, JSON.stringify(existingBookmarks));
        console.log('[DEV] Bookmark toggled locally:', formattedId, '-> bookmarked:', !isBookmarked);
        
        return {
          episode_id: episodeId,
          is_bookmarked: !isBookmarked
        };
      }
      throw error;
    }
  },

  // Tag Subscriptions
  getTagSubscriptions: async (): Promise<string[]> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.get<{tags: string[]}>(
      '/api/user/subscriptions/tags',
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data.tags;
  },

  toggleTagSubscription: async (tagName: string): Promise<{tag_name: string, is_subscribed: boolean}> => {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    
    const response = await apiClient.post<{tag_name: string, is_subscribed: boolean}>(
      `/api/user/subscriptions/tags/${encodeURIComponent(tagName)}/toggle`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },
};

