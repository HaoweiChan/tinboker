import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Minus, ArrowUpRight, ArrowDownRight, BarChart3, Flame, Layers } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import {
  getSectorBoard,
  type SectorBoardItem,
  type SectorBoardMember,
} from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

// ── Sort types ─────────────────────────────────────────────────────

type SortKey = 'hotness' | 'avg_change' | 'episode_count';

// ── Helpers ────────────────────────────────────────────────────────

function exposureTypeLabel(t: string): string {
  if (t === 'sector') return '產業';
  if (t === 'theme') return '主題';
  if (t === 'macro') return '總經';
  return t;
}

// ── ChangeArrow: arrow icon that obeys TW/US color convention ──────

function ChangeArrow({ value, size = 14 }: { value: number | null; size?: number }) {
  const trend = useStockTrendColor(value ?? 0);
  if (value == null || !Number.isFinite(value)) {
    return <Minus size={size} className="text-muted-foreground" />;
  }
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return <Icon size={size} className={trend.text} />;
}

// ── Hero tile: one top-gainer sector ──────────────────────────────

function HeroTile({ sector }: { sector: SectorBoardItem }) {
  const trend = useStockTrendColor(sector.avg_change ?? 0);
  const hasChange = sector.avg_change != null && Number.isFinite(sector.avg_change);
  const typeLabel = exposureTypeLabel(sector.exposure_type);

  return (
    <Link
      to={`/sector/${encodeURIComponent(sector.exposure_id)}`}
      className="group relative flex flex-col justify-between min-w-[140px] flex-1 bg-card border border-border rounded-lg p-4 overflow-hidden
                 hover:border-accent-info/50 hover:shadow-[0_0_16px_-4px_hsl(var(--accent-info)/0.18)] transition-all duration-200"
    >
      {/* Top: type badge */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-medium text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">
          {typeLabel}
        </span>
        {hasChange && (
          <ChangeArrow value={sector.avg_change} size={13} />
        )}
      </div>

      {/* Name */}
      <div className="text-[14px] font-semibold tracking-[-0.01em] mb-2 group-hover:text-accent-info transition-colors leading-snug">
        {sector.display_name}
      </div>

      {/* Big change number */}
      <div className="flex items-baseline gap-1">
        {hasChange ? (
          <span className={`font-mono text-[22px] font-bold tabular-nums leading-none ${trend.text}`}>
            {sector.avg_change! >= 0 ? '+' : ''}{sector.avg_change!.toFixed(2)}%
          </span>
        ) : (
          <span className="font-mono text-[22px] font-bold tabular-nums leading-none text-muted-foreground">—</span>
        )}
      </div>

      {/* Episode count */}
      <div className="mt-2 text-[10px] text-muted-foreground font-mono tabular-nums">
        {sector.episode_count} 集
      </div>

      {/* Subtle accent line at bottom */}
      {hasChange && (
        <div
          className={`absolute bottom-0 left-0 right-0 h-0.5 ${trend.bg} opacity-60`}
        />
      )}
    </Link>
  );
}

// ── Member chip row inside a board card ───────────────────────────

function MemberRow({ member }: { member: SectorBoardMember }) {
  const trend = useStockTrendColor(member.change_percent ?? 0);
  const hasChange = member.change_percent != null && Number.isFinite(member.change_percent);

  return (
    <div className="flex items-center gap-2 py-1 first:pt-0 last:pb-0">
      <span className="font-mono text-[11px] text-muted-foreground tabular-nums min-w-[3.5rem] shrink-0">
        {member.ticker.replace(/\.[A-Z]+$/i, '')}
      </span>
      <span className="text-[11px] text-foreground truncate flex-1 min-w-0">
        {member.name}
      </span>
      {hasChange ? (
        <span className={`font-mono text-[11px] tabular-nums font-medium shrink-0 ${trend.text}`}>
          {member.change_percent! >= 0 ? '+' : ''}{member.change_percent!.toFixed(2)}%
        </span>
      ) : (
        <span className="font-mono text-[11px] text-muted-foreground shrink-0">—</span>
      )}
    </div>
  );
}

// ── Board card ─────────────────────────────────────────────────────

function BoardCard({ sector }: { sector: SectorBoardItem }) {
  const trend = useStockTrendColor(sector.avg_change ?? 0);
  const hasChange = sector.avg_change != null && Number.isFinite(sector.avg_change);
  const typeLabel = exposureTypeLabel(sector.exposure_type);
  const topMembers = sector.members.slice(0, 4);

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden transition-all duration-200
                    hover:border-accent-info/40 hover:shadow-[0_0_12px_-3px_hsl(var(--accent-info)/0.15)]">
      {/* Card header */}
      <Link
        to={`/sector/${encodeURIComponent(sector.exposure_id)}`}
        className="group flex items-start justify-between gap-2 px-4 pt-3.5 pb-3 border-b border-border/50"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-medium text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded shrink-0">
              {typeLabel}
            </span>
          </div>
          <span className="text-[15px] font-semibold tracking-[-0.01em] group-hover:text-accent-info transition-colors leading-snug block">
            {sector.display_name}
          </span>
        </div>

        {/* Aggregate change */}
        <div className="shrink-0 flex flex-col items-end gap-0.5 pt-0.5">
          <div className="flex items-center gap-0.5">
            <ChangeArrow value={sector.avg_change} size={14} />
            {hasChange ? (
              <span className={`font-mono text-[16px] font-bold tabular-nums ${trend.text}`}>
                {sector.avg_change! >= 0 ? '+' : ''}{sector.avg_change!.toFixed(2)}%
              </span>
            ) : (
              <span className="font-mono text-[16px] font-bold text-muted-foreground">—</span>
            )}
          </div>
          <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
            {sector.episode_count} 集
          </span>
        </div>
      </Link>

      {/* Member rows */}
      {topMembers.length > 0 && (
        <div className="px-4 py-2.5 divide-y divide-border/30">
          {topMembers.map((m) => (
            <MemberRow key={m.ticker} member={m} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sort toggle ────────────────────────────────────────────────────

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'hotness', label: '綜合熱度' },
  { key: 'avg_change', label: '今日表現' },
  { key: 'episode_count', label: '討論熱度' },
];

function SortToggle({ value, onChange }: { value: SortKey; onChange: (k: SortKey) => void }) {
  return (
    <div className="flex items-center gap-1 bg-muted/50 border border-border rounded-lg p-0.5">
      {SORT_OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-all duration-150
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

// ── Skeleton ───────────────────────────────────────────────────────

function BoardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-lg p-4 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="h-3 w-10 bg-muted rounded mb-2" />
          <div className="h-4 w-28 bg-muted rounded" />
        </div>
        <div className="h-6 w-16 bg-muted rounded" />
      </div>
      <div className="space-y-2 pt-2 border-t border-border/50">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex gap-2 items-center">
            <div className="h-3 w-10 bg-muted rounded" />
            <div className="h-3 flex-1 bg-muted rounded" />
            <div className="h-3 w-12 bg-muted rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

function HeroSkeleton() {
  return (
    <div className="flex-1 min-w-[140px] bg-card border border-border rounded-lg p-4 animate-pulse">
      <div className="h-3 w-10 bg-muted rounded mb-3" />
      <div className="h-4 w-20 bg-muted rounded mb-2" />
      <div className="h-7 w-16 bg-muted rounded" />
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────

export const TopicsCloud: React.FC = () => {
  const [sectors, setSectors] = useState<SectorBoardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('hotness');

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

  // Top gainers for hero strip (sorted by avg_change desc, up to 5)
  const heroSectors = useMemo(() => {
    return [...sectors]
      .filter((s) => s.avg_change != null && Number.isFinite(s.avg_change))
      .sort((a, b) => (b.avg_change ?? -Infinity) - (a.avg_change ?? -Infinity))
      .slice(0, 5);
  }, [sectors]);

  // Board sorted by selected key
  const sortedSectors = useMemo(() => {
    return [...sectors].sort((a, b) => {
      if (sortKey === 'hotness') return (b.hotness ?? 0) - (a.hotness ?? 0);
      if (sortKey === 'avg_change') {
        const av = a.avg_change ?? -Infinity;
        const bv = b.avg_change ?? -Infinity;
        return bv - av;
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
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">話題排行</h1>
          {hasData && (
            <div className="text-[12px] text-muted-foreground font-mono tabular-nums flex items-center gap-2">
              <Layers size={12} className="text-muted-foreground" />
              <span>{sectors.length} 題材</span>
            </div>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground mb-6 max-w-[60ch]">
          今日最強題材焦點 — 依產業/主題聚合，顯示漲跌幅與相關個股。
        </p>

        {/* ── HERO STRIP ─────────────────────────────────────────── */}
        <div className="mb-6">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Flame size={13} className="text-accent-info" />
            <h2 className="text-[13px] font-semibold">今日漲幅最強</h2>
          </div>
          <div className="flex gap-2.5 overflow-x-auto pb-1 -mx-0.5 px-0.5">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => <HeroSkeleton key={i} />)
              : heroSectors.length > 0
                ? heroSectors.map((s) => <HeroTile key={s.exposure_id} sector={s} />)
                : (
                  <div className="flex-1 bg-card border border-border rounded-lg p-4 text-[13px] text-muted-foreground text-center">
                    尚無漲跌幅資料
                  </div>
                )
            }
          </div>
        </div>

        {/* ── BOARD ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            <BarChart3 size={13} className="text-muted-foreground" />
            <h2 className="text-[13px] font-semibold">題材總覽</h2>
          </div>
          <SortToggle value={sortKey} onChange={setSortKey} />
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => <BoardSkeleton key={i} />)}
          </div>
        ) : sectors.length === 0 ? (
          <div className="bg-card border border-border rounded-lg p-10 text-center text-[13px] text-muted-foreground">
            目前沒有題材資料。
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sortedSectors.map((s) => (
              <BoardCard key={s.exposure_id} sector={s} />
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};
