import React from 'react';
import { Bookmark } from 'lucide-react';
import { cn } from '@/lib/utils';

/** 我的清單 toggle for a 走勢 card, part of the action group in the card's top-right
 *  corner: outlined when the card is not kept, filled when it is. The icon stays small;
 *  the 40px box around it is only the tap target. */
export const SaveCheck: React.FC<{ saved: boolean; onToggle: () => void; className?: string }> = ({ saved, onToggle, className }) => (
  <button
    type="button"
    aria-pressed={saved}
    aria-label={saved ? '從我的清單移除' : '加入我的清單'}
    title={saved ? '已在我的清單' : '加入我的清單'}
    onClick={onToggle}
    className={cn(
      'flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
      saved ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground',
      className,
    )}
  >
    <Bookmark size={14} className={saved ? 'fill-current' : undefined} />
  </button>
);
