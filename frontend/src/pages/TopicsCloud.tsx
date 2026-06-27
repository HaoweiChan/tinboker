import React, { useEffect, useMemo, useState } from 'react';
import { Flame, BarChart3, Layers, Hash, Info } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign/Segmented';
import SectorPerformance from '@/components/industry/SectorPerformance';
import { SectorHeroCard } from '@/components/topics/SectorHeroCard';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TagBoardCard } from '@/components/topics/TagBoardCard';
import {
  getSectorBoard,
  getIndustryPerformance,
  getThemePerformance,
  getTrendingTags,
  type SectorBoardItem,
  type IndustryPerformanceItem,
  type ThemePerformanceItem,
  type TrendingTag,
} from '@/services/api/podcasts';
import type { SectorBubbleData } from '@/services/mocks/types';
import { fetchWithFallback } from '@/services/api/migration';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';

// ── Tab + sort types ─────────────────────────────────────────────────────────

type TabKey = 'industry' | 'theme';
type SortKey = 'hotness' | 'avg_change' | 'episode_count';

const TAB_OPTIONS = [
  { value: 'theme' as const, label: '題材' },
  { value: 'industry' as const, label: '產業' },
];

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

function sortBoard(items: SectorBoardItem[], sortKey: SortKey): SectorBoardItem[] {
  return [...items].sort((a, b) => {
    if (sortKey === 'hotness') return (b.hotness ?? 0) - (a.hotness ?? 0);
    if (sortKey === 'avg_change') return (b.avg_change ?? -Infinity) - (a.avg_change ?? -Infinity);
    return (b.episode_count ?? 0) - (a.episode_count ?? 0);
  });
}

// ── Main page ──────────────────────────────────────────────────────────────

export const TopicsCloud: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('theme');
  const [sectors, setSectors] = useState<SectorBoardItem[]>([]);
  const [industries, setIndustries] = useState<IndustryPerformanceItem[]>([]);
  const [themes, setThemes] = useState<ThemePerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [industryLoading, setIndustryLoading] = useState(true);
  const [themeLoading, setThemeLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('hotness');
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const tagLabels = useTagLabels();

  // Board (both tabs filter this by exposure_type)
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

  // Industry performance (bubble chart) — FinMind-driven market cap + return
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getIndustryPerformance().catch(() => [] as IndustryPerformanceItem[]);
      if (!alive) return;
      setIndustries(res);
      setIndustryLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  // Theme performance (bubble chart) — discussion volume × return, sized by trade value
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getThemePerformance().catch(() => [] as ThemePerformanceItem[]);
      if (!alive) return;
      setThemes(res);
      setThemeLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  // Trending tags (free-form topics, shown on the 題材 tab)
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getTrendingTags().catch(() => ({ tags: [] as TrendingTag[] }));
      if (!alive) return;
      setTags(res.tags);
    })();
    return () => { alive = false; };
  }, []);

  const industryBoard = useMemo(
    () => sectors.filter((s) => s.exposure_type === 'sector'),
    [sectors],
  );
  const themeBoard = useMemo(
    () => sectors.filter((s) => s.exposure_type === 'theme'),
    [sectors],
  );

  // Bubble-chart shape: market cap NT$ → 兆, daily avg_change → return, episodes → size.
  const industryBubbles = useMemo<SectorBubbleData[]>(
    () =>
      industries.map((i) => ({
        id: i.exposure_id,
        name: i.display_name,
        label: i.display_name,
        value: i.market_cap_twd ? i.market_cap_twd / 1e12 : 0,
        marketCap: i.market_cap_twd ? +(i.market_cap_twd / 1e12).toFixed(1) : 0,
        return: i.return_pct ?? 0,
        returnRate: i.return_pct != null ? +i.return_pct.toFixed(2) : 0,
        volume: i.episode_count,
      })),
    [industries],
  );

  // Theme bubble: X = discussion (episodes), Y = return %, size = today's trade value (億).
  const themeBubbles = useMemo<SectorBubbleData[]>(
    () =>
      themes.map((t) => ({
        id: t.exposure_id,
        name: t.display_name,
        label: t.display_name,
        value: t.heat ?? 0,
        // X = recency-weighted 討論熱度 (time-decay, 7d half-life); raw count → sub-line.
        marketCap: t.heat != null ? +t.heat.toFixed(1) : 0,
        subLabel: `${t.episode_count} 集討論`,
        return: t.return_pct ?? 0,
        returnRate: t.return_pct != null ? +t.return_pct.toFixed(2) : 0,
        volume: t.trading_value_twd ? +(t.trading_value_twd / 1e8).toFixed(0) : 0,
      })),
    [themes],
  );

  // Theme tab hero strip: top theme gainers
  const heroThemes = useMemo(
    () =>
      [...themeBoard]
        .filter((s) => s.avg_change != null && Number.isFinite(s.avg_change))
        .sort((a, b) => (b.avg_change ?? -Infinity) - (a.avg_change ?? -Infinity))
        .slice(0, 5),
    [themeBoard],
  );

  const visibleBoard = tab === 'industry' ? industryBoard : themeBoard;
  const sortedBoard = useMemo(() => sortBoard(visibleBoard, sortKey), [visibleBoard, sortKey]);

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
          {!loading && sectors.length > 0 && (
            <div className="text-xs text-muted-foreground font-mono tabular-nums flex items-center gap-1.5">
              <Layers size={12} />
              <span>{visibleBoard.length} {tab === 'industry' ? '產業' : '題材'}</span>
            </div>
          )}
        </div>
        <p className="text-base text-muted-foreground mb-5 max-w-[60ch]">
          {tab === 'industry'
            ? '台股產業地圖 — 市值與近期漲跌，依產業別聚合。'
            : '今日最強題材焦點 — 短線概念聚合，顯示漲跌幅與相關個股。'}
        </p>

        {/* Tabs */}
        <Segmented options={TAB_OPTIONS} value={tab} onChange={(v) => setTab(v as TabKey)} className="mb-3" />

        {/* Data-freshness disclaimer: prices come from the last *completed* daily bar,
            not live ticks — so before today's close the figures may be the prior day's. */}
        <p className="mb-6 flex items-start gap-1.5 text-xs text-muted-foreground">
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>漲跌與市值採用最近一個<strong className="font-medium text-foreground/80">完整交易日</strong>的收盤資料，非即時報價；當日尚未收盤結算前，可能顯示前一交易日數據。</span>
        </p>

        {tab === 'industry' ? (
          <>
            {/* ── BUBBLE CHART ─────────────────────────────────────── */}
            <div className="mb-7 rounded-xl border border-border bg-card overflow-hidden h-[600px] md:h-[520px]">
              {industryLoading ? (
                <div className="w-full h-full animate-pulse bg-muted/30" />
              ) : industryBubbles.length > 0 ? (
                <SectorPerformance variant="embedded" data={industryBubbles} />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-sm text-muted-foreground">
                  尚無產業市值資料
                </div>
              )}
            </div>

            {/* ── INDUSTRY BOARD ───────────────────────────────────── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5">
                <BarChart3 size={13} className="text-muted-foreground" />
                <h2 className="text-sm font-semibold">產業總覽</h2>
              </div>
              <SortToggle value={sortKey} onChange={setSortKey} />
            </div>
            <BoardGrid loading={loading} items={sortedBoard} empty="目前沒有產業資料。" />
          </>
        ) : (
          <>
            {/* ── BUBBLE CHART (討論熱度 × 漲跌, sized by 成交值) ───────── */}
            <div className="mb-7 rounded-xl border border-border bg-card overflow-hidden h-[600px] md:h-[520px]">
              {themeLoading ? (
                <div className="w-full h-full animate-pulse bg-muted/30" />
              ) : themeBubbles.length > 0 ? (
                <SectorPerformance
                  variant="embedded"
                  data={themeBubbles}
                  xAxisLabel="討論熱度（近 7 日加權）"
                  xTickSuffix=""
                  xTooltipLabel="討論熱度"
                  radiusTooltipLabel="今日成交值"
                  radiusTooltipSuffix=" 億"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-sm text-muted-foreground">
                  尚無題材熱度資料
                </div>
              )}
            </div>

            {/* ── HERO STRIP ───────────────────────────────────────── */}
            <div className="mb-7">
              <div className="flex items-center gap-1.5 mb-2.5">
                <Flame size={13} className="text-accent-info" />
                <h2 className="text-sm font-semibold">今日漲幅最強</h2>
              </div>
              <div className="flex gap-2.5 overflow-x-auto pb-1 -mx-0.5 px-0.5 scrollbar-none">
                {loading
                  ? Array.from({ length: 5 }).map((_, i) => <HeroSkeleton key={i} />)
                  : heroThemes.length > 0
                    ? heroThemes.map((s) => <SectorHeroCard key={s.exposure_id} sector={s} />)
                    : (
                      <div className="flex-1 bg-card border border-border rounded-xl p-4 text-sm text-muted-foreground text-center">
                        尚無漲跌幅資料
                      </div>
                    )}
              </div>
            </div>

            {/* ── THEME BOARD ──────────────────────────────────────── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5">
                <BarChart3 size={13} className="text-muted-foreground" />
                <h2 className="text-sm font-semibold">題材總覽</h2>
              </div>
              <SortToggle value={sortKey} onChange={setSortKey} />
            </div>
            <BoardGrid loading={loading} items={sortedBoard} empty="目前沒有題材資料。" />

            {/* ── TAGS ─────────────────────────────────────────────── */}
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
          </>
        )}
      </PageContent>
    </>
  );
};

function BoardGrid({ loading, items, empty }: { loading: boolean; items: SectorBoardItem[]; empty: string }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <BoardSkeleton key={i} />)}
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
        {empty}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map((s) => (
        <SectorBoardCard key={s.exposure_id} sector={s} />
      ))}
    </div>
  );
}
