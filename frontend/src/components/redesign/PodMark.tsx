import React from 'react';
import { cn } from '@/lib/utils';

export type PodMarkKind = 'solid' | 'info' | 'bull' | 'bear' | 'mute';

interface PodMarkProps {
  /** Single-character (or short) avatar fallback. */
  label: string;
  kind?: PodMarkKind;
  /** Square side in px. */
  size?: number;
  className?: string;
}

const KIND_CLASS: Record<PodMarkKind, string> = {
  solid: 'bg-foreground text-background',
  info: 'bg-accent-info-soft text-accent-info',
  bull: 'bg-sentiment-bull-soft text-sentiment-bull',
  bear: 'bg-sentiment-bear-soft text-sentiment-bear',
  mute: 'bg-muted text-muted-foreground',
};

/** Square rounded avatar for a podcaster / show. */
export const PodMark: React.FC<PodMarkProps> = ({ label, kind = 'mute', size = 28, className }) => (
  <span
    className={cn('inline-grid place-items-center font-semibold shrink-0 select-none', KIND_CLASS[kind], className)}
    style={{ width: size, height: size, fontSize: Math.round(size * 0.42), borderRadius: Math.max(5, Math.round(size * 0.22)) }}
    aria-hidden="true"
  >
    {label}
  </span>
);
