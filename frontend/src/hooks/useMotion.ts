import { useEffect, useRef, useState } from 'react';

const reducedMotion = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * false on the mounting paint, true two frames later — drive a CSS transition from the
 * "empty" state to the real one (bars growing in, opacity fading in). Mount-based on
 * purpose: give the animated block a React `key` derived from its data so it remounts
 * (and grows in again) when the data arrives or changes. Always true under
 * prefers-reduced-motion.
 */
export function useGrowIn(): boolean {
  const [grown, setGrown] = useState(reducedMotion);
  useEffect(() => {
    if (grown) return;
    // Two frames: the first lets the empty state paint, the second starts the transition.
    let inner = 0;
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setGrown(true)); });
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
  }, [grown]);
  return grown;
}

/** Eased count from 0 (or the previous value) to `value`; instant under reduced motion. */
export function useCountUp(value: number, durationMs = 900): number {
  const [shown, setShown] = useState(() => (reducedMotion() ? value : 0));
  const fromRef = useRef(shown);
  useEffect(() => {
    if (reducedMotion() || !Number.isFinite(value)) { setShown(value); return; }
    const from = fromRef.current;
    const start = performance.now();
    let id = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = from + (value - from) * eased;
      setShown(t < 1 ? v : value);
      if (t < 1) id = requestAnimationFrame(step);
      else fromRef.current = value;
    };
    id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [value, durationMs]);
  return shown;
}
