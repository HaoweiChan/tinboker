import { cn } from '@/lib/utils';
import { getAvatarColor } from '@/utils/avatarColor';

interface TickerAvatarProps {
  ticker: string;
  brandColor?: string | null;
  className?: string;
}

/**
 * Rectangle avatar showing the ticker symbol with a brand color background.
 * Falls back to a hash-based color from the curated 12-color palette.
 */
export function TickerAvatar({ ticker, brandColor, className }: TickerAvatarProps) {
  const bg = brandColor || getAvatarColor(ticker);
  // Numeric tickers (TW/JP/KR) carry an exchange suffix to strip: "2330.TW" → "2330",
  // "005930.KS" → "005930". Letter tickers keep their class suffix: "BRK.B" stays.
  // Never truncate — the chip widens to fit (JP/KR 6-digit, US 5-letter like GOOGL).
  const label = /^\d/.test(ticker) ? ticker.split('.')[0] : ticker;

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded text-white font-bold font-mono text-2xs tracking-tight select-none shrink-0',
        className,
      )}
      style={{ backgroundColor: bg, minWidth: '2.75rem', height: '1.5rem', padding: '0 0.3rem' }}
    >
      {label}
    </span>
  );
}
