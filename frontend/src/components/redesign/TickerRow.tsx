import React from 'react';
import { cn } from '@/lib/utils';
import type { Sentiment } from '@/lib/sentiment';
import { SentimentChip } from './SentimentChip';
import { Change } from './Change';

export interface TickerRowData {
  symbol: string;            // e.g. 2330.TW, NVDA
  name?: string;             // resolved display_name from translation table (optional)
  sentiment?: Sentiment;     // LLM-derived; chip color follows the active price color mode
  changePercent?: number | null; // price change %; color follows the TW/US convention
  sinceLabel?: string | null;    // e.g. "播出至今" — shown next to changePercent when set
}

interface TickerRowProps {
  ticker: TickerRowData;
  onClick?: () => void;
  className?: string;
}

/** Strip the exchange suffix so "2330.TW" shows as "2330". */
function bareSymbol(symbol: string): string {
  return symbol.replace(/\.[A-Z]+$/i, '');
}

/** Inset row: [name/symbol | sentiment chip | price change %].
 *  When `name` is provided the first cell stacks the localized name (primary)
 *  over the raw ticker symbol (secondary, muted mono). */
export const TickerRow: React.FC<TickerRowProps> = ({ ticker, onClick, className }) => {
  const interactive = typeof onClick === 'function';
  const Tag = interactive ? 'button' : 'div';
  return (
    <Tag
      {...(interactive ? { type: 'button' as const, onClick } : {})}
      className={cn('ticker-row w-full text-left', interactive && 'hover:bg-muted transition-colors', className)}
    >
      {ticker.name ? (
        <span className="ticker-row-label">
          <span className="ticker-row-name">{ticker.name}</span>
          <span className="ticker-row-symbol">{bareSymbol(ticker.symbol)}</span>
        </span>
      ) : (
        <span className="ticker-row-symbol ticker-row-symbol--solo">{bareSymbol(ticker.symbol)}</span>
      )}
      {ticker.sentiment ? <SentimentChip sentiment={ticker.sentiment} /> : <span />}
      <span className="flex items-baseline gap-1 justify-end">
        <Change value={ticker.changePercent} />
        {ticker.sinceLabel && (
          <span className="text-[10px] text-muted-foreground whitespace-nowrap">{ticker.sinceLabel}</span>
        )}
      </span>
    </Tag>
  );
};
