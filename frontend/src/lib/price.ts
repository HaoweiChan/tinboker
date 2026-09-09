import { inferStockMarket } from '@/utils/stockDisplay';

/**
 * How many decimals a quote in this market actually carries — the exchange's tick
 * size, not a display preference.
 *
 * TWSE 營業細則 §62 ticks listed stocks by price band:
 *   < 10 → 0.01 · 10–50 → 0.05 · 50–100 → 0.1 · 100–500 → 0.5 · 500–1000 → 1 · ≥ 1000 → 5
 * so 台積電 at 2,465 genuinely has no cents and a NT$45.55 small cap genuinely has two.
 * (The 1000+ tick narrows from 5 to 1 in 2027-07; that changes the tick, not the
 * decimals, so nothing here moves.)
 *
 * TWSE ETFs are ticked finer than stocks — < 50 → 0.01, ≥ 50 → 0.05 — which is why
 * 0050 prints 109.65 while a stock at that price prints 109.6. ETF codes start with
 * "00" (0050, 0056, 00878B); that shape is the only signal we have without a real
 * instrument-type field.
 *
 * US (Reg NMS Rule 612): $0.01 at or above $1.00, $0.0001 below it.
 * KR quotes are whole won.
 */
export function priceDecimals(price: number, ticker: string): number {
  const p = Math.abs(price);
  const market = inferStockMarket(ticker);
  if (market === 'US') return p >= 1 ? 2 : 4;
  if (market === 'KR') return 0;
  const core = ticker.split('.')[0].toUpperCase().replace(/[A-Z]$/, '');
  if (core.startsWith('00')) return 2;               // ETF
  if (p < 50) return 2;
  if (p < 500) return 1;
  return 0;
}

export function fmtPrice(v: number | null | undefined, ticker: string): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const d = priceDecimals(v, ticker);
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
