import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { EXPLORE_ITEMS } from '@/lib/nav';

/**
 * Switcher shared by the three browse indexes. Real <Link>s (not the button-based
 * Segmented) so crawlers see the cross-links between the index pages.
 */
export const ExploreTabs: React.FC = () => {
  const { pathname } = useLocation();
  return (
    // Page-level navigation, so NOT a .filter-pill: the pills on these pages filter
    // the list in place, and three identical amber rows made the one control that
    // changes page look like a third filter. Underlined tabs + a hairline rule read
    // as "switch section" at a glance.
    <div className="flex items-center gap-5 border-b border-border mb-4" role="tablist">
      {EXPLORE_ITEMS.map((it) => {
        const active = pathname === it.to;
        return (
          <Link
            key={it.to}
            to={it.to}
            role="tab"
            aria-selected={active}
            className={cn(
              'relative -mb-px py-2 text-sm font-medium tracking-tight transition-colors',
              'after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:transition-colors',
              active
                ? 'text-foreground after:bg-primary'
                : 'text-muted-foreground hover:text-foreground after:bg-transparent',
            )}
          >
            {it.label}
          </Link>
        );
      })}
    </div>
  );
};
