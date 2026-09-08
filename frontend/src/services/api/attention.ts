import { apiClient } from './client';
import { parseResponse, AttentionSchema, type Attention } from '../../validation/schemas';

/** Home-page attention: narrative tags, most-discussed and rising tickers over rolling
 *  7d / 30d windows (see backend TrendingService.get_attention). */
export async function getAttention(): Promise<Attention> {
  const response = await apiClient.get('/api/episodes/attention');
  return parseResponse(AttentionSchema, response.data);
}
