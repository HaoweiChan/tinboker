import React from 'react';
import { cn } from '@/lib/utils';

export interface StatItem {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  /** Use sans (not mono) for non-numeric values like "今天". */
  textValue?: boolean;
}

interface StatGroupProps {
  items: readonly StatItem[];
  className?: string;
}

/** Horizontal group of stats with hairline dividers (2-up on mobile, N-up on desktop). */
export const StatGroup: React.FC<StatGroupProps> = ({ items, className }) => (
  <div
    className={cn(
      'grid bg-card border border-border rounded-[var(--radius-md)] overflow-hidden',
      'grid-cols-2',
      items.length >= 4 ? 'md:grid-cols-4' : items.length === 3 ? 'md:grid-cols-3' : 'md:grid-cols-2',
      className,
    )}
  >
    {items.map((it, i) => (
      <div
        key={i}
        className={cn(
          'px-[18px] py-4',
          // left divider except first in each row; top divider on the 2nd row (mobile)
          i % 2 === 1 && 'border-l border-border',
          i >= 2 && 'border-t border-border',
          // on md, every non-first gets a left border and no top border
          'md:border-t-0',
          i > 0 && 'md:border-l md:border-border',
          i === 0 && 'border-l-0',
        )}
      >
        <div className="text-2xs text-muted-foreground mb-1.5 uppercase tracking-[0.06em] font-medium">{it.label}</div>
        <div className={cn('font-semibold tracking-[-0.02em]', it.textValue ? 'text-lg' : 'font-mono tabular-nums text-2xl')}>
          {it.value}
        </div>
        {it.sub != null && <div className="text-2xs text-muted-foreground mt-1">{it.sub}</div>}
      </div>
    ))}
  </div>
);
