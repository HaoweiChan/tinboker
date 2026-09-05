# SEO data-presentation plan — make the data we already have visible to crawlers, then chart it

> Written 2026-09-05 from a read-only audit of production (`curl -A Googlebot` per route
> family, the live sitemap, public API payloads, and row counts on the VPS Postgres).
> Companion to [social-seo.md](social-seo.md) (sitemap + Search Console plumbing) and the
> memory of the August fix (PR #548: duplicate titles, missing sector pages).
> Tracked as TKB-010 … TKB-013 in `TODO.md`.

## 1. Diagnosis

The bottleneck is not missing data. It is that **crawlers see almost none of it**, and a
large part of what is in Postgres has no page at all.

| Measured 2026-09-05 | Value | Why it matters |
|---|---|---|
| Sitemap URLs | episode 296 · stock 101 · sector 79 · podcaster 10 · topics 1 · static 5 | fewer than 500 indexable pages |
| Distinct tickers mentioned inside the 60-day public window | 514 | only 100 of them have a `/stock/:ticker` page in the sitemap |
| Crawler-visible body text per page | ~600 chars, all script residue | every page fetches in `useEffect`; a non-JS crawler gets an empty shell |
| JSON-LD emitted at the edge | 0 blocks | `PodcastEpisode` / `Article` exist only client-side via react-helmet, after hydration |
| `/topics/:tag` pages | ~166, all `noindex` | the largest content surface is excluded wholesale |
| `content_mentions`, `ticker_performance_snapshots`, `sector_performance_snapshots` | 0 rows | the public `/api/tickers/{t}/mentions` endpoint returns `[]` for every ticker (TKB-001 is not populating prod) |
| `stock_daily_ohlc` | 2,199 tickers, 2026-03-13 → today | full daily OHLC + trading value; only used for the price line on `/stock/:ticker` |
| `stock_institutional_daily` | 2,089 tickers, 2026-06-05 → today | 三大法人 net buy/sell; internal-key only, never shown |
| `ticker_insights` per episode | `bluf_thesis`, `sentiment_label`, `time_horizon`, `reasons[]` with timestamps | our most differentiated data; appears only as prose on the episode page |
| `/api/sectors/board` | per-member 12-point sparkline, heat, hotness, avg_change | public, used only on `/topics` |

Other findings, all verified in code:

- `/stock/:ticker` and `/podcaster/:id` crawler descriptions are templates
  (`frontend/functions/_middleware.js:159-170,206-218`) — identical shape on every page,
  which Google treats as near-duplicate.
- `/` gets no crawler-specific meta (`_middleware.js:100`).
- `/articles`, `/contact`, `/disclaimer` have no inbound links from navigation
  (`frontend/src/components/layout/Sidebar.tsx:56-57`).
- Sector pages are the one family with a real per-page description reaching crawlers
  (`_middleware.js:186-205`); they are the template the other families should copy.

Verification rule (from the August lesson): test each **route family** with a crawler
UA and count body characters + `application/ld+json` blocks, then compare to the sitemap
count. "It renders in the browser" is not evidence.

```bash
curl -s -A Googlebot https://tinboker.com/stock/2330 \
  | sed 's/<script[^>]*>.*<\/script>//g; s/<[^>]*>//g' | tr -s ' \n' | wc -c
curl -s -A Googlebot https://tinboker.com/stock/2330 | grep -c 'application/ld+json'
```

## 2. Strategy — fix structure first, then add charts

### P0 · Let crawlers see the data (TKB-010)

One file: `frontend/functions/_middleware.js`. It already fetches the entity to build the
title; render the same payload as real HTML inside `#root` (React replaces it on mount)
and emit JSON-LD in the same pass.

| Route | Crawler-visible block | JSON-LD |
|---|---|---|
| `/episode/:id` | key_insights, chapter list, related tickers as `<a href="/stock/…">` | `PodcastEpisode` + `Clip` per chapter, `BreadcrumbList` |
| `/stock/:ticker` | last N `bluf_thesis` lines with podcaster + date, 30/90-day bullish/neutral/bearish tally, sector links | `BreadcrumbList`; description becomes live: "近 30 天 12 集提及，8 看多 3 中立 1 看空，最近：財經一路發" |
| `/sector/:id` | existing thesis + member tickers as links | `BreadcrumbList` |
| `/podcaster/:id` | latest episodes, top-10 mentioned tickers as links | `PodcastSeries`, `BreadcrumbList` |
| `/` | "本週熱門個股" static block, proper title/description | `Organization`, `WebSite` |

Target: 2–4k characters of unique text per page. This also solves internal linking:
episode → stock → sector → stock, podcaster → stock.

Widen the indexable surface in the same PR:

- Sitemap `/stock` family: from "top 100 trending" to "every ticker mentioned by ≥2
  episodes inside the release window" (`backend/src/routers/seo.py:160-166`). Roughly
  100 → 300 pages; the threshold keeps thin pages out.
- Add `/articles` to the sidebar; `/contact` and `/disclaimer` to the footer.
- Extend `scripts/validate-crawler-meta.mjs` to assert a minimum body length and ≥1
  JSON-LD block for every dynamic family.

### P1 · Charts on the pages that exist (TKB-011, TKB-012)

Ranked by SEO value × implementation cost. The first three need no new pipeline.

1. **Price × podcast-mention overlay** (`/stock/:ticker`, the signature chart). Daily
   candles with a marker at every episode mention, coloured by sentiment; hover shows
   `bluf_thesis` and podcaster. Data: `/api/stocks/{t}` chartData +
   `/api/ticker-insights/by-ticker/{t}`. Implement with `lightweight-charts` series
   markers — the library is already installed. Nobody else has this chart; it is the
   thing that gets screenshotted and linked.
2. **Sentiment split + time-horizon split** (`/stock/:ticker`, `/podcaster/:id`).
   Stacked bar or donut of bullish / neutral / bearish episode counts over 30 / 90 days,
   plus 短 / 中 / 長期 distribution. Derived from the same payload; the numbers also feed
   the crawler-visible sentence in P0.
3. **Sector heat vs return** (`/sector/:id`). `/topics` already has
   `HeatReturnValidation`; render the single-sector version on each sector page next to
   the existing member sparkline strip. Data: `/api/sectors/board`.
4. **三大法人 net buy/sell bars** (`/stock/:ticker`). Data is in
   `stock_institutional_daily` (3 months deep). Needs a public read path — fold it into
   `/api/stocks/{ticker}/history` or add `/api/stocks/{ticker}/institutional`. "外資買超
   + 股名" is one of the highest-volume long-tail queries in the TW market.
5. **Podcaster stock preferences** (`/podcaster/:id`). Top-10 tickers and sector-mix
   donut from `/api/ticker-insights/by-podcaster/{name}`. Turns the 10 podcaster pages
   from lists into analysis.
6. **Co-mention network** (`/sector/:id` or `/stock/:ticker`). `related_tickers`
   averages 13 tickers per episode; 300 episodes are enough for a graph.
   `frontend/src/components/graph/visuals/ForceGraph.tsx` exists but its route was
   retired. Low SEO value (canvas), high share value — last.

Blocked, not skipped: **post-mention N-day return** is the most differentiated chart, but
its tables are empty in production. It ships as soon as TKB-001 populates them.

### P2 · New page types (TKB-013)

- `/weekly/YYYY-Www` rollup: episode count, top tickers, sentiment shifts, sector heat.
  Dated URLs carry freshness signals, and the content is the same payload the
  Threads / vocus / Substack syndication already composes.
- `/topics/:tag`: stop the blanket `noindex`. Index tags that have a description and ≥5
  episodes in the window; keep `noindex` on the rest. Re-check AdSense "low value
  content" risk after 2 weeks in Search Console before widening further.

## 3. Order of work

| Week | Deliverable | Evidence of done |
|---|---|---|
| 1 | TKB-010: middleware HTML block + JSON-LD + live descriptions, sitemap ≥2-mention tickers, orphan links, validator extended | `curl -A Googlebot` on one URL per family: body ≥2,000 chars, ≥1 `ld+json`; sitemap stock count ≥250; `npm run validate:seo` green in CI |
| 2 | TKB-011: charts 1 + 2 on `/stock/:ticker`, tally sentence in crawler block | screenshot per chart on dev; `npm run build && npm run lint` green |
| 3 | TKB-012: institutional endpoint + chart 4, chart 3 on sector pages, chart 5 on podcaster pages | endpoint returns rows for 2330 on staging; screenshots |
| later | TKB-013: weekly page, selective tag indexing, co-mention graph; post-mention returns once TKB-001 lands | Search Console impressions for `/weekly/*` and `/topics/*` after 14 days |

Do not merge anything here without the crawler-UA check on production after deploy.
The August regression was invisible in the browser.
