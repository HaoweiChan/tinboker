import { apiClient } from './client';
import type { CompanyDetail, TimeframeOption } from '../types';
import { CompanyDetailSchema, parseResponse } from '../../validation/schemas';


export async function getSortedStocks(options?: {
  sortBy?: string;
  q?: string;
  limit?: number;
}): Promise<any[]> {
  const params: Record<string, any> = {};
  if (options?.sortBy) params.sort_by = options.sortBy;
  if (options?.q) params.q = options.q;
  if (options?.limit) params.limit = options.limit;
  const response = await apiClient.get('/api/stocks', { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function getStockByTicker(
  ticker: string,
  timeframe?: TimeframeOption,
  options?: { silent?: boolean; before?: number }
): Promise<CompanyDetail> {
  const params: Record<string, any> = {};
  if (timeframe) params.timeframe = timeframe;
  if (options?.before) params.before = options.before;
  const config: any = { params };
  if (options?.silent) {
    config.headers = { 'X-Silent-Error': 'true' };
  }
  const response = await apiClient.get(`/api/stocks/${ticker}`, config);
  if (import.meta.env.DEV) {
    console.log('[API] getStockByTicker raw response:', {
      ticker,
      rawData: response.data,
      price: response.data?.price,
      priceType: typeof response.data?.price,
      hasPrice: 'price' in (response.data || {}),
      dataKeys: response.data ? Object.keys(response.data) : [],
      currentPrice: response.data?.current_price,
      lastPrice: response.data?.last_price,
      closePrice: response.data?.close_price,
      latestPrice: response.data?.latest_price,
      chartDataLastPrice: response.data?.chartData && Array.isArray(response.data.chartData) && response.data.chartData.length > 0
        ? response.data.chartData[response.data.chartData.length - 1]?.price
        : undefined,
      fullResponse: JSON.stringify(response.data, null, 2)
    });
  }
  let validated = parseResponse(CompanyDetailSchema, response.data);
  // Backend returns price: 0 sometimes; use last chartData entry's price instead
  if (validated.price === 0 && validated.chartData && validated.chartData.length > 0) {
    const lastDataPoint = validated.chartData[validated.chartData.length - 1];
    if (lastDataPoint?.price && lastDataPoint.price > 0) {
      if (import.meta.env.DEV) {
        console.warn('[API] getStockByTicker: Root price is 0, using price from chartData:', {
          ticker, rootPrice: validated.price, chartDataPrice: lastDataPoint.price,
        });
      }
      validated = { ...validated, price: lastDataPoint.price };
    }
  }
  if (import.meta.env.DEV) {
    console.log('[API] getStockByTicker validated:', {
      ticker, price: validated.price, priceType: typeof validated.price,
    });
  }
  return validated;
}

export async function getStockBasicInfo(ticker: string): Promise<any> {
  const response = await apiClient.get(`/api/stocks/${ticker}/basic`);
  return response.data;
}

export async function getStockHistory(
  ticker: string,
  timeframe?: TimeframeOption
): Promise<{ data: number[] }> {
  const params: Record<string, any> = {};
  if (timeframe) params.timeframe = timeframe;
  const response = await apiClient.get(`/api/stocks/${ticker}/history`, { params });
  if (Array.isArray(response.data)) {
    return { data: response.data };
  }
  if (response.data?.data && Array.isArray(response.data.data)) {
    return { data: response.data.data };
  }
  return { data: [] };
}
