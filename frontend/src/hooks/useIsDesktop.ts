import { useEffect, useState } from 'react';

/** Tailwind's `md` breakpoint, so JS-sized things agree with the CSS beside them. */
const DESKTOP = '(min-width: 768px)';

/**
 * True at `md` and wider, kept in sync with the viewport.
 *
 * For values that must be a NUMBER rather than a class — a canvas height, a series count.
 * Reading `window.innerWidth` inline looks equivalent and is not: it is evaluated once
 * during render and never again, so it silently disagrees with the CSS next to it after
 * any resize or orientation change.
 */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      && window.matchMedia(DESKTOP).matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(DESKTOP);
    const onChange = () => setIsDesktop(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isDesktop;
}
