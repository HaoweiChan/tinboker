import { apiClient } from './client';
import type { ContentAsset, ContentIndexResponse } from '../types';


export async function getContentIndex(): Promise<ContentIndexResponse> {
  const response = await apiClient.get('/api/content/index');
  if (response.data && Array.isArray((response.data as ContentIndexResponse).tickers)) {
    return response.data as ContentIndexResponse;
  }
  if (Array.isArray(response.data)) {
    return { tickers: response.data as string[] };
  }
  return { tickers: [] };
}

export async function getContentByTicker(ticker: string): Promise<ContentAsset> {
  const response = await apiClient.get(`/api/content/${ticker}`);
  const data = response.data as Partial<ContentAsset> | undefined;
  if (!data || !data.svg_url || !data.article_url) {
    throw new Error('Content asset missing required URLs');
  }
  return {
    ticker: data.ticker || ticker,
    svg_url: data.svg_url,
    article_url: data.article_url,
    ttl_seconds: typeof data.ttl_seconds === 'number' ? data.ttl_seconds : 0,
  };
}
