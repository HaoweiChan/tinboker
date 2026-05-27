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
  // Strip exchange suffix for display: "2330.TW" → "2330", "BRK.B" → "BRK.B"
  const label = ticker.includes('.') && /^\d/.test(ticker)
    ? ticker.split('.')[0]
    : ticker.split('.')[0].slice(0, 4);

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded text-white font-bold font-mono text-[10px] tracking-tight select-none shrink-0',
        className,
      )}
      style={{ backgroundColor: bg, minWidth: '2.75rem', height: '1.5rem', padding: '0 0.25rem' }}
    >
      {label}
    </span>
  );
}
