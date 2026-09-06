import React from 'react';
import { useCountUp } from '@/hooks/useMotion';

interface CountUpProps {
  value: number;
  /** Decimal places to show (default 0). */
  decimals?: number;
  className?: string;
  /** Format the eased number for display; default is toLocaleString with `decimals`. */
  format?: (n: number) => string;
}

/** A number that counts up to `value` on mount / change. Keeps `tabular-nums` layout. */
export const CountUp: React.FC<CountUpProps> = ({ value, decimals = 0, className, format }) => {
  const n = useCountUp(value);
  const text = format ? format(n) : n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return <span className={className}>{text}</span>;
};
