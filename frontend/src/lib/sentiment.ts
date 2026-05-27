// Centralized sentiment → Chinese label + chip-class mapping, plus aggregation helpers.
// Sentiment colors are SEMANTIC (always green = bull / red = bear) and intentionally
// independent of the TW/US price-change color flip handled by `useStockTrendColor`.

export type Sentiment = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null | undefined;

/** Normalize whatever the backend / mocks send into the canonical vocabulary. */
export function normalizeSentiment(raw: unknown): Exclude<Sentiment, null | undefined> | null {
  if (typeof raw !== 'string') return null;
  const s = raw.trim().toUpperCase();
  if (s === 'BULLISH' || s === 'BULL' || s === 'POSITIVE' || s === 'STRONG_BULLISH') return 'BULLISH';
  if (s === 'BEARISH' || s === 'BEAR' || s === 'NEGATIVE' || s === 'STRONG_BEARISH') return 'BEARISH';
  if (s === 'NEUTRAL' || s === 'NEUT' || s === 'MIXED') return 'NEUTRAL';
  return null;
}

export interface SentimentDisplay {
  label: string; // 看多 / 看空 / 中性
  short: string; // 多 / 空 / 中
  chipClass: string; // tailwind component classes for the chip
  toneClass: string; // text color class only
}

export function getSentimentDisplay(sentiment: Sentiment): SentimentDisplay | null {
  const s = normalizeSentiment(sentiment);
  if (!s) return null;
  switch (s) {
    case 'BULLISH':
      return { label: '看多', short: '多', chipClass: 'sentiment-chip sentiment-chip-bull', toneClass: 'text-sentiment-bull' };
    case 'BEARISH':
      return { label: '看空', short: '空', chipClass: 'sentiment-chip sentiment-chip-bear', toneClass: 'text-sentiment-bear' };
    case 'NEUTRAL':
      return { label: '中性', short: '中', chipClass: 'sentiment-chip sentiment-chip-neutral', toneClass: 'text-sentiment-neutral' };
  }
}

export interface SentimentBreakdown {
  total: number;
  bull: number;
  bear: number;
  neutral: number;
  avgScore: number | null;
}

/**
 * Aggregate sentiment across an array of recommendations for a single ticker / episode / tag.
 * Returns RAW COUNTS — never collapse this into a fake percentage; show "4 多 / 1 空" not "80% bullish".
 */
export function aggregateSentiment(
  recs: ReadonlyArray<{ sentiment?: Sentiment | string; sentiment_label?: string; sentiment_score?: string | number | null }>,
): SentimentBreakdown {
  const breakdown: SentimentBreakdown = { total: recs.length, bull: 0, bear: 0, neutral: 0, avgScore: null };
  let scoreSum = 0;
  let scoreCount = 0;
  for (const r of recs) {
    const s = normalizeSentiment(r.sentiment_label ?? r.sentiment);
    if (s === 'BULLISH') breakdown.bull++;
    else if (s === 'BEARISH') breakdown.bear++;
    else if (s === 'NEUTRAL') breakdown.neutral++;

    if (r.sentiment_score != null) {
      const n = typeof r.sentiment_score === 'string' ? parseFloat(r.sentiment_score) : r.sentiment_score;
      if (!Number.isNaN(n)) {
        scoreSum += n;
        scoreCount++;
      }
    }
  }
  if (scoreCount > 0) breakdown.avgScore = scoreSum / scoreCount;
  return breakdown;
}

/** The dominant sentiment of a breakdown, for a single "整體情緒" chip. Ties → NEUTRAL. */
export function dominantSentiment(b: SentimentBreakdown): Exclude<Sentiment, null | undefined> {
  if (b.bull > b.bear && b.bull >= b.neutral) return 'BULLISH';
  if (b.bear > b.bull && b.bear >= b.neutral) return 'BEARISH';
  return 'NEUTRAL';
}
