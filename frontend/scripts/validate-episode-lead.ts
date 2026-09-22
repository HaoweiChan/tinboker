// Pins the 關鍵洞察 / 摘要 split. The card is derived FROM the summary, so without this
// split every episode page rendered the headline and the opening paragraph twice, back to
// back — and there is no UI that makes that obviously wrong, it just reads as padding.
// The risk in the other direction is worse: strip too much and the body loses a section
// heading or its first sentence, silently, on 300+ public pages.
//
//   npm run validate:episode-lead
//
import { episodeLeadFrom } from '../src/lib/episodeLead';

let failures = 0;
function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  const ok = a === e;
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
  if (!ok) console.log(`      expected ${e}\n      actual   ${a}`);
}

// The real shape the pipeline emits: one `#` headline, one thesis paragraph, then `##`
// sections carrying (#time: N) markers.
const REAL = [
  '# 中秋連假前台股驚驚漲創高，AI沙皇與川習會前資金輪動下的操作策略',
  '',
  '台股在中秋連假前展現強勁走勢，還原息值後盤中一度創下歷史新高，但量能萎縮與強勢族群輪動快速。',
  '',
  '## 驚驚漲！還原息值創高背後的連假觀望與解套賣壓 (#time: 31)',
  '',
  '今日台股加權指數盤中大漲超過500點，最高來到47,750點附近。',
  '',
  '## 結論',
  '',
  '留意半導體封測、設備等長線穩健族群。',
].join('\n');

const real = episodeLeadFrom(REAL, 'EP1188', ['台股還原息值已創歷史新高', '穎崴等探針卡股無預警跌停']);

check('headline is the summary heading, markers stripped',
  real?.insight.headline, '中秋連假前台股驚驚漲創高，AI沙皇與川習會前資金輪動下的操作策略');
check('thesis is the opening paragraph',
  real?.insight.thesis, '台股在中秋連假前展現強勁走勢，還原息值後盤中一度創下歷史新高，但量能萎縮與強勢族群輪動快速。');
check('key_insights win over section headings for highlights',
  real?.insight.highlights, ['台股還原息值已創歷史新高', '穎崴等探針卡股無預警跌停']);

// The whole point: neither of those two lines may survive into the body...
check('body drops the headline', real?.body.includes('AI沙皇與川習會前資金輪動下的操作策略'), false);
check('body drops the thesis', real?.body.includes('還原息值後盤中一度創下歷史新高'), false);
// ...and everything else must survive it, markers intact.
check('body keeps section headings', real?.body.includes('## 驚驚漲！還原息值創高背後的連假觀望與解套賣壓 (#time: 31)'), true);
check('body keeps section prose', real?.body.includes('今日台股加權指數盤中大漲超過500點'), true);
check('body keeps the closing section', real?.body.includes('## 結論'), true);
check('body keeps the closing prose', real?.body.includes('留意半導體封測、設備等長線穩健族群。'), true);
check('body does not open with blank lines', real?.body.startsWith('##'), true);

// --- degenerate summaries: strip nothing we cannot account for ------------------
const noHeading = episodeLeadFrom('這一集談的是記憶體產業的兩極化現象與後續觀察重點。', 'EP2');
check('no heading: headline falls back to the first paragraph',
  noHeading?.insight.headline, '這一集談的是記憶體產業的兩極化現象與後續觀察重點。');
check('no heading: that paragraph is the thesis, so the body empties rather than repeat it',
  noHeading?.body.trim(), '');

const headingOnly = episodeLeadFrom('# 只有標題', 'EP3');
check('heading only: no thesis invented', headingOnly?.insight.thesis, undefined);
check('heading only: body empties', headingOnly?.body.trim(), '');

const shortLead = episodeLeadFrom(['# 標題', '', '太短', '', '## 一節', '', '內文在這裡。'].join('\n'), 'EP4');
check('a <=12 char line is not treated as the thesis', shortLead?.insight.thesis, undefined);
check('...so it stays in the body', shortLead?.body.includes('太短'), true);
check('...and the section survives', shortLead?.body.includes('## 一節'), true);

check('empty summary yields no lead at all', episodeLeadFrom('', 'EP5'), null);
check('whitespace-only summary yields no lead', episodeLeadFrom('\n\n   \n', 'EP6'), null);

// A repeated paragraph in the source is the pipeline's business, not ours: only the
// FIRST occurrence is the lead, so a genuine later repeat is left visible.
const dupe = episodeLeadFrom(['# T', '', '一樣的句子在這裡出現兩次喔。', '', '## S', '', '一樣的句子在這裡出現兩次喔。'].join('\n'), 'EP7');
check('only the first occurrence of the thesis is consumed',
  (dupe?.body.match(/一樣的句子在這裡出現兩次喔。/g) || []).length, 1);

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
