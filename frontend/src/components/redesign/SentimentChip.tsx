import React from 'react';
import { cn } from '@/lib/utils';
import { getSentimentDisplay, type Sentiment } from '@/lib/sentiment';

interface SentimentChipProps {
  sentiment: Sentiment;
  /** Render only the colored text (no chip background). */
  bare?: boolean;
  className?: string;
}

/** LLM-derived sentiment badge — 看多 / 看空 / 中性. Renders nothing for unknown sentiment. */
export const SentimentChip: React.FC<SentimentChipProps> = ({ sentiment, bare = false, className }) => {
  const d = getSentimentDisplay(sentiment);
  if (!d) return null;
  if (bare) {
    return <span className={cn('text-[11px] font-medium uppercase tracking-wide', d.toneClass, className)}>{d.label}</span>;
  }
  return <span className={cn(d.chipClass, className)}>{d.label}</span>;
};
