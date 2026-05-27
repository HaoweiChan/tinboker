import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { RailCard } from '@/components/redesign';
import { getTags } from '@/services/api/podcasts';
import type { Tag } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

export const TopicsCloud: React.FC = () => {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const res = await fetchWithFallback(() => getTags(), { tags: [] }, 'getTags:cloud').catch(() => ({ tags: [] as Tag[] }));
      if (!alive) return;
      setTags(Array.isArray(res?.tags) ? res.tags : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const { sorted, maxCount } = useMemo(() => {
    const s = [...tags].sort((a, b) => (b.episode_count || 0) - (a.episode_count || 0));
    return { sorted: s, maxCount: s[0]?.episode_count || 1 };
  }, [tags]);

  return (
    <>
      <SEO title="話題雲" description="最近熱門的財經話題 — 大小依被提及的集數數量。" />
      <PageContent>
        <div className="flex items-baseline justify-between mb-4">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">話題雲</h1>
          <div className="text-[12px] text-muted-foreground">大小依被提及的集數數量</div>
        </div>

        {loading ? (
          <div className="bg-card border border-border rounded-md p-10 h-[220px] animate-pulse" />
        ) : sorted.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有話題資料。</div>
        ) : (
          <>
            <div className="bg-card border border-border rounded-md p-7">
              <div className="flex flex-wrap gap-x-3.5 gap-y-2.5 items-baseline justify-center min-h-[180px]">
                {sorted.map((t) => {
                  const weight = (t.episode_count || 1) / maxCount;
                  return (
                    <Link
                      key={t.id || t.name}
                      to={`/topics/${encodeURIComponent(t.name)}`}
                      className="font-medium px-3 py-1 rounded-full bg-card border border-border hover:border-foreground/30 hover:-translate-y-0.5 transition-all"
                      style={{ fontSize: 13 + Math.round(weight * 16) }}
                    >
                      #{t.name}
                      <span className="text-muted-foreground ml-1.5 font-mono text-[11px] align-baseline">{t.episode_count}</span>
                    </Link>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-[18px]">
              {sorted.slice(0, 6).map((t) => (
                <Link key={`f-${t.id || t.name}`} to={`/topics/${encodeURIComponent(t.name)}`}>
                  <RailCard title={`#${t.name}`} sub={`${t.episode_count} 集`}>
                    <div className="text-[12px] text-muted-foreground">本月 {t.episode_count} 集提及</div>
                  </RailCard>
                </Link>
              ))}
            </div>
          </>
        )}
      </PageContent>
    </>
  );
};
