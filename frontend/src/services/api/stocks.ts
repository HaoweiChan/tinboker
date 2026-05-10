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
  let validated = parseResponse(CompanyDetailSchema, response.data);
  // When backend returns zeros (snapshot unavailable), derive from chartData
  if (validated.chartData && validated.chartData.length > 0) {
    const last = validated.chartData[validated.chartData.length - 1];
    if (validated.price === 0 && last.price > 0) {
      validated = { ...validated, price: last.price };
    }
    if (validated.change === 0 && validated.changePercent === 0 && validated.chartData.length >= 2) {
      const prev = validated.chartData[validated.chartData.length - 2];
      if (prev.price > 0 && last.price > 0) {
        const change = last.price - prev.price;
        validated = {
          ...validated,
          change,
          changePercent: (change / prev.price) * 100,
        };
      }
    }
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
