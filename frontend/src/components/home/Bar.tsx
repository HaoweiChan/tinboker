import { useGrowIn } from '@/hooks/useMotion';

/** What the bar's colour says — its STATE, not which panel it lives in. 'default' is
 *  every ordinary statistic, 'strong' the leader of a list (one step brighter), 'hot'
 *  something actually heating up, in the cyan of the 升溫 / NEW badges. Giving each
 *  panel its own hue made the page look like three dashboards pasted together; per-row
 *  colours would collide with the green/red spent on gains and losses. */
export type BarTone = 'default' | 'strong' | 'hot';

/** One attention bar: a groove plus a fill that grows on mount. The gradient and glow
 *  are deliberately near-invisible — a flat fill reads as a stock progress component,
 *  a strong one as glowing plastic. */
export const Bar: React.FC<{ value: number; max: number; tone: BarTone; delayMs?: number }> = ({
  value,
  max,
  tone,
  delayMs = 0,
}) => {
  const grown = useGrowIn();
  const from = `hsl(var(--bar-${tone}-from))`;
  const to = `hsl(var(--bar-${tone}-to))`;
  return (
    <span className="h-4 sm:h-[16px] rounded-[3px] overflow-hidden" style={{ backgroundColor: 'hsl(var(--bar-track))' }}>
      <span
        className="block h-full rounded-[3px]"
        style={{
          width: grown ? `${(value / Math.max(1, max)) * 100}%` : '0%',
          background: `linear-gradient(90deg, ${from} 0%, ${to} 100%)`,
          boxShadow: `0 0 6px hsl(var(--bar-${tone}-to) / 0.10)`,
          transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)',
          transitionDelay: `${delayMs}ms`,
        }}
      />
    </span>
  );
};
