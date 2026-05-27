import { apiClient } from './client';
import type { StockEvent } from '../types';
import { EventsResponseSchema, StockEventSchema, parseResponse } from '../../validation/schemas';


export async function getSortedNews(sortBy: string = 'date'): Promise<StockEvent[]> {
  const response = await apiClient.get('/api/news', {
    params: { sort_by: sortBy },
  });
  if (Array.isArray(response.data)) {
    return response.data.reduce((acc: StockEvent[], item: any) => {
      const result = StockEventSchema.safeParse(item);
      if (result.success) acc.push(result.data);
      return acc;
    }, []);
  }
  const validated = parseResponse(EventsResponseSchema, response.data);
  return validated.data;
}

export async function getNewsById(newsId: string): Promise<StockEvent> {
  const response = await apiClient.get(`/api/news/${newsId}`);
  if (response.data.data) {
    return response.data.data;
  }
  return response.data;
}

export async function fetchNewsFromMassive(
  ticker: string,
  limit: number = 10
): Promise<any> {
  const response = await apiClient.post(`/api/news/fetch/${ticker}`, null, {
    params: { limit },
  });
  return response.data;
}
