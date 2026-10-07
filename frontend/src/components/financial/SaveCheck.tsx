import React from 'react';
import { Bookmark } from 'lucide-react';
import { cn } from '@/lib/utils';

/** 我的清單 toggle for a 走勢 card: a small bookmark beside the date, outlined when the
 *  card is not kept and filled when it is. The padding is the tap target, pulled back
 *  with negative margins so the icon still lines up with the date text. */
export const SaveCheck: React.FC<{ saved: boolean; onToggle: () => void; className?: string }> = ({ saved, onToggle, className }) => (
  <button
    type="button"
    aria-pressed={saved}
    aria-label={saved ? '從我的清單移除' : '加入我的清單'}
    title={saved ? '已在我的清單' : '加入我的清單'}
    onClick={onToggle}
    className={cn(
      '-my-2 -mr-2 shrink-0 rounded p-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
      saved ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground',
      className,
    )}
  >
    <Bookmark size={15} className={saved ? 'fill-current' : undefined} />
  </button>
);
