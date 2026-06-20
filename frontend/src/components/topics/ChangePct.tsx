import React from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';

interface ChangePctProps {
  value: number | null;
  /** text size class, e.g. 'text-[11px]' */
  sizeClass?: string;
  /** extra className on the wrapper span */
  className?: string;
  showArrow?: boolean;
  /** If true renders a skeleton placeholder when value is null */
  skeleton?: boolean;
}

/**
 * Renders a change-percent value (e.g. "+2.34%") with the correct
 * TW/US color via useStockTrendColor.  Must be rendered as its own
 * component (not inside a map callback) so the hook runs at top level.
 */
export const ChangePct: React.FC<ChangePctProps> = ({
  value,
  sizeClass = 'text-[11px]',
  className = '',
  showArrow = false,
  skeleton = false,
}) => {
  const trend = useStockTrendColor(value ?? 0);
  const hasValue = value != null && Number.isFinite(value);

  if (!hasValue) {
    if (skeleton) {
      return (
        <span className="inline-block h-3 w-10 animate-pulse bg-muted rounded" />
      );
    }
    return <Minus size={12} className="text-muted-foreground shrink-0" />;
  }

  const Arrow = value! >= 0 ? ArrowUpRight : ArrowDownRight;
  const sign = value! >= 0 ? '+' : '';

  return (
    <span className={`flex items-center gap-0.5 font-mono tabular-nums font-medium shrink-0 ${trend.text} ${sizeClass} ${className}`}>
      {showArrow && <Arrow size={12} />}
      {sign}{value!.toFixed(2)}%
    </span>
  );
};
