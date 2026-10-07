import React, { useEffect, useMemo, useState } from 'react';
import { isAxiosError } from 'axios';
import { ThemeCard } from '@/components/financial/ThemeCard';
import { useTickerWindowReturns, windowReturnsKey } from '@/hooks/useTickerWindowReturns';
import { savedThemeKey } from '@/lib/savedPicks';
import { useAppStore } from '@/store/useAppStore';
import { getThemeCards, type ThemeCardData } from '@/services/api/themeViews';

interface ThemeCardsFeedProps {
  /** 我的 narrows to the member's subscribed shows; 全部 shows every show. */
  scope: 'mine' | 'all' | 'saved';
  /** Shows to load in full: the subscribed ones, the picked ones, or — for 我的清單 —
   *  the ones with a saved theme card.
   *  Empty means the newest themes across every show. */
  shows: string[];
  /** 7 / 30 / 90: only themes first mentioned at least that long ago, best average
   *  return over that window first — the same rule as 個股. null is newest first. */
  period: 7 | 30 | 90 | null;
  podcastImages: Map<string, string | undefined>;
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
  onShowAll: () => void;
}

const PAGE_SIZE = 30;
/** Ranking by return needs every candidate's prices, so cap how many are fetched. */
const RANK_CAP = 120;
const WINDOW = { 7: 'd7', 30: 'd30', 90: 'd90' } as const;

/** The 題材 side of 走勢: themes each show has been talking about, newest run first. */
export const ThemeCardsFeed: React.FC<ThemeCardsFeedProps> = ({ scope, shows, period, podcastImages, onPlaySegment, onShowAll }) => {
  const [cards, setCards] = useState<ThemeCardData[] | null>(null);
  const [error, setError] = useState('');

  const [shown, setShown] = useState(PAGE_SIZE);
  const showsKey = shows.join('\n');

  useEffect(() => { setShown(PAGE_SIZE); }, [period]);

  useEffect(() => {
    const controller = new AbortController();
    const names = showsKey ? showsKey.split('\n') : [];
    setCards(null);
    setError('');
    setShown(PAGE_SIZE);
    // 我訂閱的節目 / 我的清單 with no shows has nothing to load; it must not fall back to every show.
    const load = names.length
      ? Promise.all(names.map((name) => getThemeCards(controller.signal, name))).then((lists) => lists.flat().sort((a, b) => b.latest_ms - a.latest_ms))
      : scope === 'all' ? getThemeCards(controller.signal) : Promise.resolve([]);
    load
      .then(setCards)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(isAxiosError(err) && err.response?.status === 402 ? '題材走勢是會員內容。' : '無法載入題材走勢，請稍後再試。');
      });
    return () => controller.abort();
  }, [showsKey, scope]);

  const savedPicks = useAppStore((st) => st.savedPicks);
  const toggleSavedPick = useAppStore((st) => st.toggleSavedPick);
  const savedSet = useMemo(() => new Set(savedPicks), [savedPicks]);
  const listed = useMemo(
    () => (cards ?? []).filter((c) => scope !== 'saved' || savedSet.has(savedThemeKey(c.key))),
    [cards, scope, savedSet],
  );
  // A period keeps only runs old enough for that window to have come due, and only
  // those with stocks to score.
  const candidates = useMemo(() => {
    if (period === null) return listed;
    const cutoff = Date.now() - period * 86_400_000;
    return listed.filter((c) => c.first_ms <= cutoff && c.tickers.length > 0).slice(0, RANK_CAP);
  }, [listed, period]);
  // Every named company is scored from its card's FIRST mention, not the latest one.
  // Newest-first only needs prices for the cards on screen; ranking needs them all.
  const priced = useMemo(() => (period === null ? candidates.slice(0, shown) : candidates), [candidates, period, shown]);
  const refs = useMemo(
    () => priced.flatMap((c) => c.tickers.map((t) => ({ ticker: t.ticker, reference_ms: c.first_ms }))),
    [priced],
  );
  const windowsMap = useTickerWindowReturns(refs);
  const ranked = useMemo(() => {
    if (period === null) return candidates;
    const key = WINDOW[period];
    const score = (c: ThemeCardData) => {
      const values = c.tickers
        .map((t) => windowsMap.get(windowReturnsKey(t.ticker, c.first_ms))?.[key])
        .filter((v): v is number => v != null && Number.isFinite(v));
      return values.length ? values.reduce((a, b) => a + b, 0) / values.length : Number.NEGATIVE_INFINITY;
    };
    return [...candidates].sort((a, b) => score(b) - score(a));
  }, [candidates, period, windowsMap]);
  const visible = useMemo(() => ranked.slice(0, shown), [ranked, shown]);

  if (error) return <p role="alert" className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">{error}</p>;
  if (cards === null) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />)}
      </div>
    );
  }
  if (visible.length === 0) {
    return (
      <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
        {period !== null && listed.length > 0 ? `還沒有滿 ${period} 天、而且有個股可計算的題材，試試較短的天期或其他節目。` : scope === 'saved' ? '我的清單還沒有題材卡片。點卡片右上角的書籤就會存進來。' : scope === 'all' ? (shows.length ? '這些節目還沒有題材走勢。' : '目前還沒有題材走勢。') : (
          <>你訂閱的節目還沒有題材走勢。<button type="button" onClick={onShowAll} className="text-accent-info hover:underline ml-1">看全部</button></>
        )}
      </div>
    );
  }
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
        {visible.map((card) => (
          <ThemeCard key={card.key} card={card} windowsMap={windowsMap} podcastImage={podcastImages.get(card.podcaster)} onPlaySegment={onPlaySegment} saved={savedSet.has(savedThemeKey(card.key))} onToggleSaved={() => void toggleSavedPick(savedThemeKey(card.key))} className="rounded-md" />
        ))}
      </div>
      {ranked.length > visible.length ? (
        <button
          type="button"
          onClick={() => setShown((n) => n + PAGE_SIZE)}
          className="mt-3 flex min-h-10 w-full items-center justify-center rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
        >
          顯示更多（還有 {ranked.length - visible.length} 個）
        </button>
      ) : (
        <p className="h-10 flex items-center justify-center text-xs text-muted-foreground mt-2">共 {ranked.length} 個題材</p>
      )}
    </>
  );
};

export default ThemeCardsFeed;
