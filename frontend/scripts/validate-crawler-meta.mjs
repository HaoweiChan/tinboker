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
  metaFor, isCandidate, normalizeTagSlug, tagLabelFallback, NOINDEX_ROUTE,
  renderPage, mdToHtml, chapters, tally,
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
];
assert.deepEqual(tally(INSIGHTS), { days: 30, total: 2, bull: 1, neu: 1, bear: 0 });
assert.deepEqual(tally([]).total, 0);

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
    });
  }
  if (u.includes('/api/episodes/recent')) return json({ episodes: [EPISODE] });
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
    ['/podcaster/Gooaye%20%E8%82%A1%E7%99%8C', 'Gooaye 股癌 · Podcast 頻道'],
    ['/sector/sector_mlcc', '被動元件 MLCC'],
    ['/podcaster', '所有節目'],
    ['/stock', '所有個股'],
    ['/topics', '話題排行'],
    ['/articles', '文章'],
    ['/about', '關於 TinBoker'],
    ['/contact', '聯絡我們'],
    ['/disclaimer', '免責聲明'],
  ];
  const titles = new Set();
  for (const [path, expected] of cases) {
    const meta = await metaFor(path, ORIGIN, API);
    assert.ok(meta, `${path} resolved no meta — crawlers get the generic homepage title`);
    assert.equal(meta.title, expected, `${path} title`);
    assert.ok(meta.description && meta.description.length > 10, `${path} needs a real description`);
    assert.ok(meta.url.startsWith(ORIGIN + '/'), `${path} canonical must be absolute`);
    const page = renderPage(meta);
    assert.ok(page.includes('<h1>') && page.includes('href="/disclaimer"'), `${path} body must carry the H1 and footer links`);
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
  assert.deepEqual(ldTypes(episode), ['PodcastEpisode', 'BreadcrumbList']);
  assert.equal(episode.ld[0].hasPart.length, 2, 'one Clip per timestamped chapter');
  assert.equal(episode.ld[0].hasPart[0].url, `${ORIGIN}/episode/abc123#t-37`);

  const stock = await metaFor('/stock/2330', ORIGIN, API);
  const stockPage = renderPage(stock);
  assert.ok(stock.description.startsWith('台積電（2330） 近 30 天 2 集 Podcast 提及：1 看多 · 1 中立 · 0 看空。'), `stock description is live data: ${stock.description}`);
  assert.ok(stock.description.length <= 160, 'stock description fits a snippet');
  for (const needle of ['<h2>Podcast 觀點</h2>', 'href="/episode/e1"', 'href="/podcaster/Gooaye%20%E8%82%A1%E7%99%8C"', 'href="/sector/sector_mlcc"', '看空']) {
    assert.ok(stockPage.includes(needle), `stock body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(stock), ['BreadcrumbList']);
  // A ticker nobody has discussed keeps the template description rather than "0 集".
  globalThis.fetch = (fetchWithEmptyInsights => async (url) => {
    const u = String(url);
    if (u.includes('/api/ticker-insights/by-ticker/')) return json([]);
    return fetchWithEmptyInsights(url);
  })(globalThis.fetch);
  const quiet = await metaFor('/stock/9999', ORIGIN, API);
  assert.ok(quiet.description.startsWith('查看 台積電（9999） 的即時股價走勢'), `quiet ticker keeps the template: ${quiet.description}`);
  assert.ok(!renderPage(quiet).includes('Podcast 觀點'), 'quiet ticker renders no empty insight section');

  const sector = await metaFor('/sector/sector_mlcc', ORIGIN, API);
  // The sector description is the page's own paragraph, trimmed — not the template.
  assert.equal(sector.description, '被動元件 MLCC 題材涵蓋積層陶瓷電容與主要被動元件供應鏈。');
  const sectorPage = renderPage(sector);
  for (const needle of ['<h2>相關個股</h2>', '國巨（2327）', '全球最大晶片電阻供應商', '<h2>相關集數</h2>', 'href="/episode/abc123"']) {
    assert.ok(sectorPage.includes(needle), `sector body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(sector), ['BreadcrumbList']);
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
  for (const needle of ['<h2>最新集數</h2>', 'href="/episode/abc123"', '<h2>最常提到的個股</h2>', 'href="/stock/2330"', '3 次']) {
    assert.ok(podPage.includes(needle), `podcaster body missing ${needle}`);
  }
  assert.ok(podcaster.description.includes('最常提到：2330'), `podcaster description is live: ${podcaster.description}`);
  assert.deepEqual(ldTypes(podcaster), ['PodcastSeries', 'BreadcrumbList']);

  const home = await metaFor('/', ORIGIN, API);
  assert.equal(home.url, `${ORIGIN}/`);
  const homePage = renderPage(home);
  for (const needle of ['<h1>聽播客 TinBoker</h1>', '<h2>最新集數</h2>', 'href="/episode/abc123"', '<h2>近 30 天熱門個股</h2>', 'href="/stock/2330"']) {
    assert.ok(homePage.includes(needle), `home body missing ${needle}`);
  }
  assert.deepEqual(ldTypes(home), ['WebSite', 'Organization']);

  // Index pages link to what they list — the hub links Google follows into the site.
  assert.ok(renderPage(await metaFor('/stock', ORIGIN, API)).includes('href="/stock/2330"'), '/stock index links its tickers');
  assert.ok(renderPage(await metaFor('/podcaster', ORIGIN, API)).includes('href="/podcaster/Gooaye%20%E8%82%A1%E7%99%8C"'), '/podcaster index links its channels');
  assert.ok(renderPage(await metaFor('/topics', ORIGIN, API)).includes('href="/sector/sector_mlcc"'), '/topics index links its sectors');

  // /tag/:tag renders the same page as /topics/:tag, so it must canonicalize there —
  // otherwise the page competes with its own twin.
  const legacy = await metaFor('/tag/ai', ORIGIN, API);
  assert.equal(legacy.url, `${ORIGIN}/topics/ai`);
  assert.equal(legacy.title, '#人工智慧');

  // Everything else stays untouched — the middleware is not a router.
  for (const path of ['/watchlist', '/assets/index.js', '/episode/a/b', '/admin/tags', '/profile']) {
    assert.equal(await metaFor(path, ORIGIN, API), null, `${path} should not be rewritten`);
    assert.equal(isCandidate(path), false, `${path} should not reach metaFor at all`);
  }

  // The gate and the resolver must agree, or a covered route silently never runs.
  for (const [path] of cases) {
    assert.ok(isCandidate(path), `${path} resolves meta but the gate rejects it`);
  }

  // --- 4. thin routes are noindex, valuable ones are not -------------------------
  // Topic pages carry 97 characters of their own around a link list, repeated across
  // ~166 of them. They keep their social card (meta still resolves) but must not be
  // offered to Google. Sector pages are the contrast and must stay indexable.
  for (const p of ['/topics/ai', '/topics/ai/', '/tag/ai']) {
    assert.ok(NOINDEX_ROUTE.test(p), `${p} should be noindex`);
    assert.ok(await metaFor(p, ORIGIN, API), `${p} should still resolve a social card`);
  }
  for (const p of ['/sector/sector_mlcc', '/episode/abc123', '/topics', '/', '/stock/2330']) {
    assert.ok(!NOINDEX_ROUTE.test(p), `${p} must stay indexable`);
  }
} finally {
  globalThis.fetch = originalFetch;
}

console.log('validate-crawler-meta: ok');
