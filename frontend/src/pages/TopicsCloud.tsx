import React, { useEffect, useMemo, useState } from 'react';
import { Flame, BarChart3, Layers, Hash } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { SectorHeroCard } from '@/components/topics/SectorHeroCard';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TagBoardCard } from '@/components/topics/TagBoardCard';
import {
  getSectorBoard,
  getTrendingTags,
  type SectorBoardItem,
  type TrendingTag,
} from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';

// ── Sort types ─────────────────────────────────────────────────────────────

type SortKey = 'hotness' | 'avg_change' | 'episode_count';

// ── Sort toggle ────────────────────────────────────────────────────────────

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'hotness', label: '綜合熱度' },
  { key: 'avg_change', label: '今日表現' },
  { key: 'episode_count', label: '討論熱度' },
];

function SortToggle({ value, onChange }: { value: SortKey; onChange: (k: SortKey) => void }) {
  return (
    <div className="flex items-center gap-0.5 bg-muted/50 border border-border rounded-lg p-0.5">
      {SORT_OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150
            ${value === opt.key
              ? 'bg-card text-foreground shadow-sm border border-border/60'
              : 'text-muted-foreground hover:text-foreground'
            }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ── Skeleton cards ─────────────────────────────────────────────────────────

function HeroSkeleton() {
  return (
    <div className="flex-1 min-w-[148px] bg-card border border-border dark:border-white/[0.08] rounded-xl p-4 animate-pulse">
      <div className="flex items-center gap-1.5 mb-3">
        <div className="h-3 w-3 bg-muted rounded" />
        <div className="h-3 w-8 bg-muted rounded" />
      </div>
      <div className="h-4 w-24 bg-muted rounded mb-3" />
      <div className="h-7 w-16 bg-muted rounded" />
      <div className="h-2.5 w-8 bg-muted rounded mt-2" />
    </div>
  );
}

function BoardSkeleton() {
  return (
    <div className="bg-card border border-border dark:border-white/[0.08] rounded-xl p-4 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="h-3 w-3 bg-muted rounded" />
            <div className="h-3 w-8 bg-muted rounded" />
          </div>
          <div className="h-4 w-28 bg-muted rounded" />
        </div>
        <div className="h-6 w-16 bg-muted rounded" />
      </div>
      <div className="space-y-2 pt-2 border-t border-border/40">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex gap-2 items-center">
            <div className="h-3 w-10 bg-muted rounded" />
            <div className="h-3 flex-1 bg-muted rounded" />
            <div className="h-3 w-11 bg-muted rounded" />
            <div className="h-3 w-12 bg-muted rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export const TopicsCloud: React.FC = () => {
  const [sectors, setSectors] = useState<SectorBoardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('hotness');
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const tagLabels = useTagLabels();

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const result = await fetchWithFallback(
        () => getSectorBoard(),
        [] as SectorBoardItem[],
        'getSectorBoard',
      ).catch(() => [] as SectorBoardItem[]);
      if (!alive) return;
      setSectors(result);
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  // Trending tags for the secondary section (free-form topics, no price data).
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getTrendingTags().catch(() => ({ tags: [] as TrendingTag[] }));
      if (!alive) return;
      setTags(res.tags);
    })();
    return () => { alive = false; };
  }, []);

  // Top gainers for hero strip: sorted by avg_change desc, up to 5
  const heroSectors = useMemo(() => {
    return [...sectors]
      .filter((s) => s.avg_change != null && Number.isFinite(s.avg_change))
      .sort((a, b) => (b.avg_change ?? -Infinity) - (a.avg_change ?? -Infinity))
      .slice(0, 5);
  }, [sectors]);

  // Board sorted by toggle
  const sortedSectors = useMemo(() => {
    return [...sectors].sort((a, b) => {
      if (sortKey === 'hotness') return (b.hotness ?? 0) - (a.hotness ?? 0);
      if (sortKey === 'avg_change') {
        return (b.avg_change ?? -Infinity) - (a.avg_change ?? -Infinity);
      }
      return (b.episode_count ?? 0) - (a.episode_count ?? 0);
    });
  }, [sectors, sortKey]);

  const hasData = !loading && sectors.length > 0;

  return (
    <>
      <SEO
        title="話題排行"
        description="今日最強題材焦點 — 依產業/主題聚合，顯示漲跌幅與相關個股表現。"
      />
      <PageContent>
        {/* Page header */}
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">話題排行</h1>
          {hasData && (
            <div className="text-xs text-muted-foreground font-mono tabular-nums flex items-center gap-1.5">
              <Layers size={12} />
              <span>{sectors.length} 題材</span>
            </div>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-6 max-w-[60ch]">
          今日最強題材焦點 — 依產業/主題聚合，顯示漲跌幅與相關個股。
        </p>

        {/* ── HERO STRIP ──────────────────────────────────────────── */}
        <div className="mb-7">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Flame size={13} className="text-accent-info" />
            <h2 className="text-sm font-semibold">今日漲幅最強</h2>
          </div>
          <div className="flex gap-2.5 overflow-x-auto pb-1 -mx-0.5 px-0.5 scrollbar-none">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => <HeroSkeleton key={i} />)
              : heroSectors.length > 0
                ? heroSectors.map((s) => <SectorHeroCard key={s.exposure_id} sector={s} />)
                : (
                  <div className="flex-1 bg-card border border-border rounded-xl p-4 text-sm text-muted-foreground text-center">
                    尚無漲跌幅資料
                  </div>
                )
            }
          </div>
        </div>

        {/* ── BOARD ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            <BarChart3 size={13} className="text-muted-foreground" />
            <h2 className="text-sm font-semibold">題材總覽</h2>
          </div>
          <SortToggle value={sortKey} onChange={setSortKey} />
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => <BoardSkeleton key={i} />)}
          </div>
        ) : sectors.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
            目前沒有題材資料。
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sortedSectors.map((s) => (
              <SectorBoardCard key={s.exposure_id} sector={s} />
            ))}
          </div>
        )}

        {/* ── TAGS ────────────────────────────────────────────────── */}
        {tags.length > 0 && (
          <div className="mt-9">
            <div className="flex items-center gap-1.5 mb-3">
              <Hash size={13} className="text-muted-foreground" />
              <h2 className="text-sm font-semibold">熱門標籤</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {tags.map((t) => (
                <TagBoardCard key={t.id} tag={t} label={tagLabelFor(t.id, tagLabels)} />
              ))}
            </div>
          </div>
        )}
      </PageContent>
    </>
  );
};
