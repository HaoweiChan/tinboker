// Cloudflare Pages Function — per-route meta, JSON-LD and a crawler-visible body.
//
// Non-JS crawlers (LINE, Threads, Facebook, Twitter/X, Slack, Discord, ...) never
// run the SPA's React, so a shared content link shows the generic homepage card.
// This middleware detects crawlers on content routes, fetches the page's real data
// from the platform API, and rewrites <head> with accurate OG / Twitter / title tags.
// Covered: /, /episode, /article, /stock, /topics (+ legacy /tag), /sector, /podcaster,
// and the index pages listed in STATIC_META. Anything left out serves index.html's
// generic title to Googlebot, i.e. N pages that look like exact duplicates of each
// other and mostly never get indexed — which is what /topics (166 URLs), /sector (81)
// and /podcaster (10) were all doing before they were added here.
//
// Since 2026-09 it also fills <div id="root"> with the page's content as plain HTML
// (headings, lists, links) and emits schema.org JSON-LD in <head>. Measured before:
// every public page handed crawlers ~600 characters of script residue and zero
// structured data, because all content arrives via useEffect after mount. React mounts
// with createRoot().render(), which replaces whatever is inside #root, so humans never
// see this markup; crawlers see the same text and links the rendered page shows (not
// cloaking — it is the same API payload the components fetch).
//
// Humans pass straight through (no edge fetch, no change) — React + react-helmet
// already set their meta client-side. Every path is wrapped so any failure falls back
// to the unmodified SPA: this middleware can never break a page.

const CRAWLER = /bot|crawl|spider|mediapartners|facebookexternalhit|facebot|twitterbot|\bline\b|slackbot|whatsapp|telegrambot|discordbot|pinterest|linkedinbot|redditbot|embedly|quora|skypeuripreview|applebot|googlebot|bingbot|baiduspider|yandex|duckduckbot/i;

const BRAND_IMG = 'https://tinboker.com/brand/tinboker-square-dark-1080.png';
const CACHE_1H = { cf: { cacheTtl: 3600, cacheEverything: true } };
const SITE = '聽播客 TinBoker';
// Only these serve indexable content; every other host this code runs on (dev.,
// staging., <pr>.pages.dev) is a copy of it.
const PROD_HOSTS = new Set(['tinboker.com', 'www.tinboker.com']);

// Routes served noindex even on production. /topics/:tag renders 97 characters of its
// own — nav chrome plus one sentence that is identical across all ~166 tag pages — around
// a list of links to episode summaries. That is the "low value content" shape AdSense
// suspended the site over. The pages stay for navigation; they just stop being something
// Google evaluates. Sector pages are deliberately NOT here: their hand-written thesis and
// per-constituent descriptions are the curation the same policy asks for.
export const NOINDEX_ROUTE = /^\/(?:topics|tag)\/[^/]+\/?$/;

function apiBase(hostname) {
  const h = hostname.replace(/^www\./, '');
  const apiHost = h === 'tinboker.com'
    ? 'api.tinboker.com'
    : h.replace(/\.tinboker\.com$/, '-api.tinboker.com');
  return `https://${apiHost}`;
}

// Social crawlers (FB/LINE/Twitter/...) reject SVG og:images, so only use an
// image URL if it's a raster format; otherwise fall back to a valid PNG card.
function rasterImage(url, fallback) {
  return url && !/\.svg(\?|#|$)/i.test(url) ? url : fallback;
}

// Attribute/text-safe escaping for values injected into the HTML.
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// --- Tag labels ---------------------------------------------------------------
// /topics/:tag renders a zh-TW label, not the English slug, so the crawler title has
// to resolve the same registry the client does. Mirrors normalizeTagSlug/tagLabelFor
// in src/hooks/useTagLabels.ts — keep the two in sync (scripts/validate-crawler-meta.mjs
// asserts the alias table matches).
const TAG_ALIASES = {
  datacenters: 'datacenter',
  earningsreport: 'earnings',
  electricvehicles: 'ev',
  electric_vehicles: 'ev',
  lowearthorbitsatellite: 'leosatellite',
  mergersandacquisitions: 'mergersacquisitions',
};

export function normalizeTagSlug(slug) {
  const s = String(slug).replace(/^#/, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return TAG_ALIASES[s] || s;
}

// Fallback when the registry has no entry — same shape the client falls back to.
export function tagLabelFallback(tag) {
  return String(tag).replace(/^#/, '').replace(/[_-]/g, ' ');
}

// The registry is one small document shared by every topic page; let the edge cache
// hold it for an hour instead of refetching per crawl.
async function tagLabel(tag, api) {
  try {
    const r = await fetch(`${api}/api/tags/registry`, CACHE_1H);
    if (!r.ok) return tagLabelFallback(tag);
    const reg = await r.json();
    const want = normalizeTagSlug(tag);
    for (const entry of reg.tags || []) {
      if (entry.slug && entry.display_zh && normalizeTagSlug(entry.slug) === want) return entry.display_zh;
    }
  } catch (_e) { /* fall through */ }
  return tagLabelFallback(tag);
}

// --- Crawler-visible body helpers ---------------------------------------------
// Every builder degrades to an empty string when its fetch fails: a page with meta and
// no body is still better than the untouched shell.
async function getJson(url, init) {
  try {
    const r = await fetch(url, init);
    return r.ok ? await r.json() : null;
  } catch (_e) {
    return null;
  }
}
// null after `ms`; the fetch itself keeps running at the edge and warms the API cache
// for the next crawl.
const withTimeout = (p, ms) => Promise.race([p, new Promise((res) => setTimeout(() => res(null), ms))]);

const a = (href, text) => `<a href="${esc(href)}">${esc(text)}</a>`;
const ul = (items) => (items.length ? `<ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul>` : '');
const stockLink = (t, name) => a(`/stock/${encodeURIComponent(t)}`, name ? `${name}（${t}）` : t);
const episodeLink = (e) => a(`/episode/${encodeURIComponent(e.id)}`, e.episode_title || `EP ${e.episode_number ?? ''}`);
const sectorLink = (s) => a(`/sector/${encodeURIComponent(s.exposure_id)}`, s.display_name || s.exposure_id);
const podcasterLink = (name) => a(`/podcaster/${encodeURIComponent(name)}`, name);
// Mirrors normalizeSentiment in src/lib/sentiment.ts: the pipeline also emits
// STRONG_BULLISH / STRONG_BEARISH and older BULL/BEAR/POSITIVE/NEGATIVE/MIXED labels.
export function normSentiment(raw) {
  const s = String(raw ?? '').trim().toUpperCase();
  if (['BULLISH', 'BULL', 'POSITIVE', 'STRONG_BULLISH'].includes(s)) return 'BULLISH';
  if (['BEARISH', 'BEAR', 'NEGATIVE', 'STRONG_BEARISH'].includes(s)) return 'BEARISH';
  if (['NEUTRAL', 'NEUT', 'MIXED'].includes(s)) return 'NEUTRAL';
  return null;
}
const SENTIMENT_ZH = { BULLISH: '看多', BEARISH: '看空', NEUTRAL: '中立' };
const sentimentZh = (raw) => SENTIMENT_ZH[normSentiment(raw)] || '';
const day = (iso) => (iso ? String(iso).slice(0, 10) : '');
const hms = (sec) => {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = `${m}`.padStart(2, '0'), ss = `${s}`.padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
// Same three links the sidebar carries; also the only inbound links /contact and
// /disclaimer have from content pages.
const FOOTER = `<footer>${a('/about', '關於 TinBoker')} · ${a('/contact', '聯絡我們')} · ${a('/disclaimer', '免責聲明')}</footer>`;

// Summary markdown → HTML. Only the constructs the pipeline emits: '#'/'##' headings
// carrying '(#time:ms)' anchors, '[text](#tag:x)' links, paragraphs. The client strips the
// same anchors (src/utils/timeFormat.ts), so the text matches what the page renders.
// The page's H1 is the episode title, so summary headings shift down one level.
export function mdToHtml(md) {
  const out = [];
  for (const block of String(md || '').split(/\n{2,}/)) {
    const t = block.trim()
      .replace(/\(#time:\s*\d+\)/g, '')
      .replace(/\[([^\]]+)\]\(#[^)]*\)/g, '$1')
      .trim();
    if (!t) continue;
    const h = t.match(/^(#{1,3})\s+([\s\S]*)$/);
    if (h) {
      const lvl = Math.min(h[1].length + 1, 4);
      out.push(`<h${lvl}>${esc(h[2].trim())}</h${lvl}>`);
    } else {
      out.push(`<p>${esc(t).replace(/\n/g, '<br>')}</p>`);
    }
  }
  return out.join('');
}

// [{title, sec}] from the '## title (#time:ms)' headings — the sections the player shows
// as chapters and EpisodeDetail emits as Clip parts.
export function chapters(md) {
  const out = [];
  for (const m of String(md || '').matchAll(/^##\s+(.*?)\s*\(#time:\s*(\d+)\)/gm)) {
    out.push({ title: m[1].replace(/\[([^\]]+)\]\(#[^)]*\)/g, '$1').trim(), sec: Math.floor(Number(m[2]) / 1000) });
  }
  return out;
}

// Bullish / neutral / bearish tally of per-episode insights inside the last N days.
export function tally(insights, days = 30) {
  const since = Date.now() - days * 86400e3;
  const recent = (insights || []).filter((i) => Date.parse(i.podcast_launch_time || '') >= since);
  const n = (label) => recent.filter((i) => normSentiment(i.sentiment_label) === label).length;
  return { days, total: recent.length, bull: n('BULLISH'), neu: n('NEUTRAL'), bear: n('BEARISH') };
}
const tallySentence = (name, t) =>
  `${name} 近 ${t.days} 天 ${t.total} 集 Podcast 提及：${t.bull} 看多 · ${t.neu} 中立 · ${t.bear} 看空。`;

// JSON.stringify never emits '</script>', but '<' inside a value could still open a tag
// for a lenient parser — escape it.
const ldScript = (obj) => `<script type="application/ld+json">${JSON.stringify(obj).replace(/</g, '\\u003c')}</script>`;
const crumbs = (items) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: items.map(([name, item], i) => ({ '@type': 'ListItem', position: i + 1, name, item })),
});

// Index pages: title/description are constants (the same the page's own <SEO> sets),
// the body is the same list the page renders. Keys are pathnames with no trailing
// slash, except '/' itself. '/' has no title of its own: index.html's is right for it.
const STATIC_META = {
  '/': [null, 'TinBoker (聽播客) 結合 Podcast 觀點與即時數據，視覺化產業趨勢與專家分析，助您做出明智投資決策。'],
  '/podcaster': ['所有節目', 'TinBoker 持續結構化分析的中文財經 Podcast。'],
  '/stock': ['所有個股', '最近被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。'],
  '/topics': ['話題排行', '今日最強題材焦點 — 依題材聚合，顯示漲跌幅、資金流與相關個股表現。'],
  '/articles': ['文章', '深度分析與市場觀察 — TinBoker 的財經文章。'],
  '/about': ['關於 TinBoker', 'TinBoker（聽播客）— 結合 Podcast 觀點與即時數據的財經平台。'],
  '/contact': ['聯絡我們', '產品建議、合作想法或使用疑問 — 歡迎與 TinBoker 聯繫。'],
  '/disclaimer': ['免責聲明', 'TinBoker 免責聲明 — 所有資訊僅供參考與學習用途。'],
};

const INDEX_BODY = {
  '/': async (api, origin) => {
    const [rec, tr] = await Promise.all([
      getJson(`${api}/api/episodes/recent?limit=10`, CACHE_1H),
      getJson(`${api}/api/ticker-insights/trending?limit=20`, CACHE_1H),
    ]);
    const eps = (rec && rec.episodes) || [];
    return {
      body: `<h2>最新集數</h2>${ul(eps.map((e) => `${podcasterLink(e.podcast_name)} · ${episodeLink(e)}`))}`
        + `<h2>近 30 天熱門個股</h2>${ul((tr || []).map((r) => `${stockLink(r.ticker)} · ${r.count} 集 · ${sentimentZh(r.sentiment_label)}`))}`,
      ld: [
        { '@context': 'https://schema.org', '@type': 'WebSite', name: SITE, url: `${origin}/` },
        { '@context': 'https://schema.org', '@type': 'Organization', name: SITE, url: `${origin}/`, logo: BRAND_IMG },
      ],
    };
  },
  '/stock': async (api) => {
    const tr = await getJson(`${api}/api/ticker-insights/trending?limit=100`, CACHE_1H);
    return { body: ul((tr || []).map((r) => `${stockLink(r.ticker)} · ${r.count} 集 · ${sentimentZh(r.sentiment_label)}`)) };
  },
  '/podcaster': async (api) => {
    const pods = await getJson(`${api}/api/podcast`, CACHE_1H);
    return { body: ul((pods || []).map((p) => `${podcasterLink(p.name)} · ${p.episode_count} 集`)) };
  },
  '/topics': async (api) => {
    const s = await getJson(`${api}/api/sectors`, CACHE_1H);
    return { body: ul(((s && s.sectors) || []).map((x) => `${sectorLink(x)}：${esc(x.description || '')}`)) };
  },
};

const staticKey = (p) => (p === '/' ? '/' : p.replace(/\/$/, ''));

// A path is a candidate if it is a single-segment content route or an index page.
// Kept as one predicate so onRequest's cheap early-out and metaFor can never disagree
// about which paths are covered.
const CONTENT_ROUTE = /^\/(?:episode|article|stock|topics|tag|sector|podcaster)\/[^/]+\/?$/;
export function isCandidate(pathname) {
  return CONTENT_ROUTE.test(pathname) || staticKey(pathname) in STATIC_META;
}

// Resolves { title, description, image, type, url, body, ld } for a covered path.
// body is the inner HTML for #root (no H1 — renderPage adds the title), ld a list of
// schema.org objects. Both optional.
export async function metaFor(pathname, origin, api) {
  const key = staticKey(pathname);
  const stat = STATIC_META[key];
  if (stat) {
    const extra = INDEX_BODY[key] ? await INDEX_BODY[key](api, origin) : {};
    return {
      title: stat[0], description: stat[1], image: BRAND_IMG, type: 'website',
      url: `${origin}${key === '/' ? '/' : key}`,
      body: `<p>${esc(stat[1])}</p>${extra.body || ''}`,
      ld: extra.ld || [],
    };
  }

  let m = pathname.match(/^\/episode\/([^/]+)\/?$/);
  if (m) {
    const id = decodeURIComponent(m[1]);
    const r = await fetch(`${api}/api/episodes/${encodeURIComponent(id)}`);
    if (!r.ok) return null;
    const e = await r.json();
    // Mirror EpisodeDetail's title/name derivation exactly (episode_title field).
    const name = e.podcast_name || '節目';
    const title = e.episode_title || (e.episode_number != null ? `EP ${e.episode_number}` : '集數摘要');
    const url = `${origin}/episode/${encodeURIComponent(id)}`;
    const image = rasterImage(e.summary_image_public_url, (e.spotify_images && e.spotify_images[0]) || BRAND_IMG);
    const chs = chapters(e.summary_content);
    // Ticker names come from the sector baskets; the episode itself only carries symbols.
    const names = {};
    const sectors = new Map();
    for (const s of e.sector_exposures || []) {
      if (s.exposure_id) sectors.set(s.exposure_id, s);
      for (const t of s.resolved_tickers || []) if (t.ticker && t.name) names[t.ticker] = t.name;
    }
    const released = e.released_at_ms ? new Date(e.released_at_ms).toISOString() : null;
    // Mirrors the PodcastEpisode JSON-LD EpisodeDetail builds client-side.
    const ld = {
      '@context': 'https://schema.org',
      '@type': 'PodcastEpisode',
      name: title,
      url,
      image,
      partOfSeries: { '@type': 'PodcastSeries', name, url: `${origin}/podcaster/${encodeURIComponent(name)}` },
      ...(released ? { datePublished: released } : {}),
      ...(chs.length ? { hasPart: chs.map((c) => ({ '@type': 'Clip', name: c.title, startOffset: c.sec, url: `${url}#t-${c.sec}` })) } : {}),
    };
    const body = `<p>${podcasterLink(name)}${released ? ` · ${esc(day(released))}` : ''}</p>`
      + ((e.key_insights || []).length ? `<h2>重點</h2>${ul(e.key_insights.map(esc))}` : '')
      + (chs.length ? `<h2>章節</h2>${ul(chs.map((c) => `${hms(c.sec)} ${esc(c.title)}`))}` : '')
      + mdToHtml(e.summary_content)
      + ((e.related_tickers || []).length ? `<h2>相關個股</h2>${ul(e.related_tickers.map((t) => stockLink(t, names[t])))}` : '')
      + (sectors.size ? `<h2>產業 / 題材</h2>${ul([...sectors.values()].map(sectorLink))}` : '');
    return {
      title,
      description: `${name} · ${title} — 結構化摘要與重點。`,
      image,
      type: 'article',
      url,
      body,
      ld: [ld, crumbs([[name, `${origin}/podcaster/${encodeURIComponent(name)}`], [title, url]])],
    };
  }
  m = pathname.match(/^\/article\/([^/]+)\/?$/);
  if (m) {
    const slug = decodeURIComponent(m[1]);
    const r = await fetch(`${api}/api/articles/${encodeURIComponent(slug)}`);
    if (!r.ok) return null;
    const a_ = await r.json();
    const url = `${origin}/article/${encodeURIComponent(slug)}`;
    const image = rasterImage(a_.cover_image_url, BRAND_IMG);
    return {
      title: a_.title,
      description: a_.subtitle || (a_.key_points && a_.key_points[0]) || a_.title,
      image,
      type: 'article',
      url,
      body: (a_.subtitle ? `<p>${esc(a_.subtitle)}</p>` : '')
        + ((a_.key_points || []).length ? `<h2>重點</h2>${ul(a_.key_points.map(esc))}` : ''),
      ld: [{
        '@context': 'https://schema.org', '@type': 'Article', headline: a_.title, url, image,
        ...(a_.published_at ? { datePublished: a_.published_at } : {}),
        publisher: { '@type': 'Organization', name: SITE, logo: BRAND_IMG },
      }],
    };
  }
  m = pathname.match(/^\/stock\/([^/]+)\/?$/);
  if (m) {
    const sym = decodeURIComponent(m[1]);
    const enc = encodeURIComponent(sym);
    // by-ticker defaults to the last 7 days; ask for the 90 days the page itself
    // shows (StockDashboard), so the 30-day tally below counts the same rows.
    const iso = (d) => d.toISOString().slice(0, 10);
    const since = iso(new Date(Date.now() - 90 * 86400e3));
    const [ins, secs, basic] = await Promise.all([
      getJson(`${api}/api/ticker-insights/by-ticker/${enc}?start_date=${since}&end_date=${iso(new Date())}`),
      getJson(`${api}/api/sectors/by-ticker/${enc}`),
      getJson(`${api}/api/stocks/${enc}/basic`),
    ]);
    const name = basic && basic.name ? `${basic.name}（${sym}）` : sym;
    const url = `${origin}/stock/${enc}`;
    const insights = ins || [];
    const t = tally(insights);
    const latest = insights[0];
    // The description is the page's own numbers, so no two ticker pages read alike.
    const description = t.total && latest
      ? `${tallySentence(name, t)}最近：${latest.podcaster}（${day(latest.podcast_launch_time)}）${latest.bluf_thesis || ''}`.slice(0, 160)
      : `查看 ${name} 的即時股價走勢，以及最新提到此標的的 Podcast 摘要與分析。`;
    const members = (secs && secs.items) || [];
    const body = (insights.length ? `<p>${esc(tallySentence(name, t))}</p>` : '')
      + (members.length ? `<h2>產業 / 題材</h2>${ul(members.map((s) => `${sectorLink(s)}${s.reason ? `：${esc(s.reason)}` : ''}`))}` : '')
      + (insights.length ? `<h2>Podcast 觀點</h2>${ul(insights.map((i) =>
        `${esc(day(i.podcast_launch_time))} · ${podcasterLink(i.podcaster)} · ${esc(sentimentZh(i.sentiment_label))}`
        + `${i.time_horizon ? ` · ${esc(i.time_horizon)}` : ''} · ${a(`/episode/${encodeURIComponent(i.episode_id)}`, i.bluf_thesis || '')}`))}` : '');
    return {
      title: `${name} · 股價與相關 Podcast`,
      description,
      image: BRAND_IMG,
      type: 'website',
      url,
      body,
      ld: [crumbs([['所有個股', `${origin}/stock`], [name, url]])],
    };
  }
  // Both paths render TagPage (App.tsx), so both canonicalize to /topics/ — otherwise
  // the legacy /tag/ URL competes with its own twin in search.
  m = pathname.match(/^\/(?:topics|tag)\/([^/]+)\/?$/);
  if (m) {
    // Mirrors TagPage's <SEO title={`#${displayLabel}`} .../>.
    const raw = decodeURIComponent(m[1]).replace(/^#/, '');
    const label = await tagLabel(raw, api);
    return {
      title: `#${label}`,
      description: `所有關於「${label}」的 Podcast 摘要與市場討論。`,
      image: BRAND_IMG,
      type: 'website',
      url: `${origin}/topics/${encodeURIComponent(raw)}`,
    };
  }
  m = pathname.match(/^\/sector\/([^/]+)\/?$/);
  if (m) {
    // Header fields (display_name, description) come from the sector list, one small
    // cached document. by-sector adds the basket + episodes but a cold query costs
    // 20-50 s on the API (measured 2026-09-05), longer than a crawler waits — so it is
    // an enrichment with a deadline, never the thing the title depends on. The query
    // matches SectorPage's own call (getEpisodesBySector default) to share its cache key.
    const id = decodeURIComponent(m[1]);
    const [list, full] = await Promise.all([
      getJson(`${api}/api/sectors`, CACHE_1H),
      withTimeout(getJson(`${api}/api/episodes/by-sector/${encodeURIComponent(id)}?limit=50&offset=0`), 8000),
    ]);
    const s = full || ((list && list.sectors) || []).find((x) => x.exposure_id === id);
    if (!s) return null;
    const name = s.display_name || '產業 / 題材';
    const url = `${origin}/sector/${encodeURIComponent(id)}`;
    const desc = (s.description || '').trim();
    const body = (desc ? `<p>${esc(desc)}</p>` : '')
      + ((s.resolved_tickers || []).length ? `<h2>相關個股</h2>${ul(s.resolved_tickers.map((t) => `${stockLink(t.ticker, t.name)}${t.reason ? `：${esc(t.reason)}` : ''}`))}` : '')
      + ((s.episodes || []).length ? `<h2>相關集數</h2>${ul(s.episodes.slice(0, 10).map((e) => `${podcasterLink(e.podcast_name)} · ${episodeLink(e)}`))}` : '');
    return {
      title: name,
      // The sector description is the paragraph SectorPage renders under the H1 —
      // unique, ~100 zh-TW chars, far better than the generic template that was here.
      description: desc || `所有關於「${name}」產業 / 題材的 Podcast 摘要與市場討論。`,
      image: BRAND_IMG,
      type: 'website',
      url,
      body,
      ld: [crumbs([['話題排行', `${origin}/topics`], [name, url]])],
    };
  }
  m = pathname.match(/^\/podcaster\/([^/]+)\/?$/);
  if (m) {
    // Mirrors PodcasterPage's <SEO/>. The channel name is already in the path.
    const name = decodeURIComponent(m[1]);
    const url = `${origin}/podcaster/${m[1]}`;
    const [eps, ins] = await Promise.all([
      getJson(`${api}/api/podcast/${encodeURIComponent(name)}/episodes?limit=10`),
      getJson(`${api}/api/ticker-insights/by-podcaster/${encodeURIComponent(name)}?limit=50`),
    ]);
    const counts = {};
    for (const i of ins || []) if (i.ticker) counts[i.ticker] = (counts[i.ticker] || 0) + 1;
    const top = Object.entries(counts).sort((x, y) => y[1] - x[1]).slice(0, 10);
    const episodes = eps || [];
    const body = (episodes.length ? `<h2>最新集數</h2>${ul(episodes.map((e) => `${e.released_at_ms ? `${esc(day(new Date(e.released_at_ms).toISOString()))} · ` : ''}${episodeLink(e)}`))}` : '')
      + (top.length ? `<h2>最常提到的個股</h2>${ul(top.map(([t, n]) => `${stockLink(t)} · ${n} 次`))}` : '');
    return {
      title: `${name} · Podcast 頻道`,
      description: top.length
        ? `${name} 最新 ${episodes.length} 集結構化摘要，最常提到：${top.slice(0, 5).map(([t]) => t).join('、')}。`
        : `追蹤 ${name} 的最新 Podcast 摘要與相關個股分析。`,
      image: BRAND_IMG,
      type: 'website',
      url,
      body,
      ld: [
        { '@context': 'https://schema.org', '@type': 'PodcastSeries', name, url },
        crumbs([['所有節目', `${origin}/podcaster`], [name, url]]),
      ],
    };
  }
  return null;
}

// The HTML that replaces #root for crawlers: H1 (the page title), the route body, and
// the footer links. Exported so validate-crawler-meta.mjs can measure it.
export function renderPage(meta) {
  return `<main><h1>${esc(meta.title || SITE)}</h1>${meta.body || ''}${FOOTER}</main>`;
}

// Two reasons a response gets noindex.
//
// Host: dev./staging./<pr>.pages.dev serve the same pages as production with nothing
// stopping Google indexing them — three more copies of every URL competing with
// tinboker.com for the same queries.
//
// Route: NOINDEX_ROUTE, thin pages that should not be evaluated on any host.
//
// A header rather than a robots.txt Disallow in both cases, on purpose: a disallowed
// page can't be crawled, so the noindex would never be read and an already-indexed copy
// would just sit there. Applied last so the meta injection above still runs — that is
// how social-card previews keep working on dev, and why a shared /topics link still
// gets a proper card even though the page is not indexed.
export async function onRequest(context) {
  const url = new URL(context.request.url);
  const res = await handle(context, url);
  if (PROD_HOSTS.has(url.hostname) && !NOINDEX_ROUTE.test(url.pathname)) return res;
  try {
    // next()'s headers are immutable; re-wrap to get a mutable copy. Guarded because
    // some statuses (304 and friends) reject a re-wrap — a missing noindex on one
    // asset response is not worth 500-ing dev and staging over.
    const stamped = new Response(res.body, res);
    stamped.headers.set('X-Robots-Tag', 'noindex, nofollow');
    return stamped;
  } catch (_err) {
    return res;
  }
}

async function handle(context, url) {
  const { request, next, env } = context;
  try {
    // API origin: derived from the request host (prod), overridable via a Pages
    // env var (mirrors the frontend's VITE_API_BASE_URL; also used in local dev).
    const api = (env && env.API_ORIGIN) || apiBase(url.hostname);

    // The sitemap is generated by the API, but Search Console is pointed at the site
    // host — and without this the SPA fallback answered /sitemap.xml with index.html
    // (200 text/html), so a submission there silently indexes nothing. Proxy it so
    // both hosts serve the same XML.
    // `api !== url.origin` guards recursion: apiBase only rewrites *.tinboker.com and
    // returns any other host unchanged, so on a host it doesn't know the proxy would
    // fetch itself, re-enter this Function, and spin until the subrequest cap.
    if (url.pathname === '/sitemap.xml' && api !== url.origin) {
      const r = await fetch(`${api}/sitemap.xml`, CACHE_1H);
      if (!r.ok) return next();
      return new Response(r.body, {
        status: 200,
        headers: { 'content-type': 'application/xml', 'cache-control': 'public, max-age=3600' },
      });
    }

    // Only covered routes are candidates; everything else (assets, account pages)
    // passes straight through with just a cheap regex test.
    if (!isCandidate(url.pathname)) return next();
    const ua = request.headers.get('user-agent') || '';
    if (!CRAWLER.test(ua)) return next();

    const meta = await metaFor(url.pathname, url.origin, api);
    const res = await next();
    if (!meta) return res;
    if (!(res.headers.get('content-type') || '').includes('text/html')) return res;

    const full = meta.title ? `${meta.title} | ${SITE}` : SITE;
    const head = [
      `<title>${esc(full)}</title>`,
      `<meta name="description" content="${esc(meta.description)}">`,
      `<meta property="og:type" content="${esc(meta.type)}">`,
      `<meta property="og:site_name" content="${esc(SITE)}">`,
      `<meta property="og:title" content="${esc(full)}">`,
      `<meta property="og:description" content="${esc(meta.description)}">`,
      `<meta property="og:image" content="${esc(meta.image)}">`,
      `<meta property="og:url" content="${esc(meta.url)}">`,
      `<meta name="twitter:card" content="summary_large_image">`,
      `<meta name="twitter:title" content="${esc(full)}">`,
      `<meta name="twitter:description" content="${esc(meta.description)}">`,
      `<meta name="twitter:image" content="${esc(meta.image)}">`,
      `<link rel="canonical" href="${esc(meta.url)}">`,
      ...(meta.ld || []).map(ldScript),
    ].join('');
    const body = renderPage(meta);

    // Strip the static placeholders so crawlers see exactly one of each tag,
    // then append the per-route block to <head> and fill #root.
    return new HTMLRewriter()
      .on('title', { element: (el) => el.remove() })
      .on('meta[name="description"]', { element: (el) => el.remove() })
      .on('meta[property^="og:"]', { element: (el) => el.remove() })
      .on('meta[name^="twitter:"]', { element: (el) => el.remove() })
      .on('head', { element: (el) => el.append(head, { html: true }) })
      .on('#root', { element: (el) => el.setInnerContent(body, { html: true }) })
      .transform(res);
  } catch (_err) {
    // Meta injection must never break a page — fall back to the untouched SPA.
    return next();
  }
}
