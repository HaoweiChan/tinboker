// Cloudflare Pages Function — per-route social meta for crawlers (Phase 3 SEO).
//
// Non-JS crawlers (LINE, Threads, Facebook, Twitter/X, Slack, Discord, ...) never
// run the SPA's React, so a shared content link shows the generic homepage card.
// This middleware detects crawlers on content routes, fetches the page's real data
// from the platform API, and rewrites <head> with accurate OG / Twitter / title tags.
//
// Humans pass straight through (no edge fetch, no change) — React + react-helmet
// already set their meta client-side. The injected meta mirrors the client <SEO>
// output, so it is the same information the rendered page shows (not cloaking).
// Every path is wrapped so any failure falls back to the unmodified SPA: this
// middleware can never break a page.

const CRAWLER = /bot|crawl|spider|facebookexternalhit|facebot|twitterbot|\bline\b|slackbot|whatsapp|telegrambot|discordbot|pinterest|linkedinbot|redditbot|embedly|quora|skypeuripreview|applebot|googlebot|bingbot|baiduspider|yandex|duckduckbot/i;

const BRAND_IMG = 'https://tinboker.com/brand/tinboker-square-dark-1080.png';
const SITE = '聽播客 TinBoker';

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

async function metaFor(pathname, origin, api) {
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
  return null;
}

export async function onRequest(context) {
  const { request, next, env } = context;
  try {
    const url = new URL(request.url);
    // Only content routes are candidates; everything else (assets, home, lists)
    // passes straight through with just a cheap regex test.
    if (!/^\/(episode|article|stock)\//.test(url.pathname)) return next();
    const ua = request.headers.get('user-agent') || '';
    if (!CRAWLER.test(ua)) return next();

    // API origin: derived from the request host (prod), overridable via a Pages
    // env var (mirrors the frontend's VITE_API_BASE_URL; also used in local dev).
    const api = (env && env.API_ORIGIN) || apiBase(url.hostname);
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
