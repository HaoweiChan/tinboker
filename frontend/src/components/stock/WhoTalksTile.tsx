import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useGrowIn } from '@/hooks/useMotion';
import type { TickerInsight } from '@/services/types';

interface WhoTalksTileProps {
  insights: TickerInsight[];
  className?: string;
  max?: number;
}

/** Which shows talk about this ticker most (90-day insight count), amber bars. */
export const WhoTalksTile: React.FC<WhoTalksTileProps> = ({ insights, className, max = 4 }) => {
  const rows = useMemo(() => {
    const counts = new Map<string, number>();
    for (const i of insights) if (i.podcaster) counts.set(i.podcaster, (counts.get(i.podcaster) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, max).map(([name, n]) => ({ name, n }));
  }, [insights, max]);
  const grown = useGrowIn();
  if (rows.length === 0) return null;
  const top = rows[0].n;

  return (
    <div className={cn('bg-card border border-border rounded-[10px] p-5 flex flex-col gap-2.5', className)}>
      <div className="text-xs text-muted-foreground">誰在談 · 90 天</div>
      <div className="flex flex-col gap-2 text-sm">
        {rows.map((r, i) => (
          <Link key={r.name} to={`/podcaster/${encodeURIComponent(r.name)}`} className="group flex items-center gap-3 min-w-0">
            <span className="w-32 shrink-0 truncate group-hover:text-primary transition-colors">{r.name}</span>
            <span className="relative flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <span className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: grown ? `${(r.n / top) * 100}%` : '0%', transition: 'width 600ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 40}ms` }} />
            </span>
            <span className="w-7 shrink-0 text-right text-xs font-mono tabular-nums text-muted-foreground">{r.n}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};
