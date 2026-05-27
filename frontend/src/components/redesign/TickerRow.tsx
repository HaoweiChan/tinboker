import React from 'react';
import { cn } from '@/lib/utils';
import type { Sentiment } from '@/lib/sentiment';
import { SentimentChip } from './SentimentChip';
import { Change } from './Change';

export interface TickerRowData {
  symbol: string; // e.g. 2330.TW, NVDA
  sentiment?: Sentiment; // LLM-derived; chip color is always green=bull/red=bear
  changePercent?: number | null; // price change %; color follows the TW/US convention
}

interface TickerRowProps {
  ticker: TickerRowData;
  onClick?: () => void;
  className?: string;
}

/** Inset row: [symbol | sentiment chip | price change %]. */
export const TickerRow: React.FC<TickerRowProps> = ({ ticker, onClick, className }) => {
  const interactive = typeof onClick === 'function';
  const Tag = interactive ? 'button' : 'div';
  return (
    <Tag
      {...(interactive ? { type: 'button' as const, onClick } : {})}
      className={cn('ticker-row w-full text-left', interactive && 'hover:bg-muted transition-colors', className)}
    >
      <span className="ticker-row-symbol">{ticker.symbol}</span>
      {ticker.sentiment ? <SentimentChip sentiment={ticker.sentiment} /> : <span />}
      <Change value={ticker.changePercent} />
    </Tag>
  );
};
