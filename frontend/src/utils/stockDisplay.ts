/**
 * Stock label policy used across the UI.
 *
 * For TW stocks (4-digit numeric tickers) we surface the Chinese company name
 * as the primary label and the ticker as the secondary one — that's how
 * Taiwanese readers actually identify these companies. US stocks keep the
 * usual `NVDA` + `Nvidia Corp` layout.
 *
 * The `market` argument is optional; when omitted we infer it from the ticker.
 */

export type StockMarket = 'TW' | 'US';

export function inferStockMarket(ticker: string): StockMarket {
  if (!ticker) return 'US';
  const clean = ticker.split('.')[0];
  return /^\d+$/.test(clean) ? 'TW' : 'US';
}

interface GetStockLabelInput {
  ticker: string;
  name?: string | null;
  market?: string | null;
}

export interface StockLabel {
  primary: string;
  secondary?: string;
}

export function getStockLabel({ ticker, name, market }: GetStockLabelInput): StockLabel {
  const resolvedMarket = (market as StockMarket | undefined) || inferStockMarket(ticker);
  const trimmedName = name?.trim();
  if (resolvedMarket === 'TW' && trimmedName) {
    return { primary: trimmedName, secondary: ticker };
  }
  return { primary: ticker, secondary: trimmedName || undefined };
}
