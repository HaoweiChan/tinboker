import type React from 'react';

/** True when a click landed on the card's own body, so the card may expand or collapse.
 *  False for its controls (links, buttons, the share modal — a portal still bubbles React
 *  events to the card) and for a click that ends a text selection. */
export function isCardBodyTap(e: React.MouseEvent<HTMLElement>): boolean {
  const target = e.target as HTMLElement;
  if (!e.currentTarget.contains(target)) return false;
  if (window.getSelection()?.toString()) return false;
  return !target.closest('a, button, input, [role="button"]');
}
