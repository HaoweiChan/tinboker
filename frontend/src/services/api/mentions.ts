/**
 * Podcast mention + post-mention performance API (TKB-001).
 *
 * Thin wrappers over /api/tickers/{ticker}/mentions and
 * /api/episodes/{episode_id}/mentions, validated with Zod. Every response
 * carries a zh-TW non-investment-advice disclaimer that the UI must render.
 */
import { apiClient } from './client';
import {
  TickerMentionsResponseSchema,
  EpisodeMentionsResponseSchema,
  parseResponse,
} from '../../validation/schemas';
import type {
  TickerMentionsResponse,
  EpisodeMentionsResponse,
} from '../../validation/schemas';

export type {
  MentionPerformance,
  ContentMention,
  TickerMentionsResponse,
  EpisodeMentionsResponse,
} from '../../validation/schemas';

/** Podcast mentions of one ticker with post-mention 1/5/20/60 trading-day returns. */
export async function getTickerMentions(
  ticker: string,
  limit: number = 50,
): Promise<TickerMentionsResponse> {
  const response = await apiClient.get(
    `/api/tickers/${encodeURIComponent(ticker.toUpperCase())}/mentions`,
    { params: { limit } },
  );
  return parseResponse(TickerMentionsResponseSchema, response.data);
}

/** All ticker + sector mentions extracted from one episode, with performance. */
export async function getEpisodeMentions(episodeId: string): Promise<EpisodeMentionsResponse> {
  const response = await apiClient.get(
    `/api/episodes/${encodeURIComponent(episodeId)}/mentions`,
  );
  return parseResponse(EpisodeMentionsResponseSchema, response.data);
}
