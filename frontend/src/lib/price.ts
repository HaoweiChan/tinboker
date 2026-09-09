/**
 * Prices as people read them off a board.
 *
 * At or above 100 the cents carry nothing — 2,470.00 is 2,470, and a NVDA quote of
 * 230.36 is "two-thirty" to anyone who is not placing an order. Below 100 the decimals
 * are the price: a NT$45.55 small cap or a US$12.34 name moves in ticks the integer
 * cannot show. One rule, used by the header, the chart axis and the crosshair legend, so
 * the same number never reads three different ways on one page.
 */
export function fmtPrice(v: number | null | undefined): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const digits = Math.abs(v) >= 100 ? 0 : 2;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
