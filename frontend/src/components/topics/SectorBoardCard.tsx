import React from 'react';
import { Link } from 'react-router-dom';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import { SectorIcon } from './SectorIcon';
import { ChangePct } from './ChangePct';
import { TOPICS_TYPOGRAPHY } from './topicsTypography';
import { StockIdentity } from '@/components/common/StockIdentity';
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
  const type = TOPICS_TYPOGRAPHY.className;

  return (
    <Link
      to={`/stock/${encodeURIComponent(member.ticker)}`}
      className="group/row flex items-center gap-3 py-2.5 first:pt-0 last:pb-0 -mx-1 px-1 rounded
                 transition-colors hover:bg-muted/40"
    >
      {/* Stock identity — canonical CODE + NAME (same colour, same size) */}
      <StockIdentity
        ticker={member.ticker}
        name={member.name}
        size="sm"
        codeClassName="group-hover/row:text-accent-info transition-colors"
        className="flex-1 gap-2 leading-tight"
      />

      {/* Sparkline slot — muted thin trajectory; skeleton when no series */}
      <div className="shrink-0 w-[52px] h-[22px] flex items-center">
        {hasSeries ? (
          <SimpleSparkline
            data={member.series}
            isPositive={(member.change_percent ?? 0) >= 0}
            color={hasChange ? trend.lineColor : undefined}
            strokeWidth={1.2}
            fill={false}
            width={52}
            height={22}
            className="opacity-60"
          />
        ) : (
          <span className="w-full h-[10px] animate-pulse bg-muted rounded" />
        )}
      </div>

      {/* Change % slot — skeleton when null */}
      <div className="shrink-0 w-[4.25rem] flex justify-end">
        <ChangePct
          value={member.change_percent}
          sizeClass={type.memberMetric}
          skeleton
        />
      </div>
    </Link>
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
  const type = TOPICS_TYPOGRAPHY.className;

  const typeLabel =
    sector.exposure_type === 'industry' ? '產業'
    : sector.exposure_type === 'theme' ? '題材'
    : '總經';

  return (
    <div
      className="bg-card border border-border dark:border-white/[0.08] rounded-xl overflow-hidden transition-all duration-200
                 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.18)]
                 hover:border-border/80 dark:hover:border-white/[0.14]
                 hover:shadow-[0_4px_16px_-6px_rgba(0,0,0,0.10)] dark:hover:shadow-[0_4px_20px_-6px_rgba(0,0,0,0.35)]"
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
              iconId={sector.icon_id}
              color={sector.color_hex}
              size={13}
              variant="chip"
            />
            <span className={`${type.micro} font-medium text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded leading-none shrink-0`}>
              {typeLabel}
            </span>
          </div>
          <span className={`${type.cardTitle} font-semibold tracking-[-0.01em] group-hover:text-foreground/80 transition-colors leading-snug block`}>
            {sector.display_name}
          </span>
        </div>

        {/* Right: aggregate change + episode count */}
        <div className="shrink-0 flex flex-col items-end gap-1 pt-0.5">
          <ChangePct
            value={sector.avg_change}
            sizeClass={type.cardMetric}
            showArrow
            skeleton={false}
          />
          <span className={`${type.meta} text-muted-foreground font-mono tabular-nums`}>
            {sector.episode_count} 集
          </span>
        </div>
      </Link>

      {/* ── Member rows ─────────────────────────────────────────── */}
      {topMembers.length > 0 && (
        <div className="px-4 py-2.5 divide-y divide-border/20">
          {topMembers.map((m) => (
            <MemberRow key={m.ticker} member={m} />
          ))}
        </div>
      )}

      {/* Bottom accent — soft center-weighted hairline, color-matched to trend */}
      {hasChange && (
        <div
          className="h-px w-full"
          style={{
            background: `linear-gradient(to right, transparent, ${trend.lineColor}, transparent)`,
            opacity: 0.25,
          }}
        />
      )}
    </div>
  );
};
