/** Splits an episode summary into the 關鍵洞察 card's lead and the 摘要 body.
 *
 *  The card is built FROM the summary — its headline is the summary's first
 *  heading and its thesis is the summary's first paragraph — so rendering the
 *  card above an untouched 摘要 printed both verbatim, back to back, on every
 *  episode page (~500px of duplicate text on mobile, plus a duplicate <h2> for
 *  crawlers). Deriving both halves here keeps one owner for "which lines are the
 *  lead", so the card and the body cannot drift apart.
 */

export interface EpisodeInsightFields {
  headline: string;
  thesis?: string;
  highlights: string[];
}

export interface EpisodeLead {
  insight: EpisodeInsightFields;
  /** The summary minus the lines the card consumed — what 摘要 renders. */
  body: string;
}

export function cleanSummaryLine(line: string): string {
  return line
    .replace(/^(?:#{1,6}\s*)+/, '')
    .replace(/\s*\(#time:\s*\d+\)/g, '')
    .replace(/^[-*\s]+/, '')
    // Strip ALL inline markers ([label](#ticker:..|#tag:..|url)) down to their label
    // so the insight reads as plain text, never raw markdown.
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`>~]/g, '')
    .trim();
}

export function episodeLeadFrom(
  summary: string,
  fallbackTitle: string,
  keyInsights?: unknown,
): EpisodeLead | null {
  // Indices into the RAW lines (not a trimmed/filtered view) so the consumed lead
  // can be removed from the markdown the body renders.
  const raw = (summary || '').split('\n');
  const at = (i: number) => raw[i].trim();
  const isHeading = (i: number) => at(i).startsWith('#');
  const headlineIdx = raw.findIndex((_, i) => isHeading(i));
  const firstTextIdx = raw.findIndex((_, i) => at(i) !== '');
  // No summary at all → no card. `fallbackTitle` is a last resort for a summary whose
  // heading cleans down to nothing, never a card whose only content is the page's own
  // <h1> repeated back at the reader.
  if (firstTextIdx < 0) return null;
  const thesisIdx = raw.findIndex((_, i) => at(i) !== '' && !isHeading(i) && at(i).length > 12);

  // No truncation: the insight is the concise essence of the article and is shown
  // in full (no "…"). The headline / thesis / section headings are already short.
  const headline = cleanSummaryLine(
    headlineIdx >= 0 ? at(headlineIdx) : firstTextIdx >= 0 ? at(firstTextIdx) : fallbackTitle,
  );
  const thesis = cleanSummaryLine(thesisIdx >= 0 ? at(thesisIdx) : '');
  const keyHighlights = Array.isArray(keyInsights)
    ? keyInsights.map((line) => cleanSummaryLine(String(line))).filter(Boolean)
    : [];
  const sectionHighlights = raw
    .filter((line) => /^#{2,}/.test(line.trim()))
    .map((line) => cleanSummaryLine(line))
    .filter((line) => line && line !== headline)
    .slice(0, 3);
  const highlights = (keyHighlights.length > 0 ? keyHighlights : sectionHighlights).slice(0, 3);

  if (!headline && !thesis && highlights.length === 0) return null;

  // Drop only what the card actually shows. A summary with no thesis line leaves
  // the body's paragraphs alone, and `## …` section headings always stay in the
  // body — there they are navigation in context, not a repeat of the lead.
  // The headline is only dropped when it was a real heading: when it fell back to
  // the first paragraph, that paragraph is the body's opening sentence and the
  // thesis index already covers it.
  const consumed = new Set<number>();
  if (headlineIdx >= 0 && headline) consumed.add(headlineIdx);
  if (thesisIdx >= 0 && thesis) consumed.add(thesisIdx);
  const body = raw
    .filter((_, i) => !consumed.has(i))
    .join('\n')
    .replace(/^\s*\n+/, '');

  return {
    insight: { headline: headline || fallbackTitle, thesis: thesis || undefined, highlights },
    body,
  };
}
