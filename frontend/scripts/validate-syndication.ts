/** Checks the marker rewriting in src/utils/syndicationMarkdown.ts.
 *
 *  That transform is the only place with real logic in the syndication path — get a
 *  regex wrong and we quietly paste `#ticker:2330` into a public post. Run with:
 *    npm run validate:syndication
 */
import assert from 'node:assert/strict';
import {
  rewriteMarkersForSyndication,
  toSyndicationMarkdown,
  formatTimestamp,
} from '../src/utils/syndicationMarkdown';

const SITE = 'https://tinboker.com';
const rw = (md: string) => rewriteMarkersForSyndication(md, { siteUrl: SITE });

// ── ticker + tag markers become absolute links ───────────────────────────────
// Note the missing spaces around the links: normalizeCjkMarkerSpacing strips the
// pipeline's ASCII padding when both sides are CJK, exactly as it does on-site.
assert.equal(
  rw('看好 [台積電](#ticker:2330) 的表現'),
  `看好[台積電](${SITE}/stock/2330)的表現`,
);
assert.equal(
  rw('[輝達](#ticker:nvda) 財報'),
  `[輝達](${SITE}/stock/NVDA)財報`,
  'ticker symbols are uppercased, matching the on-site renderer',
);
assert.equal(
  rw('屬於 [半導體](#tag:semiconductor) 類股'),
  `屬於[半導體](${SITE}/topics/semiconductor)類股`,
);
assert.equal(
  rw('[能源](#tag:能源 轉型)'),
  `[能源](${SITE}/topics/${encodeURIComponent('能源 轉型')})`,
  'ids are percent-encoded so a space cannot break the link',
);

// ── timestamps flatten to text: there is no player off-site ──────────────────
assert.equal(rw('這段講得好 (#time:754000)'), '這段講得好 (12:34)');
assert.equal(rw('開場 (#time:0)'), '開場 (0:00)');
assert.equal(
  rw('已連結 [12:34](#time:754000) 的段落'),
  '已連結 12:34 的段落',
  'an already-linked timestamp keeps its label, loses the dead href',
);
assert.equal(
  rw('假標記 (#time:3)'),
  '假標記',
  'ordinal placeholders (<1000ms, the legacy writer bug) are dropped, not rendered as 0:00',
);
assert.equal(
  rw('假連結 [1](#time:3) 收掉'),
  '假連結收掉',
  'the same rule applies to placeholder markers that arrived as links',
);

// ── no in-house marker may survive into a public post ────────────────────────
const sample = [
  '# 本集重點',
  '',
  '[台積電](#ticker:2330) 在 [半導體](#tag:semiconductor) 的地位 (#time:754000)。',
  '',
  '- 重點一 [聯發科](#ticker:2454)',
].join('\n');
const out = toSyndicationMarkdown(sample, 'ep677', { siteUrl: SITE });
for (const marker of ['#ticker:', '#tag:', '#time:']) {
  assert.ok(!out.includes(marker), `${marker} leaked into the syndicated copy`);
}
assert.ok(out.includes(`${SITE}/episode/ep677`), 'attribution backlink is present');
assert.ok(out.includes('# 本集重點'), 'headings and body text are left alone');

// ── formatting + empty input ─────────────────────────────────────────────────
assert.equal(formatTimestamp(0), '0:00');
assert.equal(formatTimestamp(59_000), '0:59');
assert.equal(formatTimestamp(3_600_000), '1:00:00');
assert.equal(formatTimestamp(3_754_000), '1:02:34');
assert.equal(rw(''), '');
assert.equal(
  toSyndicationMarkdown('   ', 'ep1', { siteUrl: SITE }),
  '',
  'a blank summary yields nothing to paste — not a lone attribution line',
);

console.log('✓ syndication marker rewriting OK');
