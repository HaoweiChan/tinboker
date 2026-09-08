import React from 'react';
import { cn } from '@/lib/utils';
import { useGrowIn } from '@/hooks/useMotion';

interface SentBarProps {
  bull: number;
  neutral: number;
  bear: number;
  /** CSS width (defaults to full width of the container). */
  width?: string | number;
  className?: string;
  /** Stagger the grow-in (ms), e.g. row index × 40 in a list. */
  delayMs?: number;
}

/** Compact bull|neutral|bear proportion bar. Renders an empty track if all counts are 0. */
export const SentBar: React.FC<SentBarProps> = ({ bull, neutral, bear, width, className, delayMs = 0 }) => {
  const total = bull + neutral + bear;
  const grown = useGrowIn();
  // Segments grow from the left on mount; the site-wide reduced-motion rule disables it.
  const pct = (n: number) => (grown && total > 0 ? `${(n / total) * 100}%` : '0%');
  const seg = { transition: 'width 700ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${delayMs}ms` } as const;
  return (
    <span
      className={cn('sent-bar', width == null && 'w-full', className)}
      style={width != null ? { width } : undefined}
      aria-label={`情緒分佈 多 ${bull} / 中 ${neutral} / 空 ${bear}`}
    >
      <span className="sent-bar-bull" style={{ width: pct(bull), ...seg }} />
      <span className="sent-bar-neutral" style={{ width: pct(neutral), ...seg }} />
      <span className="sent-bar-bear" style={{ width: pct(bear), ...seg }} />
    </span>
  );
};
