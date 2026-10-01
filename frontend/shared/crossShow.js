// Wording for the episode page's 其他節目怎麼看 panel, shared by the React component
// (src/components/episode/CrossShowPanel.tsx) and the crawler body
// (functions/_middleware.js) so the two state the same thing in the same words.
// Plain JS for the same reason as sitePages.js; types in crossShow.d.ts.

export const STANCE_ZH = { BULLISH: '看多', BEARISH: '看空', NEUTRAL: '中立' };

// How this episode's stance sits against the other shows' mentions (backend
// routers/mentions.py cross_show_relation). Descriptive: statements compared with
// statements, never with the price.
export const RELATION_ZH = {
  aligned: '與其他節目同向',
  opposite: '與其他節目相反',
  reserved: '比其他節目保留',
  firmer: '比其他節目明確',
  split: '其他節目看法不一',
  alone: '只有這個節目談到',
};

// Rows worth showing: a ticker nobody else mentioned has nothing to compare against.
export const comparableRows = (data) => ((data && data.rows) || []).filter((r) => r.others && r.others.shows > 0);

export const stanceZh = (stance) => STANCE_ZH[stance] || '未表態';

// "2 個節目、3 次提及：3 看多 · 0 中立 · 0 看空"
export const othersLine = (o) => `${o.shows} 個節目、${o.mentions} 次提及：${o.bull} 看多 · ${o.neutral} 中立 · ${o.bear} 看空`;

// The panel's one-sentence lead.
export const crossShowLead = (data) => {
  const rows = comparableRows(data);
  const same = rows.filter((r) => r.relation === 'aligned').length;
  const diff = rows.filter((r) => r.relation === 'opposite').length;
  return `這一集談到的個股裡，有 ${rows.length} 檔在發布前 ${data.window_days} 天內也被其他節目談到`
    + `（同期共 ${data.shows_in_window} 個節目）：${same} 檔與其他節目同向、${diff} 檔相反。`;
};
