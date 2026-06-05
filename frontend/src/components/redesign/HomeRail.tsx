import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getRecentBuzz, type Podcast, type RecentBuzz } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { RailCard } from './RailCard';
import { SentBar } from './SentBar';
import { SentimentChip } from './SentimentChip';
import { PodMark } from './PodMark';
import { normalizeSentiment, type Sentiment } from '@/lib/sentiment';

const EMPTY_BUZZ: RecentBuzz = { tickers: [], distinct_count: 0, episode_count: 0 };

function TodayPulse({ buzz, fallbackEpisodes }: { buzz: RecentBuzz; fallbackEpisodes: number }) {
  let bull = 0;
  let bear = 0;
  let neutral = 0;
  for (const b of buzz.tickers) {
    const s = normalizeSentiment(b.sentiment_label);
    if (s === 'BULLISH') bull++;
    else if (s === 'BEARISH') bear++;
    else neutral++;
  }
  const total = bull + bear + neutral;
  const dominant: Sentiment = total === 0 ? null : bull >= bear && bull >= neutral ? 'BULLISH' : bear >= neutral ? 'BEARISH' : 'NEUTRAL';
  const episodes = buzz.episode_count || fallbackEpisodes;
  return (
    <RailCard title="今天的市場" sub="近 30 天">
      <div className="flex flex-col gap-3 text-[13px]">
        <div className="flex justify-between">
          <span className="text-muted-foreground">最近 {episodes} 集摘要</span>
          <span className="font-mono font-semibold tabular-nums">{episodes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">提到 {buzz.distinct_count} 檔個股</span>
          <span className="font-mono font-semibold tabular-nums">{buzz.distinct_count}</span>
        </div>
        {dominant && (
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">整體情緒偏</span>
            <SentimentChip sentiment={dominant} />
          </div>
        )}
        {total > 0 && <SentBar bull={bull} neutral={neutral} bear={bear} />}
      </div>
    </RailCard>
  );
}

function TopTickers({ buzz }: { buzz: RecentBuzz }) {
  if (buzz.tickers.length === 0) return null;
  return (
    <RailCard title="這幾天大家在聊" sub="近 30 天提及">
      <div className="flex flex-col">
        {buzz.tickers.slice(0, 6).map((b, i) => (
          <Link
            key={b.ticker}
            to={`/stock/${encodeURIComponent(b.ticker)}`}
            className="grid grid-cols-[18px_1fr_auto] gap-2.5 items-center py-2 border-t border-border first:border-t-0 hover:opacity-80 transition-opacity"
          >
            <span className="font-mono text-[11px] text-muted-foreground text-right">{String(i + 1).padStart(2, '0')}</span>
            <span className="min-w-0 flex items-baseline gap-1.5">
              <span className="text-[13px] font-medium truncate">{b.name || b.ticker}</span>
              {b.name && <span className="font-mono text-[10px] text-muted-foreground shrink-0">{b.ticker}</span>}
            </span>
            <span className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground font-mono tabular-nums">{b.count} 集</span>
              <SentimentChip sentiment={normalizeSentiment(b.sentiment_label)} bare />
            </span>
          </Link>
        ))}
      </div>
    </RailCard>
  );
}

function TopPodcasters({ podcasts }: { podcasts: Podcast[] }) {
  if (podcasts.length === 0) return null;
  return (
    <RailCard title="最近更新" sub="近 30 天集數">
      <div className="flex flex-col">
        {podcasts.slice(0, 5).map((p) => (
          <Link
            key={p.id || p.name}
            to={`/podcaster/${encodeURIComponent(p.name)}`}
            className="grid grid-cols-[28px_1fr_auto] gap-2.5 items-center py-2 border-t border-border first:border-t-0 hover:opacity-80 transition-opacity"
          >
            {p.image_url ? (
              <img src={p.image_url} alt="" className="w-7 h-7 rounded-[6px] object-cover shrink-0" />
            ) : (
              <PodMark label={(p.name || '?').charAt(0)} kind="mute" size={28} />
            )}
            <span className="text-[13px] font-medium truncate">{p.name}</span>
            <span className="text-[11px] text-muted-foreground font-mono tabular-nums">{p.episode_count} 集</span>
          </Link>
        ))}
      </div>
    </RailCard>
  );
}

/** Home page right rail: 今天的市場 / 這幾天大家在聊 / 最近更新.
 *  All three reflect the recent (zh-TW launch) feed — genuine mention counts +
 *  sentiment from /api/episodes/buzz, not the all-time precomputed trending. */
export const HomeRail: React.FC<{ episodeCount: number; podcasts?: Podcast[] }> = ({ episodeCount, podcasts = [] }) => {
  const [buzz, setBuzz] = useState<RecentBuzz>(EMPTY_BUZZ);

  useEffect(() => {
    let alive = true;
    fetchWithFallback<RecentBuzz>(() => getRecentBuzz({ days: 30, limit: 10 }), EMPTY_BUZZ, 'getRecentBuzz:rail')
      .catch(() => EMPTY_BUZZ)
      .then((b) => {
        if (alive) setBuzz(b && Array.isArray(b.tickers) ? b : EMPTY_BUZZ);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <TodayPulse buzz={buzz} fallbackEpisodes={episodeCount} />
      <TopTickers buzz={buzz} />
      <TopPodcasters podcasts={podcasts} />
    </>
  );
};
