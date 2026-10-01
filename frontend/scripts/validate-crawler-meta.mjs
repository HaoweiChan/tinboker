// Guards functions/_middleware.js — the crawler-meta edge function.
//
// Three things break silently here and only show up months later as pages missing from
// Google: (a) a content route drifts out of the router and starts serving index.html's
// generic title to every crawler, (b) the tag-slug normalizer drifts from the client's
// copy in src/hooks/useTagLabels.ts, so /topics/:tag resolves a different label than the
// page renders, (c) a route stops rendering a crawler-visible body or its JSON-LD, and
// crawlers are back to the empty SPA shell. All three are asserted below.
//
// Run: npm run validate:seo

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const mw = await import(resolve(here, '../functions/_middleware.js'));
const {
  metaFor, isCandidate, normalizeTagSlug, tagLabelFallback, TAG_ROUTE, tagNoindex, MIN_TAG_EPISODES, sectorNoindex,
  renderPage, mdToHtml, chapters, tally, normSentiment, stockNoindex, MIN_STOCK_INSIGHTS,
  whoTalks, monthlyMentions, latestLevel, flowSums,
} = mw;

const ORIGIN = 'https://tinboker.com';
const API = 'https://api.tinboker.com';

// --- 1. tag slug normalization matches the client -------------------------------
// Compare against the alias table literal in the TS hook rather than a hand-copied
// list, so adding an alias on one side and not the other fails here.
const hook = readFileSync(resolve(here, '../src/hooks/useTagLabels.ts'), 'utf8');
const aliasBlock = hook.match(/const aliases: Record<string, string> = \{([\s\S]*?)\};/);
assert.ok(aliasBlock, 'could not find the aliases table in useTagLabels.ts');
const clientAliases = [...aliasBlock[1].matchAll(/(\w+):\s*'([^']+)'/g)];
assert.ok(clientAliases.length > 0, 'aliases table parsed as empty');
for (const [, from, to] of clientAliases) {
  assert.equal(normalizeTagSlug(from), normalizeTagSlug(to),
    `alias ${from} → ${to} not mirrored in _middleware.js`);
}
assert.equal(normalizeTagSlug('SupplyChain'), 'supplychain');
assert.equal(normalizeTagSlug('#supply_chain'), 'supplychain');
assert.equal(normalizeTagSlug('ElectricVehicles'), 'ev');
assert.equal(tagLabelFallback('#supply_chain'), 'supply chain');

// --- 2. body helpers ------------------------------------------------------------
const SUMMARY = '# 聯準會鴿聲振奮台股\n\n開場段落，提到 [CPI](#tag:CPI) 與台積電。\n\n## 升息機率驟降 (#time:37659)\n\n第一章內容。\n\n## 大盤技術面 (#time:128263)\n\n- 第一點\n- 第二點';
assert.deepEqual(chapters(SUMMARY), [
  { title: '升息機率驟降', sec: 37 },
  { title: '大盤技術面', sec: 128 },
]);
const html = mdToHtml(SUMMARY);
assert.ok(html.startsWith('<h2>聯準會鴿聲振奮台股</h2>'), 'summary H1 shifts to H2');
assert.ok(html.includes('<h3>升息機率驟降</h3>'), 'timestamp anchor stripped from heading');
assert.ok(html.includes('提到 CPI 與台積電'), 'tag link unwrapped to its text');
assert.ok(!html.includes('#time') && !html.includes('#tag'), 'no pipeline anchors leak');
assert.ok(html.includes('- 第一點<br>- 第二點'), 'line breaks inside a block are kept');
assert.equal(mdToHtml('<b>x</b>'), '<p>&lt;b&gt;x&lt;/b&gt;</p>', 'summary text is escaped');

const now = new Date();
const daysAgo = (n) => new Date(now.getTime() - n * 86400e3).toISOString();
const INSIGHTS = [
  { episode_id: 'e1', podcaster: 'Gooaye 股癌', podcast_launch_time: daysAgo(1), ticker: '2330', sentiment_label: 'BULLISH', time_horizon: '長期', bluf_thesis: '台積電是 AI 供應鏈核心持股，長期 EPS 趨勢向上。' },
  { episode_id: 'e2', podcaster: '財經一路發', podcast_launch_time: daysAgo(10), ticker: '2330', sentiment_label: 'NEUTRAL', time_horizon: '中期', bluf_thesis: '估值已高，等待回檔。' },
  { episode_id: 'e3', podcaster: '財經一路發', podcast_launch_time: daysAgo(45), ticker: '2330', sentiment_label: 'BEARISH', time_horizon: '短期', bluf_thesis: '短線過熱。' },
  // The pipeline also emits STRONG_* labels; production had 6 of 67 for 2330 on 2026-09-06.
  { episode_id: 'e4', podcaster: '財報狗', podcast_launch_time: daysAgo(2), ticker: '2330', sentiment_label: 'STRONG_BULLISH', time_horizon: '長期', bluf_thesis: '長期看好。' },
];
assert.deepEqual(tally(INSIGHTS), { days: 30, total: 3, bull: 2, neu: 1, bear: 0 });
assert.equal(normSentiment('strong_bearish'), 'BEARISH');
assert.equal(normSentiment('MIXED'), 'NEUTRAL');
assert.equal(normSentiment(undefined), null);
assert.deepEqual(tally([]).total, 0);

// The site's own numbers, as the crawler body states them.
assert.deepEqual(whoTalks(INSIGHTS), [{ name: '財經一路發', n: 2 }, { name: 'Gooaye 股癌', n: 1 }, { name: '財報狗', n: 1 }]);
assert.deepEqual(whoTalks(null), []);
const SERIES = [
  { d: '2026-09-02', n: 3, bull: 2, bear: 0 }, { d: '2026-08-30', n: 1, bull: 0, bear: 1 },
  { d: '2026-09-15', n: 2, bull: 1, bear: 1 }, { d: '2026-07-01', n: 0, bull: 0, bear: 0 },
];
assert.deepEqual(monthlyMentions(SERIES), [
  { ym: '2026-09', n: 5, bull: 3, bear: 1 }, { ym: '2026-08', n: 1, bull: 0, bear: 1 },
], 'months newest first, silent months dropped, order of the input ignored');
assert.deepEqual(latestLevel([{ d: '2026-09-30', p: 61 }, { d: '2026-10-01', p: 39 }, { d: '2026-01-01', p: 90 }]), { d: '2026-10-01', p: 39 });
assert.equal(latestLevel([]), null);
const FLOWS = Array.from({ length: 20 }, (_, i) => ({
  date: `2026-09-${String(i + 1).padStart(2, '0')}`, total_net_shares: 1_000_000, foreign_net_shares: i < 15 ? 0 : -400_000,
}));
assert.deepEqual(flowSums(FLOWS), [
  { days: 5, total: 5000, foreign: -2000 }, { days: 20, total: 20000, foreign: -2000 },
], 'sums the newest sessions in 張; a window longer than the data is left out');
assert.deepEqual(flowSums(undefined), []);

// --- 3. every sitemap route family resolves meta + body + JSON-LD ----------------
// No network: stub fetch so this runs in CI. Any route returning null here is a route
// whose pages all share index.html's title. Order matters: longer prefixes first.
const originalFetch = globalThis.fetch;
const EPISODE = {
  id: 'abc123', podcast_name: '股癌', episode_title: 'EP500 測試', released_at_ms: now.getTime(),
  spotify_images: ['https://x/i.png'], summary_content: SUMMARY,
  key_insights: ['聯準會 9 月升息機率驟降', 'AI 長多趨勢不變'],
  related_tickers: ['2330', '2327'],
  sector_exposures: [
    { exposure_id: 'sector_mlcc', display_name: '被動元件 MLCC', resolved_tickers: [{ ticker: '2327', name: '國巨' }] },
    { exposure_id: 'sector_mlcc', display_name: '被動元件 MLCC', resolved_tickers: [] },
  ],
};
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes('/api/episodes/by-sector/')) {
    return json({
      display_name: '被動元件 MLCC',
      description: '  被動元件 MLCC 題材涵蓋積層陶瓷電容與主要被動元件供應鏈。  ',
      resolved_tickers: [{ ticker: '2327', name: '國巨', reason: '全球最大晶片電阻供應商。' }],
      episodes: [{ id: 'abc123', podcast_name: '股癌', episode_title: 'EP500 測試' }],
      total: 12,
    });
  }
  if (u.includes('/api/episodes/attention')) {
    return json({
      episode_count_7d: 29, podcast_count_7d: 9,
      narratives: [{ id: 'aiindustry', name: 'AI產業', count_7d: 10, prev_7d: 11 }],
      tickers: [{ ticker: 'NVDA', name: '輝達', count_30d: 81, prev_30d: 96, count_7d: 14, prev_7d: 20 }],
      rising: [{ ticker: '3189', name: '景碩', count_30d: 9, prev_30d: 2, count_7d: 5, prev_7d: 0 }],
    });
  }
  if (u.includes('/cross-show')) {
    return json({
      episode_id: 'abc123', window_days: 30, podcaster: '股癌', as_of: '2026-09-20', shows_in_window: 9,
      rows: [
        { ticker: '2330', name: '台積電', stance: 'BULLISH', others: { shows: 5, mentions: 12, bull: 9, neutral: 3, bear: 0 }, relation: 'aligned' },
        { ticker: '2327', name: '國巨', stance: 'BEARISH', others: { shows: 2, mentions: 3, bull: 3, neutral: 0, bear: 0 }, relation: 'opposite' },
        { ticker: '6981', name: null, stance: null, others: { shows: 0, mentions: 0, bull: 0, neutral: 0, bear: 0 }, relation: 'alone' },
      ],
      disclaimer: 'x',
    });
  }
  if (u.includes('/mention-heat')) return json({ series: SERIES, market: [], level: [{ d: '2026-10-01', p: 39 }], level_window_days: 364 });
  if (u.includes('/institutional')) return json({ ticker: '2330', rows: FLOWS });
  if (u.includes('/api/episodes/recent')) return json({ episodes: [EPISODE] });
  if (u.includes('/api/episodes/by-tag/')) {
    // 'ai' is a rich tag (>= MIN_TAG_EPISODES); anything else is thin.
    const rich = /by-tag\/ai\b/.test(u);
    const n = rich ? MIN_TAG_EPISODES + 2 : 2;
    return json({ tag: 'x', total: n, episodes: Array.from({ length: n }, (_, i) => ({ ...EPISODE, id: `t${i}`, episode_title: `EP${i} 主題` })) });
  }
  if (/\/api\/weekly\/[^/?]+/.test(u)) {
    return json({
      week: '2026-W36', start: '2026-08-31', end: '2026-09-06', episode_count: 12,
      podcasts: [{ name: '股癌', episodes: 7 }, { name: '財經一路發', episodes: 5 }],
      tickers: [{ ticker: '2330', name: '台積電', episodes: 6, bull: 4, neu: 1, bear: 0, prev_bull: 1, prev_neu: 0, prev_bear: 2 }],
      sectors: [{ exposure_id: 'sector_mlcc', display_name: '被動元件 MLCC', episodes: 3 }],
      episodes: [{ id: 'abc123', podcast_name: '股癌', episode_title: 'EP500 測試', key_insights: ['升息機率驟降'] }],
    });
  }
  if (u.endsWith('/api/weekly')) return json({ weeks: [{ week: '2026-W36', start: '2026-08-31', end: '2026-09-06', episode_count: 12 }] });
  if (u.includes('/api/episodes/')) return json(EPISODE);
  if (u.includes('/api/articles/')) return json({ title: '測試文章', subtitle: '這是一段夠長的文章副標，會直接當成 meta description 使用', key_points: ['第一點'] });
  if (u.includes('/api/tags/registry')) return json({ tags: [{ slug: 'ai', display_zh: '人工智慧' }] });
  if (u.includes('/api/ticker-insights/by-ticker/')) return json(INSIGHTS);
  if (u.includes('/api/ticker-insights/by-podcaster/')) return json(INSIGHTS);
  if (u.includes('/api/ticker-insights/trending')) return json([{ ticker: '2330', count: 68, sentiment_label: 'BULLISH' }]);
  if (u.includes('/api/sectors/by-ticker/')) return json({ items: [{ exposure_id: 'sector_mlcc', display_name: '被動元件 MLCC', reason: '核心供應商。' }] });
  if (u.includes('/api/sectors')) return json({ sectors: [{ exposure_id: 'sector_mlcc', display_name: '被動元件 MLCC', description: '題材描述。' }] });
  if (/\/api\/stocks\/[^/]+\/basic/.test(u)) return json({ ticker: '2330', name: '台積電' });
  if (/\/api\/podcast\/[^/]+\/episodes/.test(u)) return json([EPISODE]);
  if (/\/api\/podcast\/[^/]+$/.test(u)) return json({ image_url: 'https://x/show.jpg' });
  if (u.endsWith('/api/podcast')) return json([{ name: 'Gooaye 股癌', episode_count: 18 }]);
  throw new Error(`unstubbed fetch: ${u}`);
};
const json = (body) => new Response(JSON.stringify(body), {
  status: 200, headers: { 'content-type': 'application/json' },
});

try {
  const cases = [
    ['/', null],
    ['/episode/abc123', 'EP500 測試'],
    ['/article/my-slug', '測試文章'],
    ['/stock/2330', '台積電（2330） · 股價與相關 Podcast'],
    ['/topics/ai', '#人工智慧'],
    ['/topics/AI', '#人工智慧'],                       // normalizer path
    ['/topics/quantum-computing', '#quantum computing'], // registry miss → fallback
    ['/weekly', 'Podcast 週報'],
    ['/weekly/2026-W36', 'W36 Podcast 週報：2026/08/31 – 09/06'],
    ['/podcaster/Gooaye%20%E8%82%A1%E7%99%8C', 'Gooaye 股癌 · Podcast 頻道'],
    ['/sector/sector_mlcc', '被動元件 MLCC'],
    ['/podcaster', '所有節目'],
    ['/stock', '所有個股'],
    ['/topics', '話題排行'],
    ['/articles', '文章'],
    ['/about', '關於 TinBoker'],
    ['/terms', '服務條款與政策'],
    ['/methodology', '資料來源與方法'],
  ];
  const titles = new Set();
  for (const [path, expected] of cases) {
    const meta = await metaFor(path, ORIGIN, API);
    assert.ok(meta, `${path} resolved no meta — crawlers get the generic homepage title`);
    assert.equal(meta.title, expected, `${path} title`);
    assert.ok(meta.description && meta.description.length > 10, `${path} needs a real description`);
    assert.ok(meta.url.startsWith(ORIGIN + '/'), `${path} canonical must be absolute`);
    const page = renderPage(meta);
    assert.ok(page.includes('<h1>') && page.includes('href="/about#disclaimer"'), `${path} body must carry the H1 and footer links`);
    titles.add(meta.title);
  }
  // The whole point: distinct pages must not share a title.
  assert.equal(titles.size, cases.length - 1, 'route titles collided (/topics/ai and /topics/AI are the same page)');

  // Dynamic families: the body is the page's own content, with links into the site,
  // and at least one JSON-LD object. The length floor is what makes a page more than
  // a title: below it, crawlers are back to evaluating an empty shell.
  const ldTypes = (meta) => (meta.ld || []).map((o) => o['@type']);
  const episode = await metaFor('/episode/abc123', ORIGIN, API);
  const epPage = renderPage(episode);
  assert.ok(epPage.length > 600, `episode body too short: ${epPage.length}`);
  for (const needle of ['<h2>重點</h2>', '<h2>章節</h2>', '00:37 升息機率驟降', 'href="/stock/2330"', '國巨（2327）', 'href="/sector/sector_mlcc"', 'href="/podcaster/%E8%82%A1%E7%99%8C"']) {
    assert.ok(epPage.includes(needle), `episode body missing ${needle}`);
  }
  assert.equal((epPage.match(/href="\/sector\/sector_mlcc"/g) || []).length, 1, 'duplicate sector exposures collapse to one link');
  // 其他節目怎麼看: the one section that is not a restatement of the episode itself.
  for (const needle of [
    '<h2>其他節目怎麼看</h2>',
    '有 2 檔在發布前 30 天內也被其他節目談到（同期共 9 個節目）：1 檔與其他節目同向、1 檔相反。',
    '台積電（2330）</a>：本集看多，其他 5 個節目、12 次提及：9 看多 · 3 中立 · 0 看空 — 與其他節目同向',
    '國巨（2327）</a>：本集看空，其他 2 個節目、3 次提及：3 看多 · 0 中立 · 0 看空 — 與其他節目相反',
    'href="/methodology#stance"',
  ]) {
    assert.ok(epPage.includes(needle), `episode body missing ${needle}`);
  }
  assert.ok(!epPage.includes('只有這個節目談到'), 'a ticker nobody else mentioned has nothing to compare and is left out');
  assert.ok(epPage.indexOf('其他節目怎麼看') < epPage.indexOf('聯準會鴿聲振奮台股'), 'the cross-show section comes before the summary');
  assert.ok(readFileSync(resolve(here, '../src/components/episode/CrossShowPanel.tsx'), 'utf8').includes("shared/crossShow.js'"), 'CrossShowPanel no longer reads shared/crossShow.js');
  assert.deepEqual(ldTypes(episode), ['PodcastEpisode', 'BreadcrumbList']);
  assert.equal(episode.ld[0].hasPart.length, 2, 'one Clip per timestamped chapter');
  assert.equal(episode.ld[0].hasPart[0].url, `${ORIGIN}/episode/abc123#t-37`);

  // RSS episodes have SVG summary cards and no Spotify episode artwork.
  const originalImages = EPISODE.spotify_images;
  EPISODE.spotify_images = [];
  EPISODE.summary_image_public_url = 'https://x/summary.svg';
  assert.equal((await metaFor('/episode/abc123', ORIGIN, API)).image, 'https://x/show.jpg');
  EPISODE.summary_image_public_url = 'https://x/summary.png';
  assert.equal((await metaFor('/episode/abc123', ORIGIN, API)).image, 'https://x/summary.png');
  EPISODE.spotify_images = originalImages;
  delete EPISODE.summary_image_public_url;

  const stock = await metaFor('/stock/2330', ORIGIN, API);
  const stockPage = renderPage(stock);
  assert.ok(stock.description.startsWith('台積電（2330） 近 30 天 3 集 Podcast 提及：2 看多 · 1 中立 · 0 看空。'), `stock description is live data: ${stock.description}`);
  assert.ok(stock.description.length <= 160, 'stock description fits a snippet');

  // Paywall: 觀點 from the last week are members-only on the page, so serving them
  // to a crawler would be cloaking. The tally still counts every mention (the page
  // shows that total to everyone) — only the readable rows are cut.
  // (The shows' NAMES do appear: 誰在談 counts every mention per show, as the page's
  // tile does for everyone. A count is not the gated text.)
  for (const gated of ['href="/episode/e1"', '台積電是 AI 供應鏈核心持股', 'href="/episode/e4"', '長期看好。']) {
    assert.ok(!stockPage.includes(gated), `paywalled mention leaked to the crawler body: ${gated}`);
  }
  assert.ok(stock.description.includes('最近：財經一路發'), `description quotes the newest FREE mention: ${stock.description}`);
  // e2/e3 are older than the paywall window, so they stay indexable; e1 (1 day) and
  // e4 (2 days) are members-only and must NOT reach a crawler — see the gated
  // assertions below.
  for (const needle of ['<h2>Podcast 觀點</h2>', 'href="/episode/e2"', 'href="/episode/e3"', 'href="/podcaster/%E8%B2%A1%E7%B6%93%E4%B8%80%E8%B7%AF%E7%99%BC"', 'href="/sector/sector_mlcc"', '看空']) {
    assert.ok(stockPage.includes(needle), `stock body missing ${needle}`);
  }
  // The page's own numbers reach the crawler as text, not only the shows' thesis lines.
  for (const needle of [
    '<h2>誰在談 · 90 天</h2>', '財經一路發</a> · 2 集', 'Gooaye 股癌</a> · 1 集',
    '<h2>Podcast 聲量</h2>', '聲量水位 39', '第 39 百分位', 'href="/methodology#stats"', '2026/09 · 5 次 · 3 看多 · 1 看空',
    '<h2>三大法人買賣超</h2>', '近 5 個交易日：三大法人合計買超 5,000 張，其中外資賣超 2,000 張',
  ]) {
    assert.ok(stockPage.includes(needle), `stock body missing ${needle}`);
  }
  assert.ok(!stockPage.includes('近 60 個交易日'), 'no 60-session line from 20 sessions of data');
  assert.deepEqual(ldTypes(stock), ['BreadcrumbList']);
  // Indexability follows what the body carries: free 觀點, not total mentions. This
  // fixture has four mentions but only two a non-member can read — a thin page.
  assert.equal(stock.noindex, true, 'two readable 觀點 is below the floor');
  assert.equal(stockNoindex(MIN_STOCK_INSIGHTS), false);
  assert.equal(stockNoindex(MIN_STOCK_INSIGHTS - 1), true);
  assert.equal(stockNoindex(0), true);
  {
    const inner = globalThis.fetch;
    const more = [...INSIGHTS, { ...INSIGHTS[1], episode_id: 'e5', podcast_launch_time: daysAgo(20) }];
    globalThis.fetch = async (url) => (String(url).includes('/api/ticker-insights/by-ticker/') ? json(more) : inner(url));
    assert.equal((await metaFor('/stock/2330', ORIGIN, API)).noindex, false, 'three readable 觀點 is indexable');
    // A failed insights fetch is unknown, not thin — do not noindex a page on an API blip.
    globalThis.fetch = async (url) => (String(url).includes('/api/ticker-insights/by-ticker/') ? new Response('', { status: 500 }) : inner(url));
    assert.equal((await metaFor('/stock/2330', ORIGIN, API)).noindex, false, 'insights fetch failure stays indexable');
    globalThis.fetch = inner;
  }
  // A ticker nobody has discussed keeps the template description rather than "0 集".
  globalThis.fetch = (fetchWithEmptyInsights => async (url) => {
    const u = String(url);
    if (u.includes('/api/ticker-insights/by-ticker/')) return json([]);
    return fetchWithEmptyInsights(url);
  })(globalThis.fetch);
  const quiet = await metaFor('/stock/9999', ORIGIN, API);
  assert.ok(quiet.description.startsWith('查看 台積電（9999） 的即時股價走勢'), `quiet ticker keeps the template: ${quiet.description}`);
  assert.ok(!renderPage(quiet).includes('Podcast 觀點'), 'quiet ticker renders no empty insight section');
  assert.equal(quiet.noindex, true, 'a ticker with nothing to read is not offered to Google');

  const sector = await metaFor('/sector/sector_mlcc', ORIGIN, API);
  // The sector description is the page's own paragraph, trimmed — not the template.
  assert.equal(sector.description, '被動元件 MLCC 題材涵蓋積層陶瓷電容與主要被動元件供應鏈。');
  const sectorPage = renderPage(sector);
  for (const needle of ['<h2>相關個股</h2>', '國巨（2327）', '全球最大晶片電阻供應商', '<h2>相關集數</h2>', 'href="/episode/abc123"']) {
    assert.ok(sectorPage.includes(needle), `sector body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(sector), ['BreadcrumbList']);
  // Sector pages follow the sitemap's two-episode floor; an unknown total stays indexable.
  assert.equal(sector.noindex, false, 'a sector with enough episodes is indexable');
  assert.equal(sectorNoindex(1), true);
  assert.equal(sectorNoindex(2), false);
  assert.equal(sectorNoindex(null), false);
  // A cold by-sector query can take 20-50 s on the API; when it misses the deadline the
  // page still gets its title and description from the cached sector list.
  globalThis.fetch = ((inner) => async (url) => {
    if (String(url).includes('/api/episodes/by-sector/')) return new Response('', { status: 500 });
    return inner(url);
  })(globalThis.fetch);
  const slow = await metaFor('/sector/sector_mlcc', ORIGIN, API);
  assert.equal(slow.title, '被動元件 MLCC', 'sector title survives a by-sector failure');
  assert.equal(slow.description, '題材描述。');
  assert.ok(!renderPage(slow).includes('<h2>'), 'no empty sections when the enrichment is missing');
  assert.equal(await metaFor('/sector/sector_unknown', ORIGIN, API), null, 'unknown sector still resolves nothing');

  const podcaster = await metaFor('/podcaster/Gooaye%20%E8%82%A1%E7%99%8C', ORIGIN, API);
  const podPage = renderPage(podcaster);
  for (const needle of ['<h2>最新集數</h2>', 'href="/episode/abc123"', '<li>聯準會 9 月升息機率驟降</li>', '<h2>最常提到的個股</h2>', 'href="/stock/2330"', '4 次']) {
    assert.ok(podPage.includes(needle), `podcaster body missing ${needle}`);
  }
  assert.ok(podcaster.description.includes('最常提到：2330'), `podcaster description is live: ${podcaster.description}`);
  assert.deepEqual(ldTypes(podcaster), ['PodcastSeries', 'BreadcrumbList']);

  const home = await metaFor('/', ORIGIN, API);
  assert.equal(home.url, `${ORIGIN}/`);
  const homePage = renderPage(home);
  for (const needle of [
    '<h1>聽播客 TinBoker</h1>', '<h2>最新集數</h2>', 'href="/episode/abc123"', '<h2>近 30 天熱門個股</h2>', 'href="/stock/2330"',
    // The three panels the home page actually leads with.
    '<h2>本週市場在聊什麼</h2>', '近 7 天收錄 29 集、9 個節目', 'href="/topics/aiindustry"', '10 集（前期 11）',
    '<h2>最多人聊</h2>', '輝達（NVDA）</a> · 81 集（前期 96）',
    '<h2>升溫最快</h2>', '景碩（3189）</a> · 5 集（前期 0）', 'href="/methodology"',
  ]) {
    assert.ok(homePage.includes(needle), `home body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(home), ['WebSite', 'Organization']);

  // Plain-text pages: the crawler body is the page's full copy (shared/sitePages.js),
  // not an excerpt. The needles are the things an excerpt once dropped — /terms served
  // 4 sentences and no advertising-cookie disclosure.
  const text = (html) => html.replace(/<[^>]+>/g, '');
  const terms = renderPage(await metaFor('/terms', ORIGIN, API));
  for (const needle of ['<h2>隱私權政策</h2>', '廣告與 Cookie', 'Google AdSense', 'href="https://adssettings.google.com"', '個人資料保護法', '<h2>退款政策</h2>', '七個工作日', 'href="/membership"']) {
    assert.ok(terms.includes(needle), `/terms body missing ${needle}`);
  }
  assert.ok(text(terms).length > 2000, `/terms body is an excerpt again: ${text(terms).length} chars`);
  const about = renderPage(await metaFor('/about', ORIGIN, API));
  for (const needle of ['<h2>經營者與方法</h2>', '以個人名義經營', 'href="/methodology"', '<h2>聯絡我們</h2>', 'contact@tinboker.com', '<h2>免責聲明</h2>', '責任限制']) {
    assert.ok(about.includes(needle), `/about body missing ${needle}`);
  }
  assert.ok(text(about).length > 900, `/about body is an excerpt again: ${text(about).length} chars`);
  const method = renderPage(await metaFor('/methodology', ORIGIN, API));
  for (const needle of ['<h2>資料來源</h2>', '<h2>摘要怎麼產生</h2>', '<h2>個股觀點與看多、看空</h2>', '聲量水位', '<h2>限制與更正</h2>', 'href="/podcaster"', 'href="/weekly"']) {
    assert.ok(method.includes(needle), `/methodology body missing ${needle}`);
  }
  assert.ok(text(method).length > 1200, `/methodology body too short: ${text(method).length} chars`);
  // The pages render the same module, so a page that stops importing it has drifted.
  for (const page of ['About.tsx', 'TermsPage.tsx', 'MethodologyPage.tsx']) {
    assert.ok(readFileSync(resolve(here, '../src/pages', page), 'utf8').includes("shared/sitePages.js'"), `${page} no longer reads shared/sitePages.js`);
  }

  // Index pages link to what they list — the hub links Google follows into the site.
  assert.ok(renderPage(await metaFor('/stock', ORIGIN, API)).includes('href="/stock/2330"'), '/stock index links its tickers');
  assert.ok(renderPage(await metaFor('/podcaster', ORIGIN, API)).includes('href="/podcaster/Gooaye%20%E8%82%A1%E7%99%8C"'), '/podcaster index links its channels');
  assert.ok(renderPage(await metaFor('/topics', ORIGIN, API)).includes('href="/sector/sector_mlcc"'), '/topics index links its sectors');

  // /tag/:tag renders the same page as /topics/:tag, so it must canonicalize there —
  // otherwise the page competes with its own twin.
  const legacy = await metaFor('/tag/ai', ORIGIN, API);
  assert.equal(legacy.url, `${ORIGIN}/topics/ai`);
  assert.equal(legacy.title, '#人工智慧');

  // Weekly pages: Article JSON-LD, links into stock / sector / episode pages.
  const weekly = await metaFor('/weekly/2026-W36', ORIGIN, API);
  const weeklyPage = renderPage(weekly);
  for (const needle of ['<h2>本週熱門個股</h2>', '台積電（2330）', '4 看多', 'href="/sector/sector_mlcc"', 'href="/episode/abc123"', '升息機率驟降']) {
    assert.ok(weeklyPage.includes(needle), `weekly body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(weekly), ['Article', 'BreadcrumbList']);
  assert.equal(weekly.type, 'article');
  assert.ok(renderPage(await metaFor('/weekly', ORIGIN, API)).includes('href="/weekly/2026-W36"'), '/weekly index links its weeks');

  // Everything else stays untouched — the middleware is not a router.
  for (const path of ['/watchlist', '/assets/index.js', '/episode/a/b', '/admin/tags', '/profile']) {
    assert.equal(await metaFor(path, ORIGIN, API), null, `${path} should not be rewritten`);
    assert.equal(isCandidate(path), false, `${path} should not reach metaFor at all`);
  }

  // The gate and the resolver must agree, or a covered route silently never runs.
  for (const [path] of cases) {
    assert.ok(isCandidate(path), `${path} resolves meta but the gate rejects it`);
  }

  // --- 4. tag pages: indexable only above the episode floor -------------------------
  // A tag with >= MIN_TAG_EPISODES scoped episodes renders those episodes' key insights
  // and is offered to Google; a thin one keeps its social card but stays noindex.
  for (const p of ['/topics/ai', '/topics/ai/', '/tag/ai', '/topics/quantum-computing']) {
    assert.ok(TAG_ROUTE.test(p), `${p} is a tag route`);
  }
  assert.ok(!TAG_ROUTE.test('/topics') && !TAG_ROUTE.test('/sector/sector_mlcc'), 'index and sector pages are not tag routes');
  const rich = await metaFor('/topics/ai', ORIGIN, API);
  assert.equal(rich.noindex, false, 'a tag with enough episodes is indexable');
  const richPage = renderPage(rich);
  for (const needle of ['<h2>相關集數</h2>', 'EP0 主題', '升息機率驟降', 'href="/episode/t0"']) {
    assert.ok(richPage.includes(needle), `rich tag body missing ${needle}`);
  }
  assert.ok(rich.description.startsWith(`近期 ${MIN_TAG_EPISODES + 2} 集 Podcast 談到「人工智慧」`), `tag description is live: ${rich.description}`);
  assert.deepEqual(ldTypes(rich), ['BreadcrumbList']);
  const thin = await metaFor('/topics/quantum-computing', ORIGIN, API);
  assert.equal(thin.noindex, true, 'a thin tag stays noindex');
  assert.equal(tagNoindex(undefined), true, 'no data → noindex');
  assert.equal(tagNoindex(MIN_TAG_EPISODES), false);
} finally {
  globalThis.fetch = originalFetch;
}

console.log('validate-crawler-meta: ok');
