import React, { useEffect, useMemo, useState } from 'react';
import { isAxiosError } from 'axios';
import { ThemeCard } from '@/components/financial/ThemeCard';
import { useTickerWindowReturns } from '@/hooks/useTickerWindowReturns';
import { getThemeCards, type ThemeCardData } from '@/services/api/themeViews';

interface ThemeCardsFeedProps {
  /** 我的 narrows to the member's subscribed shows; 全部 shows every show. */
  scope: 'mine' | 'all';
  /** Shows to load in full: the subscribed ones in 我的, the picked ones in 全部.
   *  Empty means the newest themes across every show. */
  shows: string[];
  podcastImages: Map<string, string | undefined>;
  onPlaySegment?: (episodeId: string, startTimeMs: number) => void;
  onShowAll: () => void;
}

const PAGE_SIZE = 30;

/** The 題材 side of 走勢: themes each show has been talking about, newest run first. */
export const ThemeCardsFeed: React.FC<ThemeCardsFeedProps> = ({ scope, shows, podcastImages, onPlaySegment, onShowAll }) => {
  const [cards, setCards] = useState<ThemeCardData[] | null>(null);
  const [error, setError] = useState('');

  const [shown, setShown] = useState(PAGE_SIZE);
  const showsKey = shows.join('\n');

  useEffect(() => {
    const controller = new AbortController();
    const names = showsKey ? showsKey.split('\n') : [];
    setCards(null);
    setError('');
    setShown(PAGE_SIZE);
    // 我的 with nothing subscribed has nothing to load; it must not fall back to every show.
    const load = names.length
      ? Promise.all(names.map((name) => getThemeCards(controller.signal, name))).then((lists) => lists.flat().sort((a, b) => b.latest_ms - a.latest_ms))
      : scope === 'mine' ? Promise.resolve([]) : getThemeCards(controller.signal);
    load
      .then(setCards)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(isAxiosError(err) && err.response?.status === 402 ? '題材走勢是會員內容。' : '無法載入題材走勢，請稍後再試。');
      });
    return () => controller.abort();
  }, [showsKey, scope]);

  const visible = useMemo(() => (cards ?? []).slice(0, shown), [cards, shown]);
  // Every named company is scored from its card's FIRST mention, not the latest one.
  const refs = useMemo(
    () => visible.flatMap((c) => c.tickers.map((t) => ({ ticker: t.ticker, reference_ms: c.first_ms }))),
    [visible],
  );
  const windowsMap = useTickerWindowReturns(refs);

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
        {scope === 'all' ? (shows.length ? '這些節目還沒有題材走勢。' : '目前還沒有題材走勢。') : (
          <>你訂閱的節目還沒有題材走勢。<button type="button" onClick={onShowAll} className="text-accent-info hover:underline ml-1">看全部</button></>
        )}
      </div>
    );
  }
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
        {visible.map((card) => (
          <ThemeCard key={card.key} card={card} windowsMap={windowsMap} podcastImage={podcastImages.get(card.podcaster)} onPlaySegment={onPlaySegment} className="rounded-md" />
        ))}
      </div>
      {cards.length > visible.length ? (
        <button
          type="button"
          onClick={() => setShown((n) => n + PAGE_SIZE)}
          className="mt-3 flex min-h-10 w-full items-center justify-center rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
        >
          顯示更多（還有 {cards.length - visible.length} 個）
        </button>
      ) : (
        <p className="h-10 flex items-center justify-center text-xs text-muted-foreground mt-2">共 {cards.length} 個題材</p>
      )}
    </>
  );
};

export default ThemeCardsFeed;
