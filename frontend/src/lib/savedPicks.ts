/** Saved-list keys carry the show so 我的清單 can load a card's show without scanning all. */
export const savedPickKey = (p: { episode_id: string; ticker: string; podcaster?: string | null }) =>
  `${p.episode_id}|${p.ticker}|${p.podcaster || ''}`;
export const savedThemeKey = (cardKey: string) => `theme:${cardKey}`;

/** Shows that have at least one saved card of the given kind. */
export function savedShows(saved: string[], kind: 'stocks' | 'themes'): string[] {
  const names = saved.flatMap((key) => {
    const theme = key.startsWith('theme:');
    if (theme !== (kind === 'themes')) return [];
    // theme:{podcaster}|{theme_key}|{first_ms}  ·  {episode_id}|{ticker}|{podcaster}
    const parts = (theme ? key.slice(6) : key).split('|');
    return [theme ? parts.slice(0, -2).join('|') : parts.slice(2).join('|')];
  });
  return Array.from(new Set(names.filter(Boolean))).sort();
}
