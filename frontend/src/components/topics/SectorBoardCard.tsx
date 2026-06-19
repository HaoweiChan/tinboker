import React from 'react';
import { Link } from 'react-router-dom';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import { SectorIcon } from './SectorIcon';
import { ChangePct } from './ChangePct';
import type { SectorBoardItem, SectorBoardMember } from '@/services/api/podcasts';

// ── MemberRow ──────────────────────────────────────────────────────────────
// Separate component so useStockTrendColor is called at hook top level (not in map).

interface MemberRowProps {
  member: SectorBoardMember;
}

const MemberRow: React.FC<MemberRowProps> = ({ member }) => {
  const trend = useStockTrendColor(member.change_percent ?? 0);
  const hasChange = member.change_percent != null && Number.isFinite(member.change_percent);
  const hasSeries = member.series && member.series.length > 1;

  return (
    <div className="flex items-center gap-2 py-1.5 first:pt-0 last:pb-0">
      {/* Ticker */}
      <span className="font-mono text-[11px] text-muted-foreground tabular-nums min-w-[3.5rem] shrink-0 leading-none">
        {member.ticker.replace(/\.[A-Z]+$/i, '')}
      </span>

      {/* Name */}
      <span className="text-[11px] text-foreground/80 truncate flex-1 min-w-0 leading-none">
        {member.name}
      </span>

      {/* Sparkline slot — skeleton when no series */}
      <div className="shrink-0 w-[44px] h-[18px] flex items-center">
        {hasSeries ? (
          <SimpleSparkline
            data={member.series}
            isPositive={(member.change_percent ?? 0) >= 0}
            color={hasChange ? trend.lineColor : undefined}
            width={44}
            height={18}
          />
        ) : (
          <span className="w-full h-[10px] animate-pulse bg-muted rounded" />
        )}
      </div>

      {/* Change % slot — skeleton when null */}
      <div className="shrink-0 w-[3.8rem] flex justify-end">
        <ChangePct
          value={member.change_percent}
          sizeClass="text-[11px]"
          skeleton
        />
      </div>
    </div>
  );
};

// ── SectorBoardCard ────────────────────────────────────────────────────────

interface SectorBoardCardProps {
  sector: SectorBoardItem;
}

/**
 * Card in the 題材總覽 grid.
 * - Sector icon + type badge + name + aggregate change in the header
 * - Up to 4 member rows with individual sparklines and change %
 */
export const SectorBoardCard: React.FC<SectorBoardCardProps> = ({ sector }) => {
  const trend = useStockTrendColor(sector.avg_change ?? 0);
  const hasChange = sector.avg_change != null && Number.isFinite(sector.avg_change);
  const topMembers = sector.members.slice(0, 4);

  const typeLabel =
    sector.exposure_type === 'sector' ? '產業'
    : sector.exposure_type === 'theme' ? '主題'
    : '總經';

  return (
    <div
      className="bg-card border border-border rounded-xl overflow-hidden transition-all duration-200
                 hover:border-border/70 hover:shadow-[0_2px_16px_-4px_rgba(0,0,0,0.12)]
                 dark:hover:shadow-[0_2px_16px_-4px_rgba(0,0,0,0.4)]"
    >
      {/* ── Card header ─────────────────────────────────────────── */}
      <Link
        to={`/sector/${encodeURIComponent(sector.exposure_id)}`}
        className="group flex items-start justify-between gap-3 px-4 pt-3.5 pb-3 border-b border-border/40"
      >
        {/* Left: icon + badge + name */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1.5">
            <SectorIcon
              exposureId={sector.exposure_id}
              size={13}
              className="text-muted-foreground/70 shrink-0"
            />
            <span className="text-[10px] font-medium text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded leading-none shrink-0">
              {typeLabel}
            </span>
          </div>
          <span className="text-[14px] font-semibold tracking-[-0.01em] group-hover:text-foreground/80 transition-colors leading-snug block">
            {sector.display_name}
          </span>
        </div>

        {/* Right: aggregate change + episode count */}
        <div className="shrink-0 flex flex-col items-end gap-1 pt-0.5">
          <ChangePct
            value={sector.avg_change}
            sizeClass="text-[15px]"
            showArrow
            skeleton={false}
          />
          <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
            {sector.episode_count} 集
          </span>
        </div>
      </Link>

      {/* ── Member rows ─────────────────────────────────────────── */}
      {topMembers.length > 0 && (
        <div className="px-4 py-2 divide-y divide-border/25">
          {topMembers.map((m) => (
            <MemberRow key={m.ticker} member={m} />
          ))}
        </div>
      )}

      {/* Bottom accent bar — color-matched to trend */}
      {hasChange && (
        <div
          className="h-[2px] w-full"
          style={{ backgroundColor: trend.lineColor, opacity: 0.35 }}
        />
      )}
    </div>
  );
};
