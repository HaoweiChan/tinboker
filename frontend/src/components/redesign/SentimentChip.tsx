import React from 'react';
import { cn } from '@/lib/utils';
import { getSentimentDisplay, type Sentiment } from '@/lib/sentiment';
import { useStockColorMode } from '@/hooks/useStockTrendColor';

interface SentimentChipProps {
  sentiment: Sentiment;
  /** Render only the colored text (no chip background). */
  bare?: boolean;
  className?: string;
}

/** LLM-derived sentiment badge — 看多 / 看空 / 中性. Renders nothing for unknown sentiment. */
export const SentimentChip: React.FC<SentimentChipProps> = ({ sentiment, bare = false, className }) => {
  const stockColorMode = useStockColorMode();
  const d = getSentimentDisplay(sentiment, stockColorMode);
  if (!d) return null;
  if (bare) {
    return <span className={cn('text-2xs font-medium uppercase tracking-wide', d.toneClass, className)}>{d.label}</span>;
  }
  return <span className={cn(d.chipClass, className)}>{d.label}</span>;
};
