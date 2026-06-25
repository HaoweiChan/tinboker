import React from 'react';
import { cn } from '@/lib/utils';

interface StockIdentityProps {
  /** Raw ticker/symbol — exchange suffix is stripped (e.g. "2330.TW" → "2330"). */
  ticker: string;
  /** Localized display name (e.g. "台積電", "輝達"). Omitted/equal-to-code → code only. */
  name?: string | null;
  /** Size step on the shared type scale. Default 'sm' (body). */
  size?: 'sm' | 'md' | 'lg';
  /** Hide the ticker code when a name exists — use where a TickerAvatar chip already
   *  shows the code. Falls back to the code if there's no name (so it's never blank). */
  hideCode?: boolean;
  /** Extra classes applied to the code span only (e.g. a group-hover color). */
  codeClassName?: string;
  className?: string;
}

const SIZE: Record<NonNullable<StockIdentityProps['size']>, string> = {
  sm: 'text-sm',
  md: 'text-md',
  lg: 'text-lg',
};

/**
 * Canonical stock label, used EVERYWHERE a stock is presented in a list/row:
 * `CODE  NAME` — inline, ticker first, both the SAME colour (foreground) and the
 * SAME font size. Ticker is mono; name truncates. This is the single source of
 * truth for ticker+name presentation across the site — do not hand-roll variants.
 */
export const StockIdentity: React.FC<StockIdentityProps> = ({
  ticker,
  name,
  size = 'sm',
  hideCode,
  codeClassName,
  className,
}) => {
  const code = ticker.replace(/\.[A-Z]+$/i, '');
  const showName = !!name && name !== code && name !== ticker;
  const showCode = !(hideCode && showName);
  const sz = SIZE[size];
  return (
    <span className={cn('inline-flex items-baseline gap-1.5 min-w-0', className)}>
      {showCode && (
        <span className={cn('font-mono font-semibold tabular-nums text-foreground shrink-0', sz, codeClassName)}>
          {code}
        </span>
      )}
      {showName && <span className={cn('font-medium text-foreground truncate', sz)}>{name}</span>}
    </span>
  );
};
