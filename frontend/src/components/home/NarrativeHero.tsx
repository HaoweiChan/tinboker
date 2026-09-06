import React from 'react';
import { cn } from '@/lib/utils';
import { useGrowIn } from '@/hooks/useMotion';
import { CountUp } from '@/components/common/CountUp';
import type { Attention, AttentionNarrative } from '@/validation/schemas';
import { DeltaText } from './DeltaText';
import type { Focus } from './attention';

function Spark({ values, delayMs }: { values: number[]; delayMs: number }) {
  const W = 56, H = 18, max = Math.max(1, ...values);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${((i / Math.max(1, values.length - 1)) * W).toFixed(1)} ${(H - 2 - (v / max) * (H - 4)).toFixed(1)}`).join(' ');
  const grown = useGrowIn();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-14 h-[18px] shrink-0 text-muted-foreground" aria-hidden>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="200" strokeDashoffset={grown ? 0 : 200} style={{ transition: 'stroke-dashoffset 900ms ease-out', transitionDelay: `${delayMs}ms` }} />
    </svg>
  );
}

interface Props {
  data: Attention | null;
  focus: Focus | null;
  onFocus: (f: Focus | null) => void;
}

/** Layer ①: what the market is talking about this week — top narratives by 7-day
 *  mentions plus one "rising" slot. Rows are clickable and filter the feed below. */
export const NarrativeHero: React.FC<Props> = ({ data, focus, onFocus }) => {
  const rows: AttentionNarrative[] = data?.narratives ?? [];
  const max = Math.max(1, ...rows.map((r) => r.count_7d));
  const grown = useGrowIn();
  const pick = (r: AttentionNarrative) => onFocus(focus?.kind === 'tag' && focus.key === r.id ? null : { kind: 'tag', key: r.id, label: r.name });

  return (
    <div className="bg-card border border-border rounded-[10px] p-5 flex flex-col gap-4 min-w-0">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold tracking-[-0.02em]">本週市場在聊什麼</h1>
          {data && (
            <p className="text-sm text-muted-foreground mt-0.5">
              近 7 天收錄 <span className="font-mono tabular-nums text-foreground font-semibold"><CountUp value={data.episode_count_7d} /></span> 集 ·{' '}
              <span className="font-mono tabular-nums text-foreground font-semibold">{data.podcast_count_7d}</span> 個節目
            </p>
          )}
        </div>
        <span className="hidden sm:block text-2xs text-muted-foreground">近 7 天提及集數 · 較前 7 天變化 · 點主題篩選下方集數</span>
      </div>

      {rows.length === 0 ? (
        <div className="h-[168px] animate-pulse bg-muted/40 rounded-md" />
      ) : (
        <div className="grid grid-cols-[auto_1fr_auto_auto] sm:grid-cols-[auto_1fr_auto_auto_auto] items-center gap-x-3 sm:gap-x-4 gap-y-2.5 text-sm">
          {rows.map((r, i) => {
            const on = focus?.kind === 'tag' && focus.key === r.id;
            return (
              <React.Fragment key={r.id}>
                <button type="button" onClick={() => pick(r)} aria-pressed={on} className={cn('text-left font-semibold whitespace-nowrap hover:text-primary transition-colors', on && 'text-primary')}>
                  {r.name}
                  {r.rising && <span className="ml-1.5 align-[1px] text-2xs font-medium text-accent-info border border-accent-info rounded px-1">升溫</span>}
                </button>
                <span className="h-4 sm:h-[16px] rounded-[3px] bg-muted overflow-hidden">
                  <span className="block h-full bg-primary/85 rounded-[3px]" style={{ width: grown ? `${(r.count_7d / max) * 100}%` : '0%', transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 60}ms` }} />
                </span>
                <span className="font-mono tabular-nums text-right">{r.count_7d} <span className="text-2xs text-muted-foreground">集</span></span>
                <span className="hidden sm:block"><Spark values={r.weekly} delayMs={i * 60 + 200} /></span>
                <span className="text-right min-w-[48px] font-semibold"><DeltaText now={r.count_7d} prev={r.prev_7d} /></span>
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
};
