import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
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

  // Soft ambient glow: a large-radius, low-opacity (~10–16%) wash so the trend color
  // bleeds out as mist rather than reading as a hard neon outline. Paired with a faint
  // base elevation shadow so the card still lifts off the page when change is flat.
  const magnitude = Math.min(Math.abs(sector.avg_change ?? 0), 10);
  const glowBlur = Math.round(24 + (magnitude / 10) * 12); // 24–36px radius
  const glowAlpha = 0.1 + (magnitude / 10) * 0.06;          // 0.10–0.16 opacity
  const alphaHex = Math.round(glowAlpha * 255).toString(16).padStart(2, '0');
  const baseShadow = '0 1px 3px rgba(0,0,0,0.22)';
  const glowStyle = {
    boxShadow: hasChange
      ? `${baseShadow}, 0 0 ${glowBlur}px 0 ${trend.lineColor}${alphaHex}`
      : baseShadow,
  };

  const series = sector.series && sector.series.length > 1 ? sector.series : undefined;

  return (
    <Link
      to={`/sector/${encodeURIComponent(sector.exposure_id)}`}
      className="group relative flex flex-col justify-between min-w-[148px] flex-1 bg-card rounded-xl p-4 overflow-hidden
                 border border-white/[0.08] hover:border-white/[0.14] transition-all duration-300"
      style={glowStyle}
    >
      {/* Full-bleed background sparkline for depth */}
      {series && (
        <div className="absolute inset-0 pointer-events-none opacity-[0.1]">
          <SimpleSparkline
            data={series}
            isPositive={isPositive}
            color={trend.lineColor}
            smooth
            strokeWidth={1.5}
            width={200}
            height={80}
            className="w-full h-full"
          />
        </div>
      )}

      {/* Content sits above the sparkline */}
      <div className="relative z-10">
        {/* Top row: icon + type badge */}
        <div className="flex items-center gap-1.5 mb-3">
          <SectorIcon
            exposureId={sector.exposure_id}
            size={12}
            className="text-muted-foreground shrink-0"
          />
          <span className="text-[10px] font-medium text-muted-foreground bg-muted/70 px-1.5 py-0.5 rounded leading-none">
            {sector.exposure_type === 'sector' ? '產業' : sector.exposure_type === 'theme' ? '主題' : '總經'}
          </span>
        </div>

        {/* Sector name */}
        <div className="text-[13px] font-semibold tracking-[-0.01em] mb-3 leading-snug group-hover:text-foreground/90 transition-colors line-clamp-2">
          {sector.display_name}
        </div>

        {/* Big change number + arrow */}
        <div className="flex items-center gap-1">
          {hasChange ? (
            <>
              <span className={`font-mono text-[20px] font-bold tabular-nums leading-none ${trend.text}`}>
                {sector.avg_change! >= 0 ? '+' : ''}{sector.avg_change!.toFixed(2)}%
              </span>
              <Arrow size={16} className={trend.text} />
            </>
          ) : (
            <span className="font-mono text-[20px] font-bold tabular-nums leading-none text-muted-foreground">—</span>
          )}
        </div>

        {/* Episode count */}
        <div className="mt-2 text-[10px] text-muted-foreground font-mono tabular-nums">
          {sector.episode_count} 集
        </div>
      </div>
    </Link>
  );
};
