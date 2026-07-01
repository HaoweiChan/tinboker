import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ChartScatter, Layers, Hash, Info, ListTree, ChevronDown } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign/Segmented';
import SectorPerformance from '@/components/industry/SectorPerformance';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TOPICS_TYPOGRAPHY } from '@/components/topics/topicsTypography';
import {
  getSectorBoard,
  getExposurePerformance,
  getTrendingTags,
  getBatchPricesTrailing,
  type SectorBoardItem,
  type ExposurePerformanceItem,
  type TrailingPerf,
  type TrendingTag,
} from '@/services/api/podcasts';
import type { SectorBubbleData } from '@/services/mocks/types';
import { fetchWithFallback } from '@/services/api/migration';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';

// ── Sort types ───────────────────────────────────────────────────────────────

type SortKey = 'hotness' | 'avg_change' | 'episode_count';
type BubbleSource = {
  exposure_id: string;
  display_name: string;
  heat?: number | null;
  episode_count: number;
  return_pct: number | null;
  trading_value_twd?: number | null;
  trading_value_windows_twd?: Record<string, number> | null;
};

// Return-axis timeframe for the bubble chart (trailing close-to-close % per window).
type TF = '1' | '7' | '30' | '90';
const TF_OPTIONS = [
  { value: '1' as const, label: '1日' },
  { value: '7' as const, label: '7日' },
  { value: '30' as const, label: '30日' },
  { value: '90' as const, label: '90日' },
];

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'hotness', label: '綜合熱度' },
  { value: 'avg_change', label: '今日表現' },
  { value: 'episode_count', label: '討論熱度' },
];

// ── Skeleton cards ─────────────────────────────────────────────────────────

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
  const navigate = useNavigate();
  const type = TOPICS_TYPOGRAPHY.className;
  const iconSize = TOPICS_TYPOGRAPHY.iconSize;
  const openExposure = (id: string) => navigate(`/sector/${encodeURIComponent(id)}`);
  const [sectors, setSectors] = useState<SectorBoardItem[]>([]);
  const [perf, setPerf] = useState<ExposurePerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [perfLoading, setPerfLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('hotness');
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const [tf, setTf] = useState<TF>('1');
  const [trailing, setTrailing] = useState<Record<string, TrailingPerf>>({});
  const [trailingLoading, setTrailingLoading] = useState(false);
  const tagLabels = useTagLabels();

  // Board — every exposure (split by exposure_type for the theme hero vs the industry drawer).
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

  // Unified exposure performance (bubble chart) — heat × return, sized by trading value.
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await getExposurePerformance().catch(() => [] as ExposurePerformanceItem[]);
      if (!alive) return;
      setPerf(res);
      setPerfLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  // Trending tags → 總經與焦點議題 chip strip (cross-sector policy/macro topics).
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
    () => sectors.filter((s) => s.exposure_type === 'industry'),
    [sectors],
  );
  const themeBoard = useMemo(
    () => sectors.filter((s) => s.exposure_type === 'theme'),
    [sectors],
  );
  const themePerf = useMemo(
    () => perf.filter((p) => p.exposure_type === 'theme'),
    [perf],
  );

  // exposure_id → constituent tickers (from the board), so the bubble Y can be recomputed
  // per timeframe from trailing returns without the perf endpoint carrying member lists.
  const membersByExposure = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const s of sectors) m[s.exposure_id] = (s.members || []).map((x) => x.ticker.toUpperCase());
    return m;
  }, [sectors]);

  // exposure_id → lucide icon name (from the board), to draw an icon inside each bubble.
  const iconByExposure = useMemo(() => {
    const m: Record<string, string | null | undefined> = {};
    for (const s of sectors) m[s.exposure_id] = s.icon_id;
    return m;
  }, [sectors]);

  const boardByExposure = useMemo(() => {
    const m: Record<string, SectorBoardItem> = {};
    for (const s of sectors) m[s.exposure_id] = s;
    return m;
  }, [sectors]);

  // Fetch trailing 1/7/30/90D returns for every board constituent (chunked — the endpoint
  // caps at 60 tickers/call), so the TF toggle re-plots Y client-side with no refetch.
  useEffect(() => {
    const union = [...new Set(Object.values(membersByExposure).flat())];
    if (!union.length) return;
    let alive = true;
    (async () => {
      setTrailingLoading(true);
      const chunks: string[][] = [];
      for (let i = 0; i < union.length; i += 60) chunks.push(union.slice(i, i + 60));
      const results: Record<string, TrailingPerf>[] = [];
      for (const chunk of chunks) {
        results.push(await getBatchPricesTrailing(chunk).catch(() => ({})));
      }
      if (!alive) return;
      setTrailing(Object.assign({}, ...results));
      setTrailingLoading(false);
    })();
    return () => { alive = false; };
  }, [membersByExposure]);

  // Average member trailing return for the selected timeframe (skips tickers with no data).
  const memberReturn = useMemo(() => {
    const ready = Object.keys(trailing).length > 0;
    return (exposureId: string, fallback: number | null): number | null => {
      if (!ready || trailingLoading) return fallback;
      const vals = (membersByExposure[exposureId] || [])
        .map((t) => trailing[t]?.[`d${tf}` as 'd1' | 'd7' | 'd30' | 'd90'])
        .filter((v): v is number => v != null);
      if (vals.length) return +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
      return tf === '1' ? fallback : null;
    };
  }, [trailing, trailingLoading, membersByExposure, tf]);

  const tfLabel = TF_OPTIONS.find((o) => o.value === tf)?.label ?? '';
  const yAxisLabel = `近期漲跌 %（${tfLabel}）`;

  // Timeframe toggle rendered inside the chart card (top-left of the legend bar).
  const tfToggle = (
    <div className={`flex shrink-0 items-center gap-0.5 whitespace-nowrap ${type.micro}`}>
      <span className="mr-1 hidden text-muted-foreground/60 min-[420px]:inline">漲跌期間</span>
      {TF_OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => setTf(o.value as TF)}
          className={`shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 transition-colors ${
            tf === o.value
              ? 'bg-primary/15 font-semibold text-primary'
              : 'text-muted-foreground/70 hover:text-foreground'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );

  // Theme bubble: X = discussion heat, Y = return %, size = cumulative trading value.
  const themeBubbles = useMemo<SectorBubbleData[]>(
    () => {
      const source: BubbleSource[] = themePerf.length
        ? themePerf
        : themeBoard.map((s) => ({
            exposure_id: s.exposure_id,
            display_name: s.display_name,
            heat: s.heat,
            episode_count: s.episode_count,
            return_pct: s.avg_change,
            trading_value_windows_twd: null,
          }));
      return source.map((t) => {
        const board = boardByExposure[t.exposure_id];
        const heat = t.heat ?? board?.heat ?? 0;
        const tradingValueTwd = t.trading_value_windows_twd?.[tf] ?? (tf === '1' ? t.trading_value_twd : 0) ?? 0;
        const tradingValueYi = tradingValueTwd ? +(tradingValueTwd / 1e8).toFixed(0) : 0;
        return {
          id: t.exposure_id,
          name: t.display_name,
          label: t.display_name,
          icon_id: iconByExposure[t.exposure_id],
          value: heat,
          x: +heat.toFixed(1),
          r: tradingValueYi,
          subLabel: `${t.episode_count} 集討論 · ${tf}日成交值${tradingValueYi ? `${tradingValueYi}億` : '暫無資料'}`,
          return: memberReturn(t.exposure_id, t.return_pct),
          returnRate: memberReturn(t.exposure_id, t.return_pct),
        };
      });
    },
    [themePerf, themeBoard, boardByExposure, tf, memberReturn, iconByExposure],
  );

  const sortedThemeBoard = useMemo(() => sortBoard(themeBoard, sortKey), [themeBoard, sortKey]);
  // Industry drawer is secondary — always hotness-sorted, no own control.
  const sortedIndustryBoard = useMemo(() => sortBoard(industryBoard, 'hotness'), [industryBoard]);

  return (
    <>
      <SEO
        title="話題排行"
        description="今日最強題材焦點 — 依題材聚合，顯示漲跌幅、資金流與相關個股表現。"
      />
      <PageContent>
        {/* Page header */}
        <div className="flex items-center justify-between mb-1">
          <h1 className={`${type.pageTitle} font-semibold tracking-[-0.02em]`}>話題排行</h1>
          {themeBoard.length > 0 && (
            <div className={`${type.meta} text-muted-foreground font-mono tabular-nums flex items-center gap-1.5`}>
              <Layers size={12} />
              <span>{themeBoard.length} 題材</span>
            </div>
          )}
        </div>
        <p className={`${type.body} text-muted-foreground mb-5 max-w-[60ch]`}>
          今日最強題材焦點 — 短線概念聚合，顯示漲跌幅與相關個股。完整產業分類收於頁尾。
        </p>

        {/* Data-freshness disclaimer: prices come from the last *completed* daily bar,
            not live ticks — so before today's close the figures may be the prior day's. */}
        <p className={`mb-6 flex items-start gap-1.5 ${type.meta} text-muted-foreground`}>
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>漲跌採用最近一個<strong className="font-medium text-foreground/80">完整交易日</strong>的收盤資料，非即時報價；當日尚未收盤結算前，可能顯示前一交易日數據。</span>
        </p>

        {/* ── THEME BUBBLE CHART (hero) ─────────────────────────────── */}
        <div className="flex items-center gap-1.5 mb-2.5">
          <ChartScatter size={iconSize.section} className="text-accent-info" />
          <h2 className={`${type.sectionTitle} font-semibold`}>題材泡泡圖</h2>
        </div>
        <div className="mb-7 rounded-xl border border-border bg-card overflow-hidden md:h-[520px]">
          {perfLoading ? (
            <div className="w-full h-full animate-pulse bg-muted/30" />
          ) : themeBubbles.length > 0 ? (
            <SectorPerformance
              variant="embedded"
              data={themeBubbles}
              xAxisLabel="討論熱度（近 7 日加權，log）"
              xTickSuffix=""
              xTooltipLabel="討論熱度"
              xScaleMode="log"
              xHelp="X 軸：討論熱度（近 7 日 Podcast 提及加權，半衰期 7 天，越近期權重越高），以 log 尺度顯示以展開低熱度區；Y 軸：近期漲跌；泡泡大小：所選期間聚合成交值；顏色：題材別。"
              yAxisLabel={yAxisLabel}
              headerLeft={tfToggle}
              onSelectExposure={openExposure}
              radiusTooltipLabel={`${tf}日成交值`}
              radiusTooltipSuffix="億"
            />
          ) : (
            <div className={`w-full h-full flex items-center justify-center ${type.empty} text-muted-foreground`}>
              尚無題材熱度資料
            </div>
          )}
        </div>

        {/* ── THEME BOARD ───────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            <ListTree size={iconSize.section} className="text-accent-info" />
            <h2 className={`${type.sectionTitle} font-semibold`}>題材總覽</h2>
          </div>
          <Segmented options={SORT_OPTIONS} value={sortKey} onChange={setSortKey} />
        </div>
        <BoardGrid loading={loading} items={sortedThemeBoard} empty="目前沒有題材資料。" />

        {/* ── 總經與焦點議題 (tag chip strip) ────────────────────────── */}
        <div className="flex items-center gap-1.5 mt-9 mb-1.5">
          <Hash size={iconSize.section} className="text-amber-500" />
          <h2 className={`${type.sectionTitle} font-semibold`}>總經與焦點議題</h2>
        </div>
        <p className={`${type.meta} text-muted-foreground mb-3`}>
          跨產業的政策與總經話題，點擊探索相關集數。
        </p>
        {tags.length > 0 ? (
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 [scrollbar-width:thin]">
            {tags.map((t) => (
              <Link
                key={t.id}
                to={`/topics/${encodeURIComponent(t.id)}`}
                className={`group shrink-0 inline-flex items-center gap-1.5 rounded-full border border-border bg-card
                            px-3 py-1.5 transition-colors hover:border-amber-500/50 hover:bg-amber-500/[0.06] ${type.meta}`}
              >
                <Hash size={11} className="text-amber-500 shrink-0" />
                <span className="font-medium text-foreground/85 whitespace-nowrap group-hover:text-foreground">
                  {tagLabelFor(t.id, tagLabels)}
                </span>
                <span className="font-mono tabular-nums text-muted-foreground whitespace-nowrap">{t.scoped_count}</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className={`bg-card border border-border rounded-xl p-6 text-center ${type.empty} text-muted-foreground`}>
            目前沒有議題資料。
          </div>
        )}

        {/* ── 產業地圖 (collapsible secondary market map) ─────────────── */}
        <details className="group mt-9 rounded-xl border border-border overflow-hidden">
          <summary className="flex items-center justify-between gap-2 px-4 py-3 cursor-pointer list-none select-none [&::-webkit-details-marker]:hidden hover:bg-muted/30 transition-colors">
            <div className="flex items-center gap-1.5 min-w-0">
              <ListTree size={iconSize.section} className="text-primary shrink-0" />
              <h2 className={`${type.sectionTitle} font-semibold`}>產業地圖</h2>
              <span className={`${type.meta} text-muted-foreground truncate`}>
                完整市場分類{industryBoard.length > 0 ? ` · ${industryBoard.length} 產業` : ''}
              </span>
            </div>
            <ChevronDown size={16} className="text-muted-foreground shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4 pt-1">
            <p className={`${type.meta} text-muted-foreground mb-3 max-w-[60ch]`}>
              台股完整產業分類（個股各歸一類）。題材為跨產業概念，同一檔個股可同時屬於多個題材。
            </p>
            <BoardGrid loading={loading} items={sortedIndustryBoard} empty="目前沒有產業資料。" />
          </div>
        </details>
      </PageContent>
    </>
  );
};

function BoardGrid({ loading, items, empty }: { loading: boolean; items: SectorBoardItem[]; empty: string }) {
  const type = TOPICS_TYPOGRAPHY.className;
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <BoardSkeleton key={i} />)}
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className={`bg-card border border-border rounded-xl p-10 text-center ${type.empty} text-muted-foreground`}>
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
