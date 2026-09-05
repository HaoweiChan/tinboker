import { apiClient } from './client';
import { parseResponse, WeeklyListSchema, WeeklySchema, type Weekly, type WeeklyList } from '../../validation/schemas';

export async function getWeeks(): Promise<WeeklyList> {
  const response = await apiClient.get('/api/weekly');
  return parseResponse(WeeklyListSchema, response.data);
}

export async function getWeek(week: string): Promise<Weekly> {
  const response = await apiClient.get(`/api/weekly/${encodeURIComponent(week)}`, { headers: { 'X-Silent-Error': 'true' } });
  return parseResponse(WeeklySchema, response.data);
}
