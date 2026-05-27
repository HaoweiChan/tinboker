import {
  getRecommendationsByTicker as apiByTicker,
  getRecommendationsByPodcaster as apiByPodcaster,
  getMostDiscussedTickers as apiBuzz,
} from '@/services/api';
import type { TickerRecommendation, TickerBuzz } from './types';

export const recommendationService = {
  /**
   * @deprecated Use `getInsightsByTicker` from `@/services/api/podcasts`.
   * Wraps a soft-deprecated backend path (spec § 4.4); removed in Phase B6.
   */
  async getRecommendationsByTicker(
    ticker: string,
    params?: { start_date?: string; end_date?: string }
  ): Promise<TickerRecommendation[]> {
    return apiByTicker(ticker, params);
  },

  /**
   * @deprecated Use `getInsightsByPodcaster` from `@/services/api/podcasts`.
   * Wraps a soft-deprecated backend path (spec § 4.4); removed in Phase B6.
   */
  async getRecommendationsByPodcaster(
    podcasterName: string,
    params?: { start_date?: string; end_date?: string; podcast_slug?: string }
  ): Promise<TickerRecommendation[]> {
    return apiByPodcaster(podcasterName, params);
  },

  /**
   * @deprecated Use `getTrendingTickers` from `@/services/api/podcasts` (calls
   * /api/ticker-insights/trending). Wraps a soft-deprecated backend path per
   * spec § 4.4; will be removed in Phase B6.
   */
  async getMostDiscussedTickers(
    days: number = 30,
    limit: number = 10
  ): Promise<TickerBuzz[]> {
    return apiBuzz({ days, limit });
  },
};
