import React from 'react';
import { Change } from '@/components/redesign';
import { cn } from '@/lib/utils';
import type { MentionPerformance } from '@/validation/schemas';

// Post-mention windows are measured in *trading days* (1D/5D/20D/60D).
const WINDOWS: { key: 'r1d' | 'r5d' | 'r20d' | 'r60d'; label: string }[] = [
  { key: 'r1d', label: '1日' },
  { key: 'r5d', label: '5日' },
  { key: 'r20d', label: '20日' },
  { key: 'r60d', label: '60日' },
];

/**
 * Four post-mention return chips (1/5/20/60 trading days). Colors follow the
 * user's stock price color convention via <Change> (TW default: red = up);
 * a window that hasn't elapsed (null) renders as an em-dash.
 */
export const MentionReturnChips: React.FC<{
  performance?: MentionPerformance | null;
  className?: string;
}> = ({ performance, className }) => (
  <div className={cn('grid grid-cols-4 gap-2', className)}>
    {WINDOWS.map(({ key, label }) => (
      <div key={key} className="text-center">
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</div>
        <Change value={performance ? performance[key] : null} />
      </div>
    ))}
  </div>
);
