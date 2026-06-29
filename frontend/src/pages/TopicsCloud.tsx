import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChartScatter, Layers, Hash, Info, ListTree } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented } from '@/components/redesign/Segmented';
import SectorPerformance from '@/components/industry/SectorPerformance';
import { SectorBoardCard } from '@/components/topics/SectorBoardCard';
import { TagBoardCard } from '@/components/topics/TagBoardCard';
import { TOPICS_TYPOGRAPHY } from '@/components/topics/topicsTypography';
import {
  getSectorBoard,
  getIndustryPerformance,
  getThemePerformance,
  getTrendingTags,
  getBatchPricesTrailing,
  type SectorBoardItem,
  type IndustryPerformanceItem,
  type ThemePerformanceItem,
  type TrailingPerf,
  type TrendingTag,
} from '@/services/api/podcasts';
import type { SectorBubbleData } from '@/services/mocks/types';
import { fetchWithFallback } from '@/services/api/migration';
import { useTagLabels, tagLabelFor } from '@/hooks/useTagLabels';

// ── Tab + sort types ─────────────────────────────────────────────────────────

type TabKey = 'theme' | 'industry' | 'tag';
type SortKey = 'hotness' | 'avg_change' | 'episode_count';
type BubbleSource = {
  exposure_id: string;
  display_name: string;
  heat?: number | null;
  episode_count: number;
  return_pct: number | null;
  market_cap_twd?: number | null;
  trading_value_twd?: number | null;
  trading_value_windows_twd?: Record<string, number> | null;
};

const TAB_OPTIONS = [
  { value: 'theme' as const, label: '題材' },
  { value: 'industry' as const, label: '產業' },
  { value: 'tag' as const, label: '標籤' },
];

// Return-axis timeframe for the bubble charts (trailing close-to-close % per window).
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
  const [tab, setTab] = useState<TabKey>('theme');
  const [sectors, setSectors] = useState<SectorBoardItem[]>([]);
  const [industries, setIndustries] = useState<IndustryPerformanceItem[]>([]);
  const [themes, setThemes] = useState<ThemePerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [industryLoading, setIndustryLoading] = useState(true);
  const [themeLoading, setThemeLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('hotness');
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const [tf, setTf] = useState<TF>('1');
  const [trailing, setTrailing] = useState<Record<string, TrailingPerf>>({});
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

  // Trending tags (free-form topics, shown on the 標籤 tab)
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

  // exposure_id → constituent tickers (from the board), so the bubble Y can be recomputed
  // per timeframe from trailing returns without the perf endpoints carrying member lists.
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
      const chunks: string[][] = [];
      for (let i = 0; i < union.length; i += 60) chunks.push(union.slice(i, i + 60));
      const results = await Promise.all(chunks.map((c) => getBatchPricesTrailing(c).catch(() => ({}))));
      if (!alive) return;
      setTrailing(Object.assign({}, ...results));
    })();
    return () => { alive = false; };
  }, [membersByExposure]);

  // Average member trailing return for the selected timeframe (skips tickers with no data).
  const memberReturn = useMemo(() => {
    const ready = Object.keys(trailing).length > 0;
    return (exposureId: string, fallback: number | null): number => {
      if (!ready) return tf === '1' ? (fallback ?? 0) : 0;
      const vals = (membersByExposure[exposureId] || [])
        .map((t) => trailing[t]?.[`d${tf}` as 'd1' | 'd7' | 'd30' | 'd90'])
        .filter((v): v is number => v != null);
      if (vals.length) return +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
      return tf === '1' ? (fallback ?? 0) : 0;
    };
  }, [trailing, membersByExposure, tf]);

  const tfLabel = TF_OPTIONS.find((o) => o.value === tf)?.label ?? '';
  const yAxisLabel = `近期漲跌 %（${tfLabel}）`;

  // Timeframe toggle rendered inside each chart card (top-left of the legend bar).
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

  const hasIndustryTradingValue = useMemo(
    () =>
      industries.some((i) => {
        const value = i.trading_value_windows_twd?.[tf] ?? (tf === '1' ? i.trading_value_twd : 0) ?? 0;
        return value > 0;
      }),
    [industries, tf],
  );

  // Bubble-chart shape: X = discussion heat, Y = return %, size = cumulative trading value.
  const industryBubbles = useMemo<SectorBubbleData[]>(
    () => {
      const source: BubbleSource[] = industries.length
        ? industries
        : industryBoard.map((s) => ({
            exposure_id: s.exposure_id,
            display_name: s.display_name,
            heat: s.heat,
            episode_count: s.episode_count,
            return_pct: s.avg_change,
            trading_value_windows_twd: null,
          }));
      return source.map((i) => {
        const board = boardByExposure[i.exposure_id];
        const heat = i.heat ?? board?.heat ?? 0;
        const tradingValueTwd = i.trading_value_windows_twd?.[tf] ?? (tf === '1' ? i.trading_value_twd : 0) ?? 0;
        const tradingValueYi = tradingValueTwd ? +(tradingValueTwd / 1e8).toFixed(0) : 0;
        const marketCapT = i.market_cap_twd ? +(i.market_cap_twd / 1e12).toFixed(2) : 0;
        const sizeValue = hasIndustryTradingValue ? tradingValueYi : marketCapT;
        const sizeLabel = hasIndustryTradingValue
          ? `${tf}日成交值${tradingValueYi ? `${tradingValueYi}億` : '暫無資料'}`
          : `市值${marketCapT ? `${marketCapT}兆` : '暫無資料'}`;
        return {
          id: i.exposure_id,
          name: i.display_name,
          label: i.display_name,
          icon_id: iconByExposure[i.exposure_id],
          value: heat,
          x: +heat.toFixed(1),
          r: sizeValue,
          subLabel: `${i.episode_count} 集討論 · ${sizeLabel}`,
          return: memberReturn(i.exposure_id, i.return_pct),
          returnRate: memberReturn(i.exposure_id, i.return_pct),
        };
      });
    },
    [industries, industryBoard, boardByExposure, hasIndustryTradingValue, tf, memberReturn, iconByExposure],
  );

  // Theme bubble: X = discussion heat, Y = return %, size = cumulative trading value.
  const themeBubbles = useMemo<SectorBubbleData[]>(
    () => {
      const source: BubbleSource[] = themes.length
        ? themes
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
    [themes, themeBoard, boardByExposure, tf, memberReturn, iconByExposure],
  );

  const visibleBoard = tab === 'industry' ? industryBoard : themeBoard;
  const sortedBoard = useMemo(() => sortBoard(visibleBoard, sortKey), [visibleBoard, sortKey]);
  const headerCount = tab === 'tag' ? tags.length : visibleBoard.length;
  const headerUnit = tab === 'industry' ? '產業' : tab === 'tag' ? '標籤' : '題材';

  return (
    <>
      <SEO
        title="話題排行"
        description="今日最強題材焦點 — 依產業/主題聚合，顯示漲跌幅與相關個股表現。"
      />
      <PageContent>
        {/* Page header */}
        <div className="flex items-center justify-between mb-1">
          <h1 className={`${type.pageTitle} font-semibold tracking-[-0.02em]`}>話題排行</h1>
          {headerCount > 0 && (
            <div className={`${type.meta} text-muted-foreground font-mono tabular-nums flex items-center gap-1.5`}>
              <Layers size={12} />
              <span>{headerCount} {headerUnit}</span>
            </div>
          )}
        </div>
        <p className={`${type.body} text-muted-foreground mb-5 max-w-[60ch]`}>
          {tab === 'industry'
            ? '台股產業地圖 — 近期討論熱度與漲跌，依產業別聚合。'
            : tab === 'tag'
              ? '熱門標籤 — 依近期節目提及聚合，快速探索相關集數。'
              : '今日最強題材焦點 — 短線概念聚合，顯示漲跌幅與相關個股。'}
        </p>

        {/* Tabs */}
        <Segmented options={TAB_OPTIONS} value={tab} onChange={(v) => setTab(v as TabKey)} className="mb-3" />

        {/* Data-freshness disclaimer: prices come from the last *completed* daily bar,
            not live ticks — so before today's close the figures may be the prior day's. */}
        <p className={`mb-6 flex items-start gap-1.5 ${type.meta} text-muted-foreground`}>
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>漲跌採用最近一個<strong className="font-medium text-foreground/80">完整交易日</strong>的收盤資料，非即時報價；當日尚未收盤結算前，可能顯示前一交易日數據。</span>
        </p>

        {tab === 'industry' ? (
          <>
            {/* ── BUBBLE CHART ─────────────────────────────────────── */}
            <div className="flex items-center gap-1.5 mb-2.5">
              <ChartScatter size={iconSize.section} className="text-primary" />
              <h2 className={`${type.sectionTitle} font-semibold`}>產業泡泡圖</h2>
            </div>
            <div className="mb-7 rounded-xl border border-border bg-card overflow-hidden md:h-[520px]">
              {industryLoading ? (
                <div className="w-full h-full animate-pulse bg-muted/30" />
              ) : industryBubbles.length > 0 ? (
                <SectorPerformance
                  variant="embedded"
                  data={industryBubbles}
                  xAxisLabel="討論熱度（近 7 日加權）"
                  xTickSuffix=""
                  xTooltipLabel="討論熱度"
                  xHelp={`X 軸：討論熱度（近 7 日 Podcast 提及加權，半衰期 7 天，越近期權重越高）；Y 軸：近期漲跌；泡泡大小：${hasIndustryTradingValue ? '所選期間聚合成交值' : '聚合市值'}；顏色：產業別。`}
                  yAxisLabel={yAxisLabel}
                  headerLeft={tfToggle}
                  onSelectExposure={openExposure}
                  radiusTooltipLabel={hasIndustryTradingValue ? `${tf}日成交值` : '市值'}
                  radiusTooltipSuffix={hasIndustryTradingValue ? '億' : '兆'}
                />
              ) : (
                <div className={`w-full h-full flex items-center justify-center ${type.empty} text-muted-foreground`}>
                  尚無產業熱度資料
                </div>
              )}
            </div>

            {/* ── INDUSTRY BOARD ───────────────────────────────────── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5">
                <ListTree size={iconSize.section} className="text-primary" />
                <h2 className={`${type.sectionTitle} font-semibold`}>產業總覽</h2>
              </div>
              <Segmented options={SORT_OPTIONS} value={sortKey} onChange={setSortKey} />
            </div>
            <BoardGrid loading={loading} items={sortedBoard} empty="目前沒有產業資料。" />
          </>
        ) : tab === 'theme' ? (
          <>
            {/* ── BUBBLE CHART ─────────────────────────────────────── */}
            <div className="flex items-center gap-1.5 mb-2.5">
              <ChartScatter size={iconSize.section} className="text-accent-info" />
              <h2 className={`${type.sectionTitle} font-semibold`}>題材泡泡圖</h2>
            </div>
            <div className="mb-7 rounded-xl border border-border bg-card overflow-hidden md:h-[520px]">
              {themeLoading ? (
                <div className="w-full h-full animate-pulse bg-muted/30" />
              ) : themeBubbles.length > 0 ? (
                <SectorPerformance
                  variant="embedded"
                  data={themeBubbles}
                  xAxisLabel="討論熱度（近 7 日加權）"
                  xTickSuffix=""
                  xTooltipLabel="討論熱度"
                  xHelp="X 軸：討論熱度（近 7 日 Podcast 提及加權，半衰期 7 天，越近期權重越高）；Y 軸：近期漲跌；泡泡大小：所選期間聚合成交值；顏色：題材別。"
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

            {/* ── THEME BOARD ──────────────────────────────────────── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5">
                <ListTree size={iconSize.section} className="text-accent-info" />
                <h2 className={`${type.sectionTitle} font-semibold`}>題材總覽</h2>
              </div>
              <Segmented options={SORT_OPTIONS} value={sortKey} onChange={setSortKey} />
            </div>
            <BoardGrid loading={loading} items={sortedBoard} empty="目前沒有題材資料。" />
          </>
        ) : (
          <>
            <div className="flex items-center gap-1.5 mb-3">
              <Hash size={iconSize.section} className="text-muted-foreground" />
              <h2 className={`${type.sectionTitle} font-semibold`}>熱門標籤</h2>
            </div>
            {tags.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {tags.map((t) => (
                  <TagBoardCard key={t.id} tag={t} label={tagLabelFor(t.id, tagLabels)} />
                ))}
              </div>
            ) : (
              <div className={`bg-card border border-border rounded-xl p-10 text-center ${type.empty} text-muted-foreground`}>
                目前沒有標籤資料。
              </div>
            )}
          </>
        )}
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
