import React from 'react';
import { pctChange } from './attention';

/** ↑12% / ↓5% / — / NEW for a now-vs-prior pair. */
export const DeltaText: React.FC<{ now: number; prev: number }> = ({ now, prev }) => {
  const d = pctChange(now, prev);
  if (d === null) return <span className="text-accent-info font-mono text-2xs">NEW</span>;
  if (d > 0) return <span className="text-sentiment-bull font-mono tabular-nums">↑{d}%</span>;
  if (d < 0) return <span className="text-sentiment-bear font-mono tabular-nums">↓{-d}%</span>;
  return <span className="text-muted-foreground font-mono">—</span>;
};
