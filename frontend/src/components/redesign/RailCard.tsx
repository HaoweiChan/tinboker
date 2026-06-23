import React from 'react';
import { cn } from '@/lib/utils';

interface RailCardProps {
  title: React.ReactNode;
  /** Small muted sub-label shown on the right of the header. */
  sub?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/** Flat hairline-bordered card used in the home right-rail and elsewhere. */
export const RailCard: React.FC<RailCardProps> = ({ title, sub, children, className }) => (
  <section className={cn('bg-card border border-border rounded-[var(--radius-md)] p-4', className)}>
    <div className="flex items-baseline justify-between mb-3">
      <div className="text-lg font-semibold tracking-[-0.005em]">{title}</div>
      {sub != null && <div className="text-2xs text-muted-foreground">{sub}</div>}
    </div>
    {children}
  </section>
);
