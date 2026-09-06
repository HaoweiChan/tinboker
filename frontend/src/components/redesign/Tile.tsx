import React from 'react';
import { cn } from '@/lib/utils';

interface TileProps {
  /** Sentence-case label, small and muted — no uppercase eyebrows. */
  title?: React.ReactNode;
  /** Right side of the title row (a toggle, a count, a link). */
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/** One bento tile: the surface every dashboard block sits on. Span it with the grid
 *  classes (`md:col-span-2`, `md:row-span-2`) via className. */
export const Tile: React.FC<TileProps> = ({ title, aside, className, children }) => (
  <div className={cn('bg-card border border-border rounded-[10px] p-5 flex flex-col gap-3 min-w-0', className)}>
    {(title || aside) && (
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {title && <div className="text-xs text-muted-foreground">{title}</div>}
        {aside && <div className="text-xs text-muted-foreground">{aside}</div>}
      </div>
    )}
    {children}
  </div>
);
