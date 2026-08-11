/** Turn an episode summary into something that survives outside tinboker.com.
 *
 *  The pipeline writes three in-house markers that only mean something on our own
 *  site (see SummaryMarkdown.tsx, which renders them):
 *    [label](#ticker:SYMBOL)  -> a stock page link
 *    [label](#tag:ID)         -> a topic page link
 *    (#time:MILLISECONDS)     -> a badge that seeks the audio player
 *
 *  Pasted into 方格子 or Substack those degrade to literal `#ticker:2330` junk, and
 *  the timestamp badge has no player to seek. So: rewrite the two link markers to
 *  absolute URLs (which also earns us the backlink), and flatten timestamps to plain
 *  text, since off-site there is nothing to click.
 *
 *  Kept as a string->string transform with no React in it: this is the part with
 *  actual logic, and scripts/validate-syndication.ts exercises it directly. */
import { isRealTimeMarker } from './parseTimestampedSections';
import { normalizeCjkMarkerSpacing } from './summaryParser';

export const SITE_URL = 'https://tinboker.com';

/** `754000` -> `12:34`; hours only appear once there are any. Mirrors the on-site
 *  badge format in SummaryMarkdown.tsx so the two read the same. */
export function formatTimestamp(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

export interface SyndicationOptions {
  /** Override for tests; production always uses the real site. */
  siteUrl?: string;
}

/** Rewrite the in-house markers into plain, portable markdown. */
export function rewriteMarkersForSyndication(
  content: string,
  { siteUrl = SITE_URL }: SyndicationOptions = {},
): string {
  if (!content) return '';
  const base = siteUrl.replace(/\/+$/, '');

  return normalizeCjkMarkerSpacing(
    content
      // `[12:34](#time:754000)` — already-linked timestamps keep their label only.
      .replace(/\[([^\]]*)\]\(#time:(\d+)\)/g, (_m, label: string, ms: string) =>
        isRealTimeMarker(Number(ms)) ? label : '')
      // Bare `(#time:754000)`. Ordinal placeholders (the legacy writer-LLM bug) are
      // dropped rather than rendered as bogus 00:00 — same rule as on-site.
      .replace(/\s*\(#time:(\d+)\)/g, (_m, ms: string) =>
        isRealTimeMarker(Number(ms)) ? ` (${formatTimestamp(Number(ms))})` : '')
      .replace(/\]\(#ticker:([^)]+)\)/g, (_m, symbol: string) =>
        `](${base}/stock/${encodeURIComponent(symbol.trim().toUpperCase())})`)
      .replace(/\]\(#tag:([^)]+)\)/g, (_m, id: string) =>
        `](${base}/topics/${encodeURIComponent(id.trim())})`),
  );
}

/** The attribution line appended to every syndicated copy.
 *
 *  Full text goes out to three sites, so search engines need to be told which one is
 *  the original. Substack and 方格子 both let you set a canonical URL in the post
 *  settings — do that too where the field exists; this visible backlink is the part
 *  that works everywhere and survives a copy-paste. */
export function attributionMarkdown(episodeUrl: string): string {
  return `\n\n---\n\n本文為 [TinBoker](${SITE_URL}) 的 podcast 重點整理，原文與可點擊的逐段時間軸在 [${episodeUrl}](${episodeUrl})。`;
}

export function episodeUrl(episodeId: string, { siteUrl = SITE_URL }: SyndicationOptions = {}): string {
  return `${siteUrl.replace(/\/+$/, '')}/episode/${episodeId}`;
}

/** Markdown ready to paste — markers resolved, attribution appended. */
export function toSyndicationMarkdown(
  content: string,
  episodeId: string,
  options: SyndicationOptions = {},
): string {
  const body = rewriteMarkersForSyndication(content, options);
  if (!body.trim()) return '';
  return body.trimEnd() + attributionMarkdown(episodeUrl(episodeId, options));
}
