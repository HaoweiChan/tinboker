// Wording for the episode page's 其他節目怎麼看 panel, shared by the React component
// (src/components/episode/CrossShowPanel.tsx) and the crawler body
// (functions/_middleware.js) so the two state the same thing in the same words.
// Plain JS for the same reason as sitePages.js; types in crossShow.d.ts.

export const STANCE_ZH = { BULLISH: '看多', BEARISH: '看空', NEUTRAL: '中立' };

export const stanceZh = (stance) => STANCE_ZH[stance] || '未表態';

// The only relation worth calling out: the episode took a side and the other shows
// lean the other way. A neutral on either side is not a disagreement.
export const isOpposite = (row) => row.relation === 'opposite';

// Rows worth showing: a ticker nobody else mentioned has nothing to compare against.
// Opposites first; the backend's order (most-discussed elsewhere first) otherwise.
export const comparableRows = (data) => ((data && data.rows) || [])
  .filter((r) => r.others && r.others.shows > 0)
  .sort((a, b) => isOpposite(b) - isOpposite(a));

// Which way the other shows lean, read back from the backend's relation
// (routers/mentions.py cross_show_relation) so its threshold lives in one place.
// null: they have no lean.
export const othersLean = (row) => ({
  aligned: row.stance,
  opposite: row.stance === 'BULLISH' ? 'BEARISH' : 'BULLISH',
  firmer: 'NEUTRAL',
  reserved: row.others.bull >= row.others.bear ? 'BULLISH' : 'BEARISH',
}[row.relation]) || null;

// "20 看多 · 10 中立 · 0 看空" — raw mention counts behind the lean.
export const othersCounts = (o) => `${o.bull} 看多 · ${o.neutral} 中立 · ${o.bear} 看空`;

// The panel's one-sentence lead, from the public route's counts.
export const crossShowLead = (data) => `這一集談到的個股，有 ${data.compared} 檔在發布前 ${data.window_days} 天內也被其他節目談到，`
  + (data.opposite ? `其中 ${data.opposite} 檔看法相反。` : '沒有看法相反的。');

// What a non-member (and the crawler) gets in place of the rows.
export const CROSS_SHOW_LOCKED = '每一檔本集與其他節目的看法對照是會員內容。';
