import { useGrowIn } from '@/hooks/useMotion';

/** Which number the bar carries. One cool family, one hue each, so the panels separate
 *  without reading as three different products: 'topic' blue-grey for topic attention,
 *  'ticker' a greyer violet-blue for how much a ticker is discussed, 'momentum' teal
 *  for what is accelerating. Never per-row colours: they would collide with the
 *  green/red the page spends on gains and losses. */
export type BarTone = 'topic' | 'ticker' | 'momentum';

/** One attention bar: a groove plus a fill that grows on mount. Gradients and glow are
 *  deliberately near-invisible — a flat fill reads as a stock progress component, a
 *  strong one as glowing plastic.
 *
 *  `rising` fades the last fifth into the 升溫 cyan instead of recolouring the whole
 *  bar: a fully cyan row outshouted the ranking it belongs to. */
export const Bar: React.FC<{
  value: number;
  max: number;
  tone: BarTone;
  rising?: boolean;
  delayMs?: number;
}> = ({ value, max, tone, rising = false, delayMs = 0 }) => {
  const grown = useGrowIn();
  const from = `hsl(var(--bar-${tone}-from))`;
  const to = `hsl(var(--bar-${tone}-to))`;
  const signal = 'hsl(var(--bar-signal))';
  return (
    <span className="h-4 sm:h-[16px] rounded-[3px] overflow-hidden" style={{ backgroundColor: 'hsl(var(--bar-track))' }}>
      <span
        className="block h-full rounded-[3px]"
        style={{
          width: grown ? `${(value / Math.max(1, max)) * 100}%` : '0%',
          background: rising
            ? `linear-gradient(90deg, ${from} 0%, ${to} 78%, ${signal} 100%)`
            : `linear-gradient(90deg, ${from} 0%, ${to} 100%)`,
          boxShadow: `0 0 6px hsl(var(--bar-${tone}-to) / 0.10)`,
          transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)',
          transitionDelay: `${delayMs}ms`,
        }}
      />
    </span>
  );
};
