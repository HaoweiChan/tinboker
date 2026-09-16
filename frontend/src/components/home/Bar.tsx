import { useGrowIn } from '@/hooks/useMotion';

/** Which signal the bar carries. The hue IS the meaning — amber for topic attention,
 *  steel blue for how much a ticker is discussed, cyan for what is accelerating (the
 *  same cyan as the 升溫 / NEW badges). Never colour per row: that would collide with
 *  the green/red the page already spends on gains and losses. */
export type BarTone = 'topic' | 'ticker' | 'momentum';

/** One attention bar: a groove plus a left-dark → right-bright fill that grows on
 *  mount. A flat single-colour fill read as a stock progress component. */
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
          boxShadow: `0 0 12px -2px ${to}`,
          transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)',
          transitionDelay: `${delayMs}ms`,
        }}
      />
    </span>
  );
};
