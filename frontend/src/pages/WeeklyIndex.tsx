import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { CountUp } from '@/components/common/CountUp';
import { useGrowIn } from '@/hooks/useMotion';
import { getWeeks } from '@/services/api/weekly';
import type { WeeklyList } from '@/validation/schemas';

type Week = WeeklyList['weeks'][number];

const range = (w: Week) => `${w.start.replace(/-/g, '/')} – ${w.end.slice(5).replace('-', '/')}`;

export const WeeklyIndex: React.FC = () => {
  const [weeks, setWeeks] = useState<Week[] | null>(null);

  useEffect(() => {
    let alive = true;
    getWeeks()
      .then((w) => { if (alive) setWeeks(w.weeks); })
      .catch(() => { if (alive) setWeeks([]); });
    return () => { alive = false; };
  }, []);

  const total = useMemo(() => (weeks ?? []).reduce((a, w) => a + w.episode_count, 0), [weeks]);
  const max = useMemo(() => (weeks ?? []).reduce((m, w) => Math.max(m, w.episode_count), 1), [weeks]);
  const grown = useGrowIn();

  return (
    <>
      <SEO
        title="Podcast 週報"
        description="每週一頁：台灣財經 Podcast 這一週聊了哪些個股與題材、多空怎麼變，由 TinBoker 結構化整理。"
        url={typeof window !== 'undefined' ? `${window.location.origin}/weekly` : undefined}
        type="website"
      />
      <PageContent>
        <div className="flex items-end justify-between gap-4 flex-wrap mb-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.02em]">Podcast 週報</h1>
            <p className="text-sm text-muted-foreground mt-1 max-w-[60ch] leading-[1.6]">每週一頁：這一週台灣財經 Podcast 聊了哪些個股與題材、多空怎麼變。</p>
          </div>
          {weeks && weeks.length > 0 && (
            <div className="text-sm text-muted-foreground tabular-nums">
              <span className="font-mono text-foreground text-lg font-semibold"><CountUp value={weeks.length} /></span> 週 · <span className="font-mono text-foreground text-lg font-semibold"><CountUp value={total} /></span> 集
            </div>
          )}
        </div>

        {weeks == null ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="bg-card border border-border rounded-[10px] h-44 animate-pulse" />)}
          </div>
        ) : weeks.length === 0 ? (
          <div className="bg-card border border-border rounded-[10px] p-10 text-center text-sm text-muted-foreground">目前沒有可顯示的週報。</div>
        ) : (
          <>
            {/* Episodes per week, oldest → newest: the shape of the whole run at a glance. */}
            <div className="bg-card border border-border rounded-[10px] p-5 mb-3.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-2"><span>每週已分析集數</span><span>{[...weeks].reverse()[0].week} → {weeks[0].week}</span></div>
              <div className="flex items-end gap-1.5 h-16">
                {[...weeks].reverse().map((w, i) => (
                  <Link key={w.week} to={`/weekly/${w.week}`} title={`${range(w)} · ${w.episode_count} 集`} className="flex-1 h-full flex flex-col justify-end group">
                    <span
                      className={`block w-full rounded-sm transition-colors ${i === weeks.length - 1 ? 'bg-primary' : 'bg-primary/45 group-hover:bg-primary/80'}`}
                      style={{ height: grown ? `${(w.episode_count / max) * 100}%` : '0%', transition: 'height 600ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 30}ms` }}
                    />
                  </Link>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {weeks.map((w, i) => (
                <Link
                  key={w.week}
                  to={`/weekly/${w.week}`}
                  className={`group relative bg-card border rounded-[10px] p-5 flex flex-col gap-3 hover:bg-muted/30 transition-colors ${i === 0 ? 'border-primary/40' : 'border-border'}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-2xs font-mono text-muted-foreground tabular-nums">{w.week}{i === 0 && <span className="ml-2 rounded-full bg-primary/15 text-primary px-1.5 py-0.5 text-2xs font-medium">最新</span>}</div>
                      <div className="text-base font-medium mt-0.5 group-hover:text-primary transition-colors">{range(w)}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-mono tabular-nums text-2xl font-semibold leading-none">{w.episode_count}</div>
                      <div className="text-2xs text-muted-foreground mt-1">集 · {w.podcast_count} 個節目</div>
                    </div>
                  </div>
                  {w.top_tickers.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {w.top_tickers.map((t) => (
                        <span key={t.ticker} className="inline-flex items-baseline gap-1 rounded-md bg-muted px-2 py-0.5 text-xs">
                          <span className="font-mono">{t.ticker}</span>{t.name && <span>{t.name}</span>}<span className="font-mono tabular-nums text-muted-foreground">{t.episodes}</span>
                        </span>
                      ))}
                    </div>
                  )}
                  {w.top_sectors.length > 0 && (
                    <div className="text-xs text-muted-foreground truncate">{w.top_sectors.map((s) => s.display_name).join(' · ')}</div>
                  )}
                </Link>
              ))}
            </div>
          </>
        )}
      </PageContent>
    </>
  );
};

export default WeeklyIndex;
