import React from 'react';
import { cn } from '@/lib/utils';

interface SentBarProps {
  bull: number;
  neutral: number;
  bear: number;
  /** CSS width (defaults to full width of the container). */
  width?: string | number;
  className?: string;
}

/** Compact bull|neutral|bear proportion bar. Renders an empty track if all counts are 0. */
export const SentBar: React.FC<SentBarProps> = ({ bull, neutral, bear, width, className }) => {
  const total = bull + neutral + bear;
  const pct = (n: number) => (total > 0 ? `${(n / total) * 100}%` : '0%');
  return (
    <span
      className={cn('sent-bar', width == null && 'w-full', className)}
      style={width != null ? { width } : undefined}
      aria-label={`情緒分佈 多 ${bull} / 中 ${neutral} / 空 ${bear}`}
    >
      <span className="sent-bar-bull" style={{ width: pct(bull) }} />
      <span className="sent-bar-neutral" style={{ width: pct(neutral) }} />
      <span className="sent-bar-bear" style={{ width: pct(bear) }} />
    </span>
  );
};
