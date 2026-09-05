import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { getWeeks } from '@/services/api/weekly';
import type { WeeklyList } from '@/validation/schemas';

export const WeeklyIndex: React.FC = () => {
  const [weeks, setWeeks] = useState<WeeklyList['weeks'] | null>(null);

  useEffect(() => {
    let alive = true;
    getWeeks()
      .then((w) => { if (alive) setWeeks(w.weeks); })
      .catch(() => { if (alive) setWeeks([]); });
    return () => { alive = false; };
  }, []);

  return (
    <>
      <SEO
        title="Podcast 週報"
        description="每週一頁：台灣財經 Podcast 這一週聊了哪些個股與題材、多空怎麼變，由 TinBoker 結構化整理。"
        url={typeof window !== 'undefined' ? `${window.location.origin}/weekly` : undefined}
        type="website"
      />
      <PageContent>
        <div className="bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">Podcast 週報</h1>
          <p className="text-base text-muted-foreground mt-1 max-w-[60ch] leading-[1.55]">每週一頁：這一週台灣財經 Podcast 聊了哪些個股與題材、多空怎麼變。</p>
        </div>
        {weeks == null ? (
          <div className="bg-card border border-border rounded-md h-32 animate-pulse" />
        ) : weeks.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">目前沒有可顯示的週報。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {weeks.map((w) => (
              <Link key={w.week} to={`/weekly/${w.week}`} className="block bg-card border border-border rounded-md p-4 hover:bg-muted/40 transition-colors">
                <div className="text-2xs font-mono text-muted-foreground tabular-nums">{w.week}</div>
                <div className="text-sm font-medium mt-0.5">{w.start.replace(/-/g, '/')} – {w.end.slice(5).replace('-', '/')}</div>
                <div className="text-xs text-muted-foreground mt-1"><strong className="font-mono text-foreground tabular-nums">{w.episode_count}</strong> 集已分析</div>
              </Link>
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};

export default WeeklyIndex;
