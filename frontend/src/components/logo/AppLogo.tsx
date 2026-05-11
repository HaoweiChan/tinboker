import React from 'react';
import { cn } from '@/lib/utils';

interface AppLogoProps {
  /** Height of the bracket mark in px (the wordmark scales with it). */
  size?: number;
  className?: string;
  /** Extra classes applied to the wordmark text. */
  textClassName?: string;
  /** Hide the "聽播客 ｜ TinBoker" wordmark below the `sm` breakpoint (mark only). */
  mobileCompact?: boolean;
  /** Render the bracket mark only, no wordmark. */
  markOnly?: boolean;
}

/** The yellow accent on the closing bracket — the one warm tone in the system. */
const ACCENT = '#ffd23f';

/** TinBoker 「」 bracket mark. L bracket follows the theme via `currentColor`; R bracket is the yellow accent. */
export const BracketMark: React.FC<{ size?: number; className?: string }> = ({ size = 26, className }) => (
  <svg viewBox="0 0 42 42" width={size} height={size} fill="none" className={className} aria-hidden="true">
    <path d="M9 9 H21 V13 H13 V21 H9 Z" fill="currentColor" />
    <path d="M33 33 H21 V29 H29 V21 H33 Z" fill={ACCENT} />
    <circle cx="18" cy="24" r="1.5" fill="currentColor" />
    <circle cx="22" cy="20" r="1.5" fill="currentColor" opacity="0.7" />
    <circle cx="26" cy="16" r="1.5" fill={ACCENT} opacity="0.85" />
  </svg>
);

export const AppLogo: React.FC<AppLogoProps> = ({ size = 26, className, textClassName, mobileCompact = false, markOnly = false }) => {
  const wordSize = Math.round(size * 0.66);
  return (
    <div className={cn('flex items-center gap-2.5 select-none text-foreground', className)}>
      <span className="grid place-items-center shrink-0" style={{ width: size, height: size }}>
        <BracketMark size={size} />
      </span>
      {!markOnly && (
        <span
          className={cn('items-baseline gap-2 leading-none', mobileCompact ? 'hidden sm:flex' : 'flex', textClassName)}
          style={{ fontSize: wordSize }}
        >
          <span className="font-bold tracking-[0.01em]" style={{ fontFamily: "'Noto Sans TC', system-ui, sans-serif" }}>
            聽播客
          </span>
          <span className="self-stretch w-px bg-border" aria-hidden="true" style={{ marginInline: 2 }} />
          <span className="font-bold tracking-[-0.01em]" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
            TinBoker
          </span>
        </span>
      )}
    </div>
  );
};
