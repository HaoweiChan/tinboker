import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getRecentBuzz, type Podcast, type RecentBuzz } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { RailCard } from './RailCard';
import { SentBar } from './SentBar';
import { SentimentChip } from './SentimentChip';
import { PodMark } from './PodMark';
import { normalizeSentiment } from '@/lib/sentiment';

const EMPTY_BUZZ: RecentBuzz = { tickers: [], distinct_count: 0, episode_count: 0 };

function TrendArrow({ delta }: { delta: number }) {
  if (delta > 0) return <span className="text-sentiment-bull font-mono text-[11px]">↑ +{delta}</span>;
  if (delta < 0) return <span className="text-sentiment-bear font-mono text-[11px]">↓ {delta}</span>;
  return <span className="text-muted-foreground font-mono text-[11px]">→ 0</span>;
}

function MarketPulse({ buzz }: { buzz: RecentBuzz }) {
  // Sentiment from server, fallback to client-side count
  const sent = buzz.sentiment_summary ?? (() => {
    let bull = 0, bear = 0, neutral = 0;
    for (const b of buzz.tickers) {
      const s = normalizeSentiment(b.sentiment_label);
      if (s === 'BULLISH') bull++;
      else if (s === 'BEARISH') bear++;
      else neutral++;
    }
    return { bull, neutral, bear };
  })();
  const total = sent.bull + sent.neutral + sent.bear;
  const prev = buzz.prev_sentiment_summary;
  const bullDelta = prev ? sent.bull - prev.bull : 0;

  return (
    <RailCard title="市場脈動" sub="近 30 天">
      <div className="flex flex-col gap-4 text-[13px]">
        {/* Row 1: Sentiment trend */}
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] text-muted-foreground tracking-wide">情緒趨勢</span>
          {total > 0 && <SentBar bull={sent.bull} neutral={sent.neutral} bear={sent.bear} />}
          <div className="flex items-center justify-between">
            <span>
              <span className="text-sentiment-bull">多 {sent.bull}</span>
              <span className="text-muted-foreground"> · </span>
              <span className="text-muted-foreground">中 {sent.neutral}</span>
              <span className="text-muted-foreground"> · </span>
              <span className="text-sentiment-bear">空 {sent.bear}</span>
            </span>
            {prev && <TrendArrow delta={bullDelta} />}
          </div>
        </div>

        {/* Row 2: Fastest rising ticker */}
        {buzz.rising_ticker && (
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground tracking-wide">聲量飆升</span>
            <Link
              to={`/stock/${encodeURIComponent(buzz.rising_ticker.ticker)}`}
              className="flex items-center justify-between hover:opacity-80 transition-opacity"
            >
              <span className="flex items-baseline gap-1.5 min-w-0">
                <span className="font-medium truncate">{buzz.rising_ticker.name || buzz.rising_ticker.ticker}</span>
                {buzz.rising_ticker.name && (
                  <span className="font-mono text-[10px] text-muted-foreground shrink-0">{buzz.rising_ticker.ticker}</span>
                )}
              </span>
              <span className="text-sentiment-bull font-mono text-[11px] shrink-0">↑ +{buzz.rising_ticker.delta} 集</span>
            </Link>
          </div>
        )}

        {/* Row 3: Newly mentioned tickers */}
        {buzz.new_tickers && buzz.new_tickers.length > 0 && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground tracking-wide">新進個股</span>
              <span className="text-[11px] text-muted-foreground font-mono">+{buzz.new_tickers.length} 檔新上榜</span>
            </div>
            <div className="flex flex-wrap gap-x-1.5 gap-y-0.5 text-[12px]">
              {buzz.new_tickers.map((t, i) => (
                <span key={t.ticker}>
                  <Link to={`/stock/${encodeURIComponent(t.ticker)}`} className="text-foreground/80 hover:text-foreground underline decoration-border hover:decoration-foreground/40 transition-colors">
                    {t.name || t.ticker}
                  </Link>
                  {i < buzz.new_tickers!.length - 1 && <span className="text-muted-foreground">、</span>}
                </span>
              ))}
            </div>
          </div>
        )}
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

/** Home page right rail: 市場脈動 / 這幾天大家在聊 / 最近更新.
 *  All three reflect the recent (zh-TW launch) feed — genuine mention counts +
 *  sentiment from /api/episodes/buzz, not the all-time precomputed trending. */
export const HomeRail: React.FC<{ episodeCount?: number; podcasts?: Podcast[] }> = ({ podcasts = [] }) => {
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
      <MarketPulse buzz={buzz} />
      <TopTickers buzz={buzz} />
      <TopPodcasters podcasts={podcasts} />
    </>
  );
};
