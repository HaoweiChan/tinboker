import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { SentimentChip } from '@/components/redesign';
import { StockIdentity } from '@/components/common/StockIdentity';
import { TickerAvatar } from '@/components/common/TickerAvatar';
import { inferStockMarket } from '@/utils/stockDisplay';
import { useStockSummaries } from '@/hooks/useStockSummaries';
import { getRecentBuzz } from '@/services/api/podcasts';
import type { SentimentLabel, TickerTrending } from '@/services/types';
import type { Sentiment } from '@/lib/sentiment';

// Short market badge per row — mirrors the /stock page table.
const MARKET_BADGE: Record<ReturnType<typeof inferStockMarket>, { label: string; cls: string }> = {
  TW: { label: 'TW', cls: 'bg-sentiment-bull-soft text-sentiment-bull' },
  US: { label: 'US', cls: 'bg-accent-info-soft text-accent-info' },
  KR: { label: 'KR', cls: 'bg-muted text-muted-foreground' },
};

function labelToSentiment(label: SentimentLabel): Sentiment {
  if (label === 'STRONG_BULLISH' || label === 'BULLISH') return 'BULLISH';
  if (label === 'STRONG_BEARISH' || label === 'BEARISH') return 'BEARISH';
  return 'NEUTRAL';
}

/**
 * Watchlist table shared by the profile (desktop) and 收藏 (mobile) pages so the
 * two never drift: the /stock-page row — logo + name + market badge — plus 提及
 * (mention count) and 情緒 (sentiment) from the same recent-buzz feed. Caller
 * guards the empty case; this renders the populated table only.
 */
export const SubscribedTickers: React.FC<{ tickers: string[] }> = ({ tickers }) => {
  const summaries = useStockSummaries(tickers);
  const [buzzMap, setBuzzMap] = useState<Map<string, TickerTrending>>(new Map());

  // The buzz feed is the same top-200 regardless of which tickers we hold, so
  // fetch once when there's anything to annotate (not per-list-change).
  const hasTickers = tickers.length > 0;
  useEffect(() => {
    if (!hasTickers) {
      setBuzzMap(new Map());
      return;
    }
    let alive = true;
    getRecentBuzz({ days: 30, limit: 200 })
      .then((b) => {
        if (alive) setBuzzMap(new Map((b.tickers ?? []).map((t) => [t.ticker, t])));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [hasTickers]);

  return (
    <div className="bg-card border border-border rounded-md overflow-hidden">
      <div className="grid grid-cols-[1fr_52px_60px_22px] gap-2.5 items-center px-4 py-2.5 text-2xs font-medium text-muted-foreground uppercase tracking-[0.04em] border-b border-border font-mono">
        <span>個股</span>
        <span className="text-right">提及</span>
        <span className="text-right">情緒</span>
        <span />
      </div>
      {tickers.map((sym) => {
        const summary = summaries[sym];
        const buzz = buzzMap.get(sym) ?? buzzMap.get(sym.split('.')[0]);
        const badge = MARKET_BADGE[inferStockMarket(sym)];
        return (
          <Link
            key={sym}
            to={`/stock/${encodeURIComponent(sym)}`}
            className="grid grid-cols-[1fr_52px_60px_22px] gap-2.5 items-center px-4 py-3.5 border-b border-border last:border-b-0 hover:bg-muted transition-colors"
          >
            <span className="min-w-0 flex items-center gap-2.5">
              <TickerAvatar ticker={sym} brandColor={summary?.brand_color} />
              <span className="min-w-0 flex items-center gap-1.5">
                <StockIdentity ticker={sym} name={summary?.name} size="md" hideCode />
                <span className={`text-2xs px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 ${badge.cls}`}>{badge.label}</span>
              </span>
            </span>
            <span className="font-mono text-md tabular-nums text-right">{buzz?.count ?? ''}</span>
            <span className="text-right">
              {buzz && <SentimentChip sentiment={labelToSentiment(buzz.sentiment_label)} bare />}
            </span>
            <ChevronRight size={14} className="text-muted-foreground" />
          </Link>
        );
      })}
    </div>
  );
};
