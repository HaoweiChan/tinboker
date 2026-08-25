// Cloudflare Pages Function — per-route social meta for crawlers (Phase 3 SEO).
//
// Non-JS crawlers (LINE, Threads, Facebook, Twitter/X, Slack, Discord, ...) never
// run the SPA's React, so a shared content link shows the generic homepage card.
// This middleware detects crawlers on content routes, fetches the page's real data
// from the platform API, and rewrites <head> with accurate OG / Twitter / title tags.
// Covered: /episode, /article, /stock, /topics (+ legacy /tag), /sector, /podcaster,
// and the index pages listed in STATIC_META. Anything left out serves index.html's
// generic title to Googlebot, i.e. N pages that look like exact duplicates of each
// other and mostly never get indexed — which is what /topics (166 URLs), /sector (81)
// and /podcaster (10) were all doing before they were added here.
//
// Humans pass straight through (no edge fetch, no change) — React + react-helmet
// already set their meta client-side. The injected meta mirrors the client <SEO>
// output, so it is the same information the rendered page shows (not cloaking).
// Every path is wrapped so any failure falls back to the unmodified SPA: this
// middleware can never break a page.

const CRAWLER = /bot|crawl|spider|mediapartners|facebookexternalhit|facebot|twitterbot|\bline\b|slackbot|whatsapp|telegrambot|discordbot|pinterest|linkedinbot|redditbot|embedly|quora|skypeuripreview|applebot|googlebot|bingbot|baiduspider|yandex|duckduckbot/i;

const BRAND_IMG = 'https://tinboker.com/brand/tinboker-square-dark-1080.png';
const CACHE_1H = { cf: { cacheTtl: 3600, cacheEverything: true } };
const SITE = '聽播客 TinBoker';
// Only these serve indexable content; every other host this code runs on (dev.,
// staging., <pr>.pages.dev) is a copy of it.
const PROD_HOSTS = new Set(['tinboker.com', 'www.tinboker.com']);

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

// Attribute/text-safe escaping for values injected into the HTML head.
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

// Index pages: no API call, no per-request data — just the same title/description the
// page's own <SEO> sets client-side. Keys are pathnames with no trailing slash.
// '/' is absent on purpose: index.html's static tags are already correct for it.
const STATIC_META = {
  '/podcaster': ['所有節目', 'TinBoker 持續結構化分析的中文財經 Podcast。'],
  '/stock': ['所有個股', '最近被 TinBoker 追蹤的 Podcast 提及的所有個股，依提及次數排序。'],
  '/topics': ['話題排行', '今日最強題材焦點 — 依題材聚合，顯示漲跌幅、資金流與相關個股表現。'],
  '/articles': ['文章', '深度分析與市場觀察 — TinBoker 的財經文章。'],
  '/about': ['關於 TinBoker', 'TinBoker（聽播客）— 結合 Podcast 觀點與即時數據的財經平台。'],
  '/contact': ['聯絡我們', '產品建議、合作想法或使用疑問 — 歡迎與 TinBoker 聯繫。'],
  '/disclaimer': ['免責聲明', 'TinBoker 免責聲明 — 所有資訊僅供參考與學習用途。'],
};

// A path is a candidate if it is a single-segment content route or an index page.
// Kept as one predicate so onRequest's cheap early-out and metaFor can never disagree
// about which paths are covered.
const CONTENT_ROUTE = /^\/(?:episode|article|stock|topics|tag|sector|podcaster)\/[^/]+\/?$/;
export function isCandidate(pathname) {
  return CONTENT_ROUTE.test(pathname) || pathname.replace(/\/$/, '') in STATIC_META;
}

export async function metaFor(pathname, origin, api) {
  const stat = STATIC_META[pathname.replace(/\/$/, '')];
  if (stat) {
    return {
      title: stat[0], description: stat[1], image: BRAND_IMG, type: 'website',
      url: `${origin}${pathname.replace(/\/$/, '')}`,
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
    return {
      title,
      description: `${name} · ${title} — 結構化摘要與重點。`,
      image: rasterImage(e.summary_image_public_url, (e.spotify_images && e.spotify_images[0]) || BRAND_IMG),
      type: 'article',
      url: `${origin}/episode/${encodeURIComponent(id)}`,
    };
  }
  m = pathname.match(/^\/article\/([^/]+)\/?$/);
  if (m) {
    const slug = decodeURIComponent(m[1]);
    const r = await fetch(`${api}/api/articles/${encodeURIComponent(slug)}`);
    if (!r.ok) return null;
    const a = await r.json();
    return {
      title: a.title,
      description: a.subtitle || (a.key_points && a.key_points[0]) || a.title,
      image: rasterImage(a.cover_image_url, BRAND_IMG),
      type: 'article',
      url: `${origin}/article/${encodeURIComponent(slug)}`,
    };
  }
  m = pathname.match(/^\/stock\/([^/]+)\/?$/);
  if (m) {
    // The ticker alone is enough — mirrors the client <SEO> on StockDashboard.
    const sym = decodeURIComponent(m[1]);
    return {
      title: `${sym} · 股價與相關 Podcast`,
      description: `查看 ${sym} 的即時股價走勢，以及最新提到此標的的 Podcast 摘要與分析。`,
      image: BRAND_IMG,
      type: 'website',
      url: `${origin}/stock/${encodeURIComponent(sym)}`,
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
    // by-sector carries display_name + description in the same payload the page uses,
    // so one request covers both. limit=1 because only the header fields are needed.
    const id = decodeURIComponent(m[1]);
    const r = await fetch(`${api}/api/episodes/by-sector/${encodeURIComponent(id)}?limit=1`);
    if (!r.ok) return null;
    const s = await r.json();
    const name = s.display_name || '產業 / 題材';
    return {
      title: name,
      // The sector description is the paragraph SectorPage renders under the H1 —
      // unique, ~100 zh-TW chars, far better than the generic template that was here.
      description: (s.description || '').trim()
        || `所有關於「${name}」產業 / 題材的 Podcast 摘要與市場討論。`,
      image: BRAND_IMG,
      type: 'website',
      url: `${origin}/sector/${encodeURIComponent(id)}`,
    };
  }
  m = pathname.match(/^\/podcaster\/([^/]+)\/?$/);
  if (m) {
    // Mirrors PodcasterPage's <SEO/>. The channel name is already in the path, so
    // this route needs no API call at all.
    const name = decodeURIComponent(m[1]);
    return {
      title: `${name} · Podcast 頻道`,
      description: `追蹤 ${name} 的最新 Podcast 摘要與相關個股分析。`,
      image: BRAND_IMG,
      type: 'website',
      url: `${origin}/podcaster/${m[1]}`,
    };
  }
  return null;
}

// dev./staging./<pr>.pages.dev serve the same pages as production with nothing stopping
// Google indexing them — three more copies of every URL competing with tinboker.com for
// the same queries. Stamped as a header rather than a robots.txt Disallow on purpose: a
// disallowed page can't be crawled, so the noindex would never be read and an
// already-indexed copy would just sit there. Applied last so the meta injection above
// still runs on those hosts — that is how the social-card previews get tested.
export async function onRequest(context) {
  const url = new URL(context.request.url);
  const res = await handle(context, url);
  if (PROD_HOSTS.has(url.hostname)) return res;
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

    // Only covered routes are candidates; everything else (assets, the home page,
    // account pages) passes straight through with just a cheap regex test.
    if (!isCandidate(url.pathname)) return next();
    const ua = request.headers.get('user-agent') || '';
    if (!CRAWLER.test(ua)) return next();

    const meta = await metaFor(url.pathname, url.origin, api);
    const res = await next();
    if (!meta) return res;
    if (!(res.headers.get('content-type') || '').includes('text/html')) return res;

    const full = `${meta.title} | ${SITE}`;
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
    ].join('');

    // Strip the static placeholders so crawlers see exactly one of each tag,
    // then append the per-route block to <head>.
    return new HTMLRewriter()
      .on('title', { element: (el) => el.remove() })
      .on('meta[name="description"]', { element: (el) => el.remove() })
      .on('meta[property^="og:"]', { element: (el) => el.remove() })
      .on('meta[name^="twitter:"]', { element: (el) => el.remove() })
      .on('head', { element: (el) => el.append(head, { html: true }) })
      .transform(res);
  } catch (_err) {
    // Meta injection must never break a page — fall back to the untouched SPA.
    return next();
  }
}
