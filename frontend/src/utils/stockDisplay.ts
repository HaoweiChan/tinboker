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

export type StockMarket = 'TW' | 'US' | 'KR';

export function inferStockMarket(ticker: string): StockMarket {
  if (!ticker) return 'US';
  const clean = ticker.split('.')[0].toUpperCase();
  // Strip a single trailing class letter from TW ETFs (00878B, 00632R) so they
  // aren't mistaken for US alpha tickers.
  const core = /^\d+[A-Z]$/.test(clean) ? clean.slice(0, -1) : clean;
  if (!/^\d+$/.test(core)) return 'US';
  // 6-digit numeric codes are Korean (005930 Samsung, 000660 SK Hynix); 3-5 digit
  // codes are Taiwan (2330, 0050 ETFs). HK 4-digit codes (0700) can't be told
  // apart from TW by shape, so they stay TW — that needs a real market field.
  // (6-digit mainland A-shares would also fall here; none appear in the feed today.)
  return core.length === 6 ? 'KR' : 'TW';
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
  // Non-US markets (TW, KR) surface the localized company name as primary.
  if (resolvedMarket !== 'US' && trimmedName) {
    return { primary: trimmedName, secondary: ticker };
  }
  return { primary: ticker, secondary: trimmedName || undefined };
}
