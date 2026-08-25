// Guards functions/_middleware.js — the crawler-meta edge function.
//
// Two things break silently here and only show up months later as pages missing from
// Google: (a) a content route drifts out of the router and starts serving index.html's
// generic title to every crawler, (b) the tag-slug normalizer drifts from the client's
// copy in src/hooks/useTagLabels.ts, so /topics/:tag resolves a different label than the
// page renders. Both are asserted below.
//
// Run: npm run validate:seo

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const mw = await import(resolve(here, '../functions/_middleware.js'));
const { metaFor, isCandidate, normalizeTagSlug, tagLabelFallback } = mw;

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

// --- 2. every sitemap route family resolves meta --------------------------------
// No network: stub fetch so this runs in CI. Any route returning null here is a route
// whose pages all share index.html's title.
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes('/api/episodes/by-sector/')) {
    return json({ display_name: '被動元件 MLCC', description: '  被動元件 MLCC 題材涵蓋積層陶瓷電容與主要被動元件供應鏈。  ' });
  }
  if (u.includes('/api/episodes/')) {
    return json({ podcast_name: '股癌', episode_title: 'EP500 測試', spotify_images: ['https://x/i.png'] });
  }
  if (u.includes('/api/articles/')) return json({ title: '測試文章', subtitle: '這是一段夠長的文章副標，會直接當成 meta description 使用' });
  if (u.includes('/api/tags/registry')) {
    return json({ tags: [{ slug: 'ai', display_zh: '人工智慧' }] });
  }
  throw new Error(`unstubbed fetch: ${u}`);
};
const json = (body) => new Response(JSON.stringify(body), {
  status: 200, headers: { 'content-type': 'application/json' },
});

try {
  const cases = [
    ['/episode/abc123', 'EP500 測試'],
    ['/article/my-slug', '測試文章'],
    ['/stock/2330', '2330 · 股價與相關 Podcast'],
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
    titles.add(meta.title);
  }
  // The whole point: distinct pages must not share a title.
  assert.equal(titles.size, cases.length - 1, 'route titles collided (/topics/ai and /topics/AI are the same page)');

  // The sector description is the page's own paragraph, trimmed — not the template.
  const sector = await metaFor('/sector/sector_mlcc', ORIGIN, API);
  assert.equal(sector.description, '被動元件 MLCC 題材涵蓋積層陶瓷電容與主要被動元件供應鏈。');

  // /tag/:tag renders the same page as /topics/:tag, so it must canonicalize there —
  // otherwise the page competes with its own twin.
  const legacy = await metaFor('/tag/ai', ORIGIN, API);
  assert.equal(legacy.url, `${ORIGIN}/topics/ai`);
  assert.equal(legacy.title, '#人工智慧');

  // Everything else stays untouched — the middleware is not a router.
  for (const path of ['/', '/watchlist', '/assets/index.js', '/episode/a/b', '/admin/tags']) {
    assert.equal(await metaFor(path, ORIGIN, API), null, `${path} should not be rewritten`);
    assert.equal(isCandidate(path), false, `${path} should not reach metaFor at all`);
  }

  // The gate and the resolver must agree, or a covered route silently never runs.
  for (const [path] of cases) {
    assert.ok(isCandidate(path), `${path} resolves meta but the gate rejects it`);
  }
} finally {
  globalThis.fetch = originalFetch;
}

console.log('validate-crawler-meta: ok');
