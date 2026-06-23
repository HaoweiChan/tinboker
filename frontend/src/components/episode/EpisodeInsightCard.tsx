import React from 'react';
import { Lightbulb } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MentionText } from '@/components/episode/InlineMarkers';

export interface EpisodeInsight {
  headline: string;
  thesis?: string;
  highlights?: string[];
  meta?: string;
}

interface EpisodeInsightCardProps {
  insight: EpisodeInsight;
  className?: string;
}

export const EpisodeInsightCard: React.FC<EpisodeInsightCardProps> = ({ insight, className }) => (
  <section
    aria-label="關鍵洞察"
    className={cn('bg-card border border-border border-l-[3px] border-l-accent-info rounded-md p-3.5 sm:p-4 mb-3.5', className)}
  >
    <div className="flex items-center gap-1.5 text-2xs font-semibold tracking-[0.08em] uppercase text-muted-foreground mb-2">
      <Lightbulb size={14} className="text-accent-info" />
      <span>關鍵洞察</span>
    </div>
    <h2 className="text-xl sm:text-2xl font-semibold leading-[1.35] tracking-[-0.005em] mb-1.5">
      <MentionText text={insight.headline} />
    </h2>
    {insight.thesis && (
      <p className="text-md sm:text-lg leading-[1.7] text-muted-foreground">
        <MentionText text={insight.thesis} />
      </p>
    )}
    {insight.highlights && insight.highlights.length > 0 && (
      <ul className="mt-2.5 grid gap-1.5 text-base sm:text-md leading-[1.6] text-muted-foreground">
        {insight.highlights.slice(0, 2).map((item, index) => (
          <li key={index} className="grid grid-cols-[10px_1fr] gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-accent-info" />
            <span>
              <MentionText text={item} />
            </span>
          </li>
        ))}
      </ul>
    )}
    {insight.meta && <p className="mt-3 text-xs text-muted-foreground">{insight.meta}</p>}
  </section>
);
