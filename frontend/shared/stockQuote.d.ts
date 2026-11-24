export interface StockValuation { date: string; pe: number | null; pb: number | null; dividend_yield: number | null; source: string | null }
export interface StockQuote {
  ticker: string; name: string | null; market: string; date: string; close: number;
  prev_close: number | null; change: number | null; change_pct: number | null; volume: number | null;
  high_52w: number; low_52w: number; range_from: string; valuation: StockValuation | null;
}

export function stockDisplayName(name: string | null | undefined, ticker: string): string;
export function stockTitle(displayName: string, q: StockQuote | null | undefined): string;
export function closeSentence(q: StockQuote | null | undefined): string;
export function rangeSentence(q: StockQuote | null | undefined): string;
export function valuationItems(q: StockQuote | null | undefined): [string, string][];
export function valuationSentence(q: StockQuote | null | undefined): string;
export function quoteLead(displayName: string, q: StockQuote | null | undefined): string;
