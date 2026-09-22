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
 *  `rising` tips the last few pixels with the 升溫 cyan instead of recolouring the bar
 *  (a fully cyan row outshouted its own ranking) or fading a fifth of it (that read as
 *  loud as the momentum panel, blurring what cyan means). */
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
    // Capped, not full-bleed: in the full-width 本週市場 panel the track stretched to
    // ~950px on a desktop, so a row reading "12 集" spent most of the widest element on
    // the page being an empty groove. 440px still separates every value in these panels
    // (they top out in the low hundreds) while leaving the row legible as a row.
    <span className="block w-full max-w-[440px] h-4 sm:h-[16px] rounded-[3px] overflow-hidden" style={{ backgroundColor: 'hsl(var(--bar-track))' }}>
      <span
        className="block h-full rounded-[3px]"
        style={{
          width: grown ? `${(value / Math.max(1, max)) * 100}%` : '0%',
          background: rising
            ? `linear-gradient(90deg, ${from} 0%, ${to} calc(100% - 9px), ${signal} calc(100% - 1px))`
            : `linear-gradient(90deg, ${from} 0%, ${to} 100%)`,
          boxShadow: `0 0 6px hsl(var(--bar-${tone}-to) / 0.10)`,
          transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)',
          transitionDelay: `${delayMs}ms`,
        }}
      />
    </span>
  );
};
