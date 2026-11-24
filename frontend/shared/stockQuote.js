// Price facts for a stock page, shared by the React page (StockDashboard: <title>,
// description, header) and the crawler body (functions/_middleware.js), so the two say
// the same thing in the same words. Input is GET /api/stocks/{ticker}/quote.
// Plain JS for the same reason as sitePages.js; types in stockQuote.d.ts.
//
// Why it exists: 91% of the site's search impressions (Search Console, 90 days to
// 2026-11-21) were "<code> 股價" queries, and the page answering them stated no price.

const UNIT = { TW: { price: '元', vol: '張', per: 1000 }, US: { price: '美元', vol: '股', per: 1 } };
const unit = (q) => UNIT[q && q.market] || { price: '', vol: '股', per: 1 };

const num2 = (v) => Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const mmdd = (iso) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;

// "彰銀（2801）" — the name the page and its title use.
export const stockDisplayName = (name, ticker) => (name ? `${name}（${ticker}）` : ticker);

const hasValuation = (q) => !!(q && q.valuation && (q.valuation.pe || q.valuation.pb || q.valuation.dividend_yield != null));

// <title> without the site suffix. Names the ratios only when the page shows them.
export const stockTitle = (displayName, q) => (hasValuation(q)
  ? `${displayName}股價、本益比、殖利率 · Podcast 觀點`
  : `${displayName}股價走勢 · Podcast 觀點`);

// "11/23 收盤 25.10 元，跌 0.30（-1.18%），成交量 34,785 張。"
export function closeSentence(q) {
  if (!q || !q.close) return '';
  const u = unit(q);
  let s = `${mmdd(q.date)} 收盤 ${num2(q.close)}${u.price ? ` ${u.price}` : ''}`;
  if (q.change != null && q.change_pct != null) {
    const pct = `${q.change_pct > 0 ? '+' : ''}${q.change_pct.toFixed(2)}%`;
    s += q.change === 0 ? '，平盤' : `，${q.change > 0 ? '漲' : '跌'} ${num2(Math.abs(q.change))}（${pct}）`;
  }
  if (q.volume) s += `，成交量 ${Math.round(q.volume / u.per).toLocaleString('en-US')} ${u.vol}`;
  return `${s}。`;
}

// "近一年最高 26.00、最低 19.00。" When the stored history is shorter than a year (a new
// listing, a split, 00981A whose bars only start 2026-09-18) it says from when instead.
export function rangeSentence(q) {
  if (!q || !q.high_52w) return '';
  const days = (Date.parse(q.date) - Date.parse(q.range_from)) / 86400e3;
  const since = days >= 350 ? '近一年' : `${q.range_from.slice(0, 4)}/${mmdd(q.range_from)} 以來`;
  return `${since}最高 ${num2(q.high_52w)}、最低 ${num2(q.low_52w)}。`;
}

// [['本益比', '14.43'], ['股價淨值比', '1.31'], ['殖利率', '4.18%']] — missing ratios left out.
export function valuationItems(q) {
  const v = q && q.valuation;
  if (!v) return [];
  return [
    v.pe ? ['本益比', num2(v.pe)] : null,
    v.pb ? ['股價淨值比', num2(v.pb)] : null,
    v.dividend_yield != null ? ['殖利率', `${num2(v.dividend_yield)}%`] : null,
  ].filter(Boolean);
}

const SOURCE_ZH = { twse: '證交所', tpex: '櫃買中心' };

// "本益比 14.43、股價淨值比 1.31、殖利率 4.18%（證交所 11/23）。"
export function valuationSentence(q) {
  const items = valuationItems(q);
  if (!items.length) return '';
  const v = q.valuation;
  return `${items.map(([k, val]) => `${k} ${val}`).join('、')}（${SOURCE_ZH[v.source] || '交易所'} ${mmdd(v.date)}）。`;
}

// The description's lead: the price facts a searcher came for, before anything else.
export const quoteLead = (displayName, q) => (q && q.close
  ? `${displayName}${closeSentence(q)}${valuationSentence(q)}`
  : '');
