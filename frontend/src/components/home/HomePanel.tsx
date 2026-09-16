import React from 'react';

/** The 本週市場在聊什麼 surface, reused by the two panels under it so all three read as
 *  one block: same padding, same heading size, same muted aside. (Tile — the generic
 *  bento surface — keeps its small muted label for every other page.) */
export const HomePanel: React.FC<{
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, aside, children }) => (
  <div className="bg-card border border-border rounded-[10px] p-5 flex flex-col gap-4 min-w-0 h-full">
    <div className="flex items-baseline justify-between gap-3 flex-wrap">
      <h2 className="text-xl font-semibold tracking-[-0.02em]">{title}</h2>
      {aside && <span className="hidden sm:block text-2xs text-muted-foreground">{aside}</span>}
    </div>
    {children}
  </div>
);
