import React from 'react';
import { Check, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Corner toggle on a 走勢 card: filled check when the card is in 我的清單, a plus when not. */
export const SaveCheck: React.FC<{ saved: boolean; onToggle: () => void; className?: string }> = ({ saved, onToggle, className }) => (
  <button
    type="button"
    aria-pressed={saved}
    aria-label={saved ? '從我的清單移除' : '加入我的清單'}
    title={saved ? '已在我的清單' : '加入我的清單'}
    onClick={onToggle}
    className={cn(
      'flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
      saved ? 'border-primary bg-primary text-background' : 'border-border text-muted-foreground hover:border-muted-foreground/40 hover:text-foreground',
      className,
    )}
  >
    {saved ? <Check size={16} strokeWidth={3} /> : <Plus size={16} />}
  </button>
);
