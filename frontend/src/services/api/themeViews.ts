/**
 * Members-only theme cards: themes a show discussed WITH a stance, grouped into runs
 * of consecutive mentions anchored on the first one. See backend routers/theme_views.py.
 */

import { z } from 'zod';
import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

const MentionSchema = z.object({
  episode_id: z.string(),
  episode_number: z.string().nullable(),
  released_at_ms: z.number(),
  /** False when the episode is older than the public window: no page to link to or play. */
  episode_public: z.boolean().default(true),
  stance: z.enum(['bullish', 'bearish', 'mixed']),
  conviction: z.enum(['firm', 'tentative']),
  thesis: z.string(),
  start_ms: z.number().nullable(),
  quote: z.string().nullable(),
});
const ThemeCardSchema = z.object({
  key: z.string(),
  podcaster: z.string(),
  theme_key: z.string(),
  theme_label: z.string(),
  exposure_id: z.string().nullable(),
  first_ms: z.number(),
  latest_ms: z.number(),
  /** Companies the show named as beneficiaries during the run, most-mentioned first;
   *  when it named none, the theme's core members from the taxonomy (`members`). */
  tickers_source: z.enum(['named', 'members', 'none']).default('named'),
  tickers: z.array(z.object({ ticker: z.string(), name: z.string(), mentions: z.number() })),
  /** Oldest first; `mentions[0]` is the call the card is anchored on. */
  mentions: z.array(MentionSchema).min(1),
});
export type ThemeCardData = z.infer<typeof ThemeCardSchema>;
export type ThemeMention = z.infer<typeof MentionSchema>;

/** Newest runs first. Without `podcaster` this is the newest across every show, so one
 *  show's older themes only come back when it is asked for by name. */
export async function getThemeCards(signal?: AbortSignal, podcaster?: string): Promise<ThemeCardData[]> {
  const token = useAppStore.getState().token;
  if (!token) throw new Error('Not authenticated');
  const response = await apiClient.get('/api/theme-views/cards', {
    headers: { Authorization: `Bearer ${token}` }, signal,
    params: podcaster ? { podcaster, limit: 200 } : undefined,
  });
  return z.array(ThemeCardSchema).parse(response.data);
}
