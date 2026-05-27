import React from 'react';
import { cn } from '@/lib/utils';

interface FilterPillsProps<T extends string> {
  items: readonly T[];
  value: T;
  onChange: (value: T) => void;
  /** Optional right-aligned metadata node (e.g. "整理了 7 集"). */
  meta?: React.ReactNode;
  className?: string;
}

/** Horizontal row of toggle pills, with one active at a time. */
export function FilterPills<T extends string>({ items, value, onChange, meta, className }: FilterPillsProps<T>) {
  return (
    <div className={cn('flex items-center gap-2 flex-wrap mb-[18px]', className)}>
      {items.map((item) => (
        <button
          key={item}
          type="button"
          className="filter-pill"
          data-active={value === item || undefined}
          aria-pressed={value === item}
          onClick={() => onChange(item)}
        >
          {item}
        </button>
      ))}
      {meta != null && <div className="ml-auto text-xs text-muted-foreground">{meta}</div>}
    </div>
  );
}
