import { useEffect, useState } from 'react';

/** Tailwind's `md` breakpoint, so JS-sized things agree with the CSS beside them. */
const DESKTOP = '(min-width: 768px)';
/** Tailwind's `xl`. Where the sidebar stops being a hover rail and stays open. */
const WIDE = '(min-width: 1280px)';

/**
 * Tracks a media query, kept in sync with the viewport.
 *
 * For state that must be a VALUE rather than a class — a canvas height, whether a
 * component renders its labels. Reading `window.innerWidth` inline looks equivalent and
 * is not: it is evaluated once during render and never again, so it silently disagrees
 * with the CSS next to it after any resize or orientation change.
 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      && window.matchMedia(query).matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

/** True at `md` and wider. */
export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP);
}

/** True at `xl` and wider — enough room for a permanently open sidebar. */
export function useIsWide(): boolean {
  return useMediaQuery(WIDE);
}
