import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getTrendingTickers, type Podcast } from '@/services/api/podcasts';
import type { TickerTrending } from '@/services/types';
import { fetchWithFallback } from '@/services/api/migration';
import { RailCard } from './RailCard';
import { SentBar } from './SentBar';
import { SentimentChip } from './SentimentChip';
import { PodMark } from './PodMark';
import { normalizeSentiment, type Sentiment } from '@/lib/sentiment';

function TodayPulse({ episodeCount, buzz }: { episodeCount: number; buzz: TickerTrending[] }) {
  let bull = 0;
  let bear = 0;
  let neutral = 0;
  for (const b of buzz) {
    const s = normalizeSentiment(b.sentiment_label);
    if (s === 'BULLISH') bull++;
    else if (s === 'BEARISH') bear++;
    else neutral++;
  }
  const total = bull + bear + neutral;
  const dominant: Sentiment = total === 0 ? null : bull >= bear && bull >= neutral ? 'BULLISH' : bear >= neutral ? 'BEARISH' : 'NEUTRAL';
  return (
    <RailCard title="今天的市場" sub="近 7 天">
      <div className="flex flex-col gap-3 text-[13px]">
        <div className="flex justify-between">
          <span className="text-muted-foreground">最近 {episodeCount} 集摘要</span>
          <span className="font-mono font-semibold tabular-nums">{episodeCount}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">提到 {buzz.length} 檔個股</span>
          <span className="font-mono font-semibold tabular-nums">{buzz.length}</span>
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

function TopTickers({ buzz }: { buzz: TickerTrending[] }) {
  if (buzz.length === 0) return null;
  return (
    <RailCard title="這幾天大家在聊" sub="近 7 天提及">
      <div className="flex flex-col">
        {buzz.slice(0, 6).map((b, i) => (
          <Link
            key={b.ticker}
            to={`/stock/${encodeURIComponent(b.ticker)}`}
            className="grid grid-cols-[18px_1fr_auto] gap-2.5 items-center py-2 border-t border-border first:border-t-0 hover:opacity-80 transition-opacity"
          >
            <span className="font-mono text-[11px] text-muted-foreground text-right">{String(i + 1).padStart(2, '0')}</span>
            <span className="font-mono text-[12px] font-medium truncate">{b.ticker}</span>
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
    <RailCard title="本週更新最勤" sub="最近更新">
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

/** Home page right rail: 今天的市場 / 這幾天大家在聊 / 本週更新最勤. */
export const HomeRail: React.FC<{ episodeCount: number; podcasts?: Podcast[] }> = ({ episodeCount, podcasts = [] }) => {
  const [buzz, setBuzz] = useState<TickerTrending[]>([]);

  useEffect(() => {
    let alive = true;
    fetchWithFallback<TickerTrending[]>(() => getTrendingTickers({ days: 30, limit: 10 }), [], 'getTrendingTickers:rail')
      .catch(() => [] as TickerTrending[])
      .then((b) => {
        if (alive) setBuzz(Array.isArray(b) ? b : []);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <TodayPulse episodeCount={episodeCount} buzz={buzz} />
      <TopTickers buzz={buzz} />
      <TopPodcasters podcasts={podcasts} />
    </>
  );
};
