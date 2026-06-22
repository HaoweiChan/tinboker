import React from 'react';
import { cn } from '@/lib/utils';

interface ListRowProps {
  /** Leading cell — index number, avatar, etc. */
  lead?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Optional middle cell (e.g. chips). */
  mid?: React.ReactNode;
  /** Trailing cell — meta + chevron. */
  trailing?: React.ReactNode;
  onClick?: () => void;
  href?: string;
  className?: string;
}

/** A flat hairline-bordered row used for episode / ticker lists. */
export const ListRow: React.FC<ListRowProps> = ({ lead, title, subtitle, mid, trailing, onClick, href, className }) => {
  const inner = (
    <>
      {lead != null && <div className="shrink-0">{lead}</div>}
      <div className="min-w-0">
        <div className="text-base font-medium leading-[1.4] truncate">{title}</div>
        {subtitle != null && <div className="text-2xs text-muted-foreground mt-0.5 truncate">{subtitle}</div>}
      </div>
      {mid != null && <div className="shrink-0">{mid}</div>}
      {trailing != null && <div className="shrink-0 flex items-center gap-2.5 text-xs text-muted-foreground">{trailing}</div>}
    </>
  );
  const classes = cn(
    'flex items-center gap-4 px-4 py-3.5 bg-card border border-border rounded-[var(--radius-md)]',
    'transition-colors hover:border-foreground/25 [&+&]:mt-1.5 w-full text-left',
    className,
  );
  if (href) return <a href={href} className={classes}>{inner}</a>;
  if (onClick) return <button type="button" onClick={onClick} className={classes}>{inner}</button>;
  return <div className={classes}>{inner}</div>;
};
