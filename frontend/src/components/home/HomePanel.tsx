import React from 'react';

/** The 本週市場在聊什麼 surface, reused by the two panels under it so all three read as
 *  one block: same padding, same heading size, same muted aside. (Tile — the generic
 *  bento surface — keeps its small muted label for every other page.)
 *
 *  Amber lives on the brand layer only: the rule beside the heading and the hover
 *  border. The data layer stays blue-grey / cyan, so the brand colour never competes
 *  with a number's meaning. */
export const HomePanel: React.FC<{
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, aside, children }) => (
  <div className="bg-card border border-border rounded-[10px] p-5 flex flex-col gap-4 min-w-0 h-full transition-colors duration-200 hover:border-primary/45">
    <div className="flex items-baseline justify-between gap-3 flex-wrap">
      <h2 className="text-xl font-semibold tracking-[-0.02em] flex items-center gap-2">
        <span aria-hidden className="inline-block w-[3px] h-[18px] rounded-sm bg-primary shrink-0" />
        {title}
      </h2>
      {aside && <span className="hidden sm:block text-2xs text-muted-foreground">{aside}</span>}
    </div>
    {children}
  </div>
);
