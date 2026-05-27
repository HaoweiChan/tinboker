import { apiClient } from './client';

export interface SearchResultItem {
    id: string;
    type: 'stock' | 'podcast' | 'episode' | 'tag';
    title: string;
    subtitle?: string;
    icon_url?: string;
    link: string;
    market?: 'TW' | 'US' | null;
    metadata?: Record<string, any>;
}

export interface SearchResponse {
    stocks: SearchResultItem[];
    podcasts: SearchResultItem[];
    episodes: SearchResultItem[];
    tags: SearchResultItem[];
}

/**
 * Perform unified search
 * @param query Search query
 * @param limit Optional limit per category (default 5)
 */
export async function search(query: string, limit: number = 5): Promise<SearchResponse> {
    if (!query.trim()) {
        return { stocks: [], podcasts: [], episodes: [], tags: [] };
    }

    const response = await apiClient.get<SearchResponse>('/api/search', {
        params: { q: query, limit }
    });

    return response.data;
}

/**
 * Get instant suggestions for autocomplete
 * @param prefix Search prefix
 * @param limit Optional limit (default 8)
 */
export async function getSuggestions(prefix: string, limit: number = 8): Promise<SearchResponse> {
    if (!prefix.trim()) {
        return { stocks: [], podcasts: [], episodes: [], tags: [] };
    }

    const response = await apiClient.get<SearchResponse>('/api/search/suggest', {
        params: { q: prefix, limit }
    });
    return response.data;
}

/**
 * Get popular searches
 */
export async function getPopularSearches(): Promise<SearchResponse> {
    const response = await apiClient.get<SearchResponse>('/api/search/popular');
    return response.data;
}
