import React from 'react';
import { cn } from '@/lib/utils';

interface PageContentProps {
  children: React.ReactNode;
  /** Right-rail content (rendered as a sticky aside on xl+). */
  rail?: React.ReactNode;
  className?: string;
}

/** Centered content container for redesigned pages. Optionally adds a right rail on xl+. */
export const PageContent: React.FC<PageContentProps> = ({ children, rail, className }) => (
  <div
    className={cn(
      'max-w-[1440px] mx-auto w-full px-4 sm:px-6 lg:px-7 py-5 sm:py-[22px] pb-20',
      rail ? 'xl:grid xl:grid-cols-[minmax(0,1fr)_320px] xl:gap-6' : '',
      className,
    )}
  >
    <div className="min-w-0">{children}</div>
    {rail && <aside className="hidden xl:flex flex-col gap-4 sticky top-[76px] self-start">{rail}</aside>}
  </div>
);
