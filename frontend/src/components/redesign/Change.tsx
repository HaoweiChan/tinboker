import React from 'react';
import { cn } from '@/lib/utils';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';

interface ChangeProps {
  /** Percent change, e.g. -3.4 means -3.40%. Pass `null`/`undefined` to render an em-dash. */
  value?: number | null;
  /** Larger price-header size. */
  big?: boolean;
  className?: string;
}

/**
 * Monospace, tabular-numeral ±% with the user's price-change color convention
 * (TW user: red = up). SentimentChip uses the same up/down color convention.
 */
export const Change: React.FC<ChangeProps> = ({ value, big = false, className }) => {
  const trend = useStockTrendColor(value ?? 0);
  const has = value != null && Number.isFinite(value);
  const text = has ? `${value! >= 0 ? '+' : ''}${value!.toFixed(2)}%` : '—';
  return (
    <span
      className={cn(
        'font-mono tabular-nums font-medium',
        big ? 'text-xl' : 'text-sm',
        has ? trend.text : 'text-muted-foreground',
        className,
      )}
    >
      {text}
    </span>
  );
};
