import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { SectorIcon } from './SectorIcon';
import type { SectorBoardItem } from '@/services/api/podcasts';

interface SectorHeroCardProps {
  sector: SectorBoardItem;
}

/**
 * Hero card for a top-gaining sector. Features:
 * - Ambient glow whose color + intensity scales with |avg_change|
 * - Full-bleed background sparkline at low opacity for depth
 * - Foreground: name, big change %, arrow icon
 */
export const SectorHeroCard: React.FC<SectorHeroCardProps> = ({ sector }) => {
  const trend = useStockTrendColor(sector.avg_change ?? 0);
  const hasChange = sector.avg_change != null && Number.isFinite(sector.avg_change);
  const isPositive = (sector.avg_change ?? 0) >= 0;
  const Arrow = isPositive ? ArrowUpRight : ArrowDownRight;

  // ponytail: outer glow removed — box-shadow ignores overflow-hidden, so the per-card
  // wash bled across the strip into neighbouring cards. Plain base elevation only.
  const glowStyle = { boxShadow: '0 1px 3px rgba(0,0,0,0.22)' };

  return (
    <Link
      to={`/sector/${encodeURIComponent(sector.exposure_id)}`}
      className="group relative flex flex-col justify-between min-w-[148px] flex-1 bg-card rounded-xl p-4 overflow-hidden
                 border border-border dark:border-white/[0.08] hover:border-border/80 dark:hover:border-white/[0.14] transition-all duration-300"
      style={glowStyle}
    >
      <div className="relative z-10">
        {/* Top row: icon + type badge */}
        <div className="flex items-center gap-1.5 mb-3">
          <SectorIcon
            exposureId={sector.exposure_id}
            iconId={sector.icon_id}
            color={sector.color_hex}
            size={12}
            variant="chip"
          />
          <span className="text-2xs font-medium text-muted-foreground bg-muted/70 px-1.5 py-0.5 rounded leading-none">
            {sector.exposure_type === 'sector' ? '產業' : sector.exposure_type === 'theme' ? '主題' : '總經'}
          </span>
        </div>

        {/* Sector name */}
        <div className="text-sm font-semibold tracking-[-0.01em] mb-3 leading-snug group-hover:text-foreground/90 transition-colors line-clamp-2">
          {sector.display_name}
        </div>

        {/* Big change number + arrow */}
        <div className="flex items-center gap-1">
          {hasChange ? (
            <>
              <span className={`font-mono text-xl font-bold tabular-nums leading-none ${trend.text}`}>
                {sector.avg_change! >= 0 ? '+' : ''}{sector.avg_change!.toFixed(2)}%
              </span>
              <Arrow size={16} className={trend.text} />
            </>
          ) : (
            <span className="font-mono text-xl font-bold tabular-nums leading-none text-muted-foreground">—</span>
          )}
        </div>

        {/* Episode count */}
        <div className="mt-2 text-2xs text-muted-foreground font-mono tabular-nums">
          {sector.episode_count} 集
        </div>
      </div>
    </Link>
  );
};
