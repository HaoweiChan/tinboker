# Articles platform plan — TinBoker as a blogging surface

Status: **Phase 1 implemented; MCP authoring implemented; image upload deferred** · Owner: @hwchan42 · Created 2026-06-05 · Updated 2026-06-06

Plan for turning TinBoker into a publishing platform: rich, embed-enriched articles
authored first by the admin (you), eventually by any registered user, with the
authoring toolkit exposed as **MCP tools** so an agent can write articles end-to-end.

This doc is the north star. Each phase is independently shippable through the normal
`develop → dev → main → staging → tag → prod` pipeline ([deploy-flow](workflows/deploy-flow.md)).

---

## 1. Locked decisions

These were decided up front; the rest of the plan assumes them.

| Decision | Choice | Why |
|---|---|---|
| **Body format** | **Markdown + embed directives** | Reuses the existing `SummaryMarkdown` renderer and the `[label](#ticker:X)` / `#tag:X` marker grammar; agents emit plain text, so it is the most MCP-friendly format. |
| **Phase-1 authoring** | **MCP-first + a simple admin markdown editor** | Leads with the agent-writes-articles vision; defers a heavy WYSIWYG build. |
| **Image serving** | **Public GCS prefix + Cloudflare CDN** | A public blog needs no per-request signing; immutable content-hashed URLs cache forever at the edge. |
| **v1 embeds** | **Ticker citations, tag/topic chips, images** | Tickers + tags already render for free via the marker grammar; images are the one net-new piece. **Stock charts + knowledge-graph embeds are deferred to Phase 3.** |

### Constraints inherited from the codebase (non-negotiable)

1. **No new Firestore-direct reads.** Reads are consolidating behind VPS Postgres + the upcoming HTTP API ([firestore-data-change](workflows/firestore-data-change.md)). Articles are platform-owned user-generated content → they live in **Postgres/SQLite + GCS**, never in Firestore.
2. **Stay out of the agents contract.** [`docs/firestore-contract.md`](firestore-contract.md) governs the `episodes`/`tickers`/`tags` collections written by `tinboker-agents`. Articles must not enter those collections or that contract.
3. **`use_postgres` portability.** Any new table must work on both SQLite (dev) and Postgres (prod) — use the SQLAlchemy `Base` path in [`backend/src/database/postgres.py`](../backend/src/database/postgres.py), not raw SQL.
4. **Reuse the marker grammar; never enable raw HTML.** Inline citations use `[label](#ticker:SYMBOL)` / `[label](#tag:ID)`. Block embeds use a closed allowlist of directives. `rehype-raw` stays **off** so no HTML sanitizer is ever required — even for untrusted multi-author content.
5. **zh-TW + no emoji** in all author-facing UI (`frontend/AGENTS.md`); icons are lucide-react / SVG only.

---

## 2. Target architecture

### 2.1 Storage model

Three tiers, mirroring how episodes already work (DB row + GCS body + cached blob):

```
Postgres/SQLite  articles            ← metadata, status, denormalized author byline, tags[], tickers[]
                 article_tags        ← inverted index (tag → article) for discovery
                 article_tickers     ← inverted index (ticker → article)
GCS              graphfolio-articles/articles/img/{hash}.webp ← uploaded images (public-read) [Phase 0]
Redis            articles:{slug}, articles:list:*             ← cache_get → cache_set, like episodes
```

> **Phase 1 note:** body is stored inline in `articles.body_content` (TEXT column) for MVP
> simplicity. GCS offloading (`body_url` pointer + lazy fetch) is a future optimisation for
> very long articles. The `body_url` column is omitted from the initial schema.

Model the slice on the **`news`** vertical end-to-end — it is the closest existing
precedent (DB entity + content text field + `news_tickers` join + Redis cache + CRUD):
[`models/news.py`](../backend/src/models/news.py), [`database/news_db.py`](../backend/src/database/news_db.py),
[`services/news.py`](../backend/src/services/news.py), [`routers/news.py`](../backend/src/routers/news.py).
Use the SQLAlchemy ORM path (like `stock_translations`), not raw SQL.

**`articles` columns (as implemented):**

| Column | Type | Notes |
|---|---|---|
| `id` | int (autoincrement) | internal PK |
| `slug` | str(255), unique | public URL is `/article/{slug}`; auto-generated from title with collision suffix |
| `title` | text | |
| `subtitle` | text? | optional deck |
| `author_id` | str(255) | user ID or email |
| `author_name` | str(255) | **denormalized** so reads need no user lookup |
| `author_avatar` | text? | denormalized avatar URL |
| `status` | str(20) | `draft \| pending_review \| published \| archived` |
| `cover_image_url` | text? | public CDN URL |
| `body_content` | text | inline markdown body (GCS offloading deferred) |
| `key_points` | json (str[]) | optional plain-text takeaways, analogous to `episodes.key_insights` |
| `tags` | json (str[]) | lowercase, free-form; merged with body-extracted `#tag:` markers |
| `tickers` | json (str[]) | symbols cited; merged with body-extracted `#ticker:` markers |
| `published_at`, `created_at`, `updated_at` | datetime | |
| `read_minutes` | int | CJK-aware estimate (~400 chars/min) |
| `view_count` | int | incremented on each public slug fetch |

### 2.2 Body format spec

Markdown (`remark-gfm`), rendered by react-markdown. Three embed mechanisms:

**Inline entity citations — already render today, zero new work:**
```markdown
[輝達](#ticker:NVDA) leads in [AI 晶片](#tag:ai-chips).
```
Resolved by the custom `a` renderer in [`SummaryMarkdown.tsx`](../frontend/src/components/episode/SummaryMarkdown.tsx)
(`#ticker:` → `/stock/{symbol}`, `#tag:` → `/topics/{id}`) and `MentionText` in
[`InlineMarkers.tsx`](../frontend/src/components/episode/InlineMarkers.tsx). The backend
already extracts `[..](#tag:ID)` markers in [`episode_transformer.py`](../backend/src/services/episode_transformer.py) —
reuse the same regex to populate `articles.tags` / `articles.tickers` server-side.

**Images (Phase 1) — standard markdown image + new `img` renderer:**
```markdown
![財報重點摘要](https://cdn.tinboker.com/articles/img/{hash}.webp "Q3 data-center revenue")
```
Needs a new `img`/`figure` renderer (none exists in `SummaryMarkdown` today) — responsive,
`loading="lazy"`, optional caption from title text, `onError` fallback following the
[`PodcastAvatar`](../frontend/src/components/common/PodcastAvatar.tsx) convention.

**Block embeds (Phase 3) — `remark-directive`, closed allowlist:**
```markdown
:::chart{ticker=NVDA timeframe=1Y indicators=MA20,Volume}
:::

:::graph{id=semis-supply-chain}
:::

:::callout{type=insight}
Data-center revenue up 200% YoY.
:::
```
Adds the `remark-directive` plugin and one renderer per allowed directive. `chart` wraps
the existing [`TradingViewChart`](../frontend/src/components/charts/TradingViewChart.tsx)
fed by `GET /api/stocks/{ticker}?timeframe=...`; `graph` wraps
[`ForceGraph`](../frontend/src/components/graph/visuals/ForceGraph.tsx) with `isWidget`.
Unknown directives degrade to nothing (no raw markdown leaks).

### 2.3 Rendering

Create a dedicated **`ArticleBody.tsx`** rather than overloading `SummaryMarkdown`
(articles add an `img` renderer + directives + an untrusted-author posture episodes don't have).
Extract the shared `a`-renderer marker logic into a small module
(`frontend/src/components/markdown/markers.ts`) imported by both so the two stay aligned.

Article page (`/article/{slug}`, **new route** — none exists today) uses the
[`PageContent`](../frontend/src/components/layout/PageContent.tsx) shell with the optional
`xl+` right rail for a table-of-contents / cited-ticker list, mirroring
[`EpisodeDetail.tsx`](../frontend/src/pages/EpisodeDetail.tsx). Article cards reuse the flat
[`EpisodeCardV2`](../frontend/src/components/redesign/EpisodeCardV2.tsx) aesthetic (not the
legacy gradient `TopStoryCard`). Design tokens: CSS variables in
[`frontend/src/index.css`](../frontend/src/index.css) (Tailwind v4).

### 2.4 Auth & roles

Extend the **service-token pattern**, do not invent a new one.

- **MCP write auth:** add `TINBOKER_ARTICLE_TOKEN` to [`config.py`](../backend/src/config.py)
  (mirroring `tinboker_write_token`) and a `get_article_author_access()` dependency modeled
  on `get_translation_access` in [`admin_auth.py`](../backend/src/auth/admin_auth.py) — accepts
  an admin JWT **or** the bearer service token (constant-time `secrets.compare_digest`),
  scoped to article endpoints only. Do **not** reuse the dev-bypass token (non-prod only) or
  widen `get_admin_access`.
- **MCP byline:** service-token writes can use `TINBOKER_ARTICLE_AUTHOR_ID`,
  `TINBOKER_ARTICLE_AUTHOR_NAME`, and `TINBOKER_ARTICLE_AUTHOR_AVATAR` so drafts created by
  an agent still publish under the admin author's byline.
- **Phase 1 (admin-only):** you are the sole allowlisted `ADMIN_EMAILS` author. No role table yet.
- **Phase 4 (multi-author):** add `role: reader | author | admin` to Firestore `users/{id}`
  ([`models/user.py`](../backend/src/models/user.py)), an `articles.status` moderation flow, and
  per-author API keys (hash on the user doc) so the token both authenticates and identifies the
  author — eliminating the "pass author_id explicitly" trust gap.

> Doc-drift note found during research: [`docs/agents/auth-admin.md`](agents/auth-admin.md)
> describes a password-based admin login (`ADMIN_PASSWORD` / `/api/admin/auth/login`) that
> **does not exist in code** — admin auth is Google-JWT + `ADMIN_EMAILS` only. Fix that doc
> opportunistically; do not build against the described flow.

### 2.5 MCP authoring server

Clone [`mcp-servers/stock-translations/`](../mcp-servers/stock-translations/server.py) into
`mcp-servers/article-authoring/`: FastMCP over stdio, a thin httpx wrapper over the public
`/api/articles/*` + admin endpoints (**no DB/GCS credentials in the MCP**), read tools open,
write tools gated on `TINBOKER_ARTICLE_TOKEN`. Register a sibling entry in
[`.mcp.json`](../.mcp.json). Changes under `mcp-servers/**` are outside the deploy path filter,
so the MCP runs client-side and needs no VPS change.

Tool surface (the "insert" tools return ready-to-paste marker/directive strings so the agent
assembles the body, keeping the MCP thin):

| Tool | Kind | Returns / does |
|---|---|---|
| `search_tickers(query)` | read | resolve a name to `SYMBOL` (reuse the translations API) |
| `cite_ticker(query)` | read | validates + returns `[display](#ticker:SYMBOL)` |
| `suggest_tags(text)` | read | existing tags matching the draft |
| `add_tag(name)` | read | returns `[name](#tag:slug)` and the slug |
| `upload_image(source_url_or_base64, alt)` | write | backend fetches/decodes → GCS → returns public CDN URL + `![alt](url)` snippet |
| `insert_chart(ticker, timeframe, indicators?)` | read | returns `:::chart{...}` directive (Phase 3) |
| `insert_graph(graph_id)` | read | returns `:::graph{...}` directive (Phase 3) |
| `create_draft(title, body_markdown, tags?, cover_image_url?)` | write | POST → returns `article_id` + admin preview URL |
| `update_draft(article_id, ...)` | write | PATCH |
| `list_my_drafts()` / `get_article(id)` | read | for iteration |
| `publish(article_id)` | write | flips `status → published` (or `pending_review` for non-admins in Phase 4) |

### 2.6 Discoverability

- **Search:** add a `type:"article"` source block to `build_search_index()`
  ([`routers/search.py`](../backend/src/routers/search.py)) and an `article_service.search_articles()`
  for the live `/api/search` path. Include the **full zh-TW title** as a keyword (Chinese
  matching is prefix-only). BUG-1 is already fixed (index builds in `main.py` lifespan).
- **Tags:** maintain an `article_tags` inverted index; teach [`TagPage.tsx`](../frontend/src/pages/TagPage.tsx)
  (currently episode-only) to also fetch + render tagged articles. Optionally widen the
  `Tag` schema so the [topics cloud](../frontend/src/pages/TopicsCloud.tsx) counts articles too.
- **Trending:** reuse the click-analytics sorted-set pattern — `POST /api/analytics/click {type:"article", id}`
  on article view, then `get_trending_articles()` reading `analytics:clicks:article`, surfaced via the
  existing `/api/search/popular` endpoint.

---

## 3. Phased roadmap

### Phase 0 — Foundations & cleanup (prereqs, ~small)

Resolve the infra ambiguities that would otherwise block image upload:

- [ ] **Standardize the bucket name.** Real bucket is `graphfolio-articles`; docs/scripts say
  `tinboker-articles` ([`backend/docs/features/content-api-gcs.md`](../backend/docs/features/content-api-gcs.md),
  [`frontend/scripts/cors.json`](../frontend/scripts/cors.json)). Pick `graphfolio-articles` everywhere.
- [ ] **Wire `CONTENT_BUCKET`** (currently unset in all envs → the `/api/content` router 500s) into
  per-service env in [`docker-compose.multi.yml`](../backend/docker-compose.multi.yml); add `CONTENT_CDN_BASE`.
- [ ] Decide the public image prefix + CDN hostname (e.g. `cdn.tinboker.com` via Cloudflare → GCS),
  set the prefix public-read, confirm bucket CORS allows the real frontend origins (not just `*.vercel.app`).
- [ ] Extend [`gcs_content.upload_content()`](../backend/src/services/gcs_content.py) to accept `bytes`
  + arbitrary `content_type` (today it takes `str`).

**Acceptance:** a manual `upload_content()` of a test image yields a public, edge-cacheable URL.

### Phase 1 — Admin-only MVP + MCP authoring (the core)

Everything needed for *you* to publish embed-rich articles, by hand and via an agent.

> **Implementation status:** Phase 1 core shipped in `feat/articles-platform` (2026-06-06).
> Image upload and MCP server deferred — see notes below.

**Backend**
- [x] `articles` + `article_tags` + `article_tickers` tables (SQLAlchemy, dual-dialect) in
  [`database/models.py`](../backend/src/database/models.py); Pydantic schemas in
  [`models/article.py`](../backend/src/models/article.py); service in
  [`services/article_service.py`](../backend/src/services/article_service.py).
- [x] [`routers/articles.py`](../backend/src/routers/articles.py) (public, unauthenticated
  GET: list + `/{slug}`) registered in [`main.py`](../backend/src/main.py); CDN cached via
  `@cdn_cached(profile=CacheProfile.NEWS)`, Redis `cache_get/cache_set` with `articles:*` keys.
- [x] [`routers/admin_articles.py`](../backend/src/routers/admin_articles.py)
  (write: create/update/publish/delete) behind `get_article_author_access`;
  `tinboker_article_token` in [`config.py`](../backend/src/config.py),
  `get_article_author_access()` in [`admin_auth.py`](../backend/src/auth/admin_auth.py).
- [ ] Image upload endpoint — **deferred** (blocked on Phase 0: CDN hostname + GCS wiring).
  Articles can reference external image URLs in markdown; the `img`/`figure` renderer handles
  them. The dedicated upload endpoint ships with Phase 0 completion.
- [x] Server-side marker extraction to populate `tags`/`tickers` from the body — reuses the
  `episode_transformer` regex pattern (`_TAG_RE`, `_TICKER_RE` in `article_service.py`).

**Frontend**
- [x] [`ArticleBody.tsx`](../frontend/src/components/article/ArticleBody.tsx) — dedicated
  renderer with `img`/`figure` (responsive, lazy-loading, caption from title text, `onError`
  fallback), `#ticker:`/`#tag:` link renderers, tables, code blocks, blockquotes.
  `rehype-raw` stays off. Marker logic inlined (shared `markers.ts` extraction deferred to
  when `SummaryMarkdown` diverges enough to warrant it).
- [x] [`/article/{slug}`](../frontend/src/pages/ArticleDetail.tsx) page on `PageContent` shell
  with right rail (tags, tickers, key points); [`/articles`](../frontend/src/pages/ArticleList.tsx)
  list page with card grid; `ArticleCard` component reusing `EpisodeCardV2` aesthetic.
  Routes added in [`App.tsx`](../frontend/src/App.tsx).
- [x] Admin [`/admin/articles`](../frontend/src/pages/AdminArticlesPage.tsx): markdown textarea
  + **live `ArticleBody` preview** + title/subtitle/slug/cover/tags/tickers/key-points fields
  + draft/publish workflow. Added to [`AdminSidebar`](../frontend/src/components/admin/AdminSidebar.tsx)
  + `App.tsx` admin routes. Zod schemas (`ArticleSchema`, `ArticleListItemSchema`) in
  [`schemas.ts`](../frontend/src/validation/schemas.ts). API service in
  [`articleService.ts`](../frontend/src/services/articleService.ts).

**MCP**
- [x] `mcp-servers/article-authoring/` — FastMCP stdio wrapper over the HTTP API. Tools cover
  ticker/tag snippets, external-image markdown, draft create/update/list/read, and publish.
  Registered in [`.mcp.json`](../.mcp.json). Write tools require `TINBOKER_ARTICLE_TOKEN`.
- [ ] `upload_image` — **deferred** with the backend upload endpoint (blocked on Phase 0 CDN/GCS
  wiring). Current MCP exposes `image_markdown()` for existing public image URLs.

**Acceptance:** (1) ~~you write an article in the admin editor with a ticker citation, a tag, and an
uploaded image~~ **Partially met:** admin editor creates articles with ticker citations and tags
that render correctly at `/article/{slug}` with clickable links. Image upload deferred (external
image URLs work via standard markdown `![alt](url)` syntax). (2) MCP can create/update/publish
drafts when configured with the article token.

### Phase 2 — Discoverability

- [ ] Articles in the search index (`type:"article"`) + live `/api/search`.
- [ ] `TagPage` renders tagged articles alongside episodes; `article_tags` index powers it.
- [ ] `get_trending_articles()` via click analytics; surfaced in `/api/search/popular` and/or a
  home rail.
- [ ] Optional: articles appear in relevant home sections; topics-cloud counts include articles.

**Acceptance:** an article is findable by title in search, appears on its tag's `/topics/{tag}`
page, and can trend after views.

### Phase 3 — Rich embeds: stock charts + knowledge graphs

- [ ] Add `remark-directive`; implement `:::chart{ticker timeframe indicators}` → `TradingViewChart`
  (theme-aware; fetch via `getStockByTicker`) and `:::graph{id}` → `ForceGraph isWidget`.
  Lazy-load these heavy widgets so they don't bloat the PWA precache.
- [ ] `insert_chart` / `insert_graph` MCP tools emit the directives.
- [ ] **Fix BUG-5** ([`frontend/src/validation/schemas.ts`](../frontend/src/validation/schemas.ts):
  `marketCapTier`/`ticker` required) before feeding article data through the graph schema —
  make the fields optional at the schema, not via a silent fallback.
- [ ] Verify chart/graph embeds respect dark mode and have explicit mobile heights + pointer handling.

**Acceptance:** an article renders a live, interactive price chart and a knowledge-graph widget
inline, in both light and dark mode, on desktop and mobile.

### Phase 4 — Multi-author publishing

- [ ] `role` field on `users/{id}`; `get_author_access()` grants write if `role ∈ {author, admin}`.
- [ ] `articles.status` moderation flow + an admin **approval queue** (`pending_review → published`)
  reusing the `/admin` shell (no moderation surface exists today).
- [ ] Author profiles (bio, byline, avatar, author slug) on the user doc; public author page
  listing their articles; profile UI in [`ProfilePage`](../frontend/src/pages/ProfilePage.tsx) /
  [`SettingsPage`](../frontend/src/pages/SettingsPage.tsx).
- [ ] Per-author MCP API keys (hashed on the user doc) replacing the single shared token.
- [ ] Comments on articles: generalize the `comments` table from `(podcast_name, episode_id)` to a
  polymorphic `(target_type, target_id)` (or add nullable `article_id`) —
  [`database/comment_db.py`](../backend/src/database/comment_db.py).

**Acceptance:** a non-admin registered user is granted author, drafts via their own API key,
submits for review, and an admin approves it to publish.

### Phase 5 — Polish

- [ ] SEO: per-article meta/OG tags, sitemap, structured data.
- [ ] RSS / Atom feed.
- [ ] Author/article analytics dashboard; publish → notification fan-out
  ([`notification_service.py`](../backend/src/services/notification_service.py)).
- [ ] Scheduled publishing; revision history; related-articles (tag/ticker overlap).

---

## 4. Cross-cutting concerns

- **Security.** Never enable `rehype-raw`; markdown-only + a closed directive allowlist means no
  HTML sanitizer is required even for untrusted authors. Validate image upload type/size; rate-limit
  write endpoints. Per-author keys are hashed at rest.
- **PWA caching** ([`vite.config.ts`](../frontend/vite.config.ts)): images are `CacheFirst`
  (30-day) — **content-hash image filenames** so edits get a new URL. API responses are
  `NetworkFirst` and the cache regex is hardcoded to `api.tinboker.com` (prod only), so dev/staging
  are unaffected. Invalidate Redis **and** Cloudflare on article edit.
- **i18n / icons.** All author-facing UI in zh-TW; lucide-react/SVG icons only, never emoji.
- **Testing.** Backend: pytest for the article service/router + marker extraction (no
  `continue-on-error` — BUG-4). Frontend: `npm run build` + lint; render `ArticleBody` against a
  fixture exercising every embed type.
- **Field lockstep.** Any new field must change the backend model + serializer + the frontend Zod
  schema/type together (the documented episode/comment drift pitfall).

---

## 5. Open questions / risks

1. **CDN hostname** — confirm `cdn.tinboker.com` (or reuse an existing host) and the Cloudflare→GCS
   wiring before Phase 1 image work. **Still open — blocks image upload endpoint.**
2. ~~**Slug strategy**~~ — **Resolved:** auto-generated from title via `slugify` (ascii
   transliteration); collisions get a `-{timestamp}` suffix. Admin editor shows the slug and
   allows manual override before publish.
3. ~~**Draft storage**~~ — **Resolved:** same `articles` table with `status=draft` (as recommended).
4. **MCP image upload ergonomics** — still open; deferred with MCP server.
5. **Graph embeds depend on real graph data** — `GraphGallery` is currently mock-fed and BUG-5 is
   open; Phase 3 must wire real `createGraph`/`getGraphById` data.

---

## 6. Key file touchpoints (reference)

### Implemented in Phase 1

| Area | File |
|---|---|
| Article ORM models | [`backend/src/database/models.py`](../backend/src/database/models.py) (`Article`, `ArticleTag`, `ArticleTicker`) |
| Article Pydantic schemas | [`backend/src/models/article.py`](../backend/src/models/article.py) |
| Article service (CRUD, markers, cache) | [`backend/src/services/article_service.py`](../backend/src/services/article_service.py) |
| Public article router | [`backend/src/routers/articles.py`](../backend/src/routers/articles.py) |
| Admin article router | [`backend/src/routers/admin_articles.py`](../backend/src/routers/admin_articles.py) |
| Article auth dependency | [`backend/src/auth/admin_auth.py`](../backend/src/auth/admin_auth.py) (`get_article_author_access`) |
| Article config token | [`backend/src/config.py`](../backend/src/config.py) (`tinboker_article_token`) |
| Cache TTLs | [`backend/src/cache/cache_config.py`](../backend/src/cache/cache_config.py) (`article_item`, `article_list`) |
| Article body renderer | [`frontend/src/components/article/ArticleBody.tsx`](../frontend/src/components/article/ArticleBody.tsx) |
| Article detail page | [`frontend/src/pages/ArticleDetail.tsx`](../frontend/src/pages/ArticleDetail.tsx) |
| Article list page | [`frontend/src/pages/ArticleList.tsx`](../frontend/src/pages/ArticleList.tsx) |
| Admin articles editor | [`frontend/src/pages/AdminArticlesPage.tsx`](../frontend/src/pages/AdminArticlesPage.tsx) |
| Article API service | [`frontend/src/services/articleService.ts`](../frontend/src/services/articleService.ts) |
| Article Zod schemas | [`frontend/src/validation/schemas.ts`](../frontend/src/validation/schemas.ts) (`ArticleSchema`, `ArticleListItemSchema`) |

### Existing files extended

| Area | File | Change |
|---|---|---|
| Router registration | [`backend/src/main.py`](../backend/src/main.py) | Added `articles_router`, `admin_articles_router` |
| App routing | [`frontend/src/App.tsx`](../frontend/src/App.tsx) | Added `/articles`, `/article/:slug`, admin `/articles` routes |
| Admin sidebar | [`frontend/src/components/admin/AdminSidebar.tsx`](../frontend/src/components/admin/AdminSidebar.tsx) | Added "Articles" nav item |

### Reference files (for future phases)

| Area | Follow / extend |
|---|---|
| News slice (original template) | `backend/src/{models,database,services,routers}/news.*` |
| GCS upload primitive | [`backend/src/services/gcs_content.py`](../backend/src/services/gcs_content.py) |
| Marker extraction (original) | [`backend/src/services/episode_transformer.py`](../backend/src/services/episode_transformer.py) |
| Body renderer (episode) | [`frontend/src/components/episode/SummaryMarkdown.tsx`](../frontend/src/components/episode/SummaryMarkdown.tsx) |
| Chart / graph embeds (Phase 3) | [`frontend/src/components/charts/TradingViewChart.tsx`](../frontend/src/components/charts/TradingViewChart.tsx), [`frontend/src/components/graph/visuals/ForceGraph.tsx`](../frontend/src/components/graph/visuals/ForceGraph.tsx) |
| Search indexing | [`backend/src/routers/search.py`](../backend/src/routers/search.py), [`backend/src/services/suggestion_index.py`](../backend/src/services/suggestion_index.py) |
| Tag pages | [`frontend/src/pages/TagPage.tsx`](../frontend/src/pages/TagPage.tsx), [`frontend/src/pages/TopicsCloud.tsx`](../frontend/src/pages/TopicsCloud.tsx) |
| MCP server template | [`mcp-servers/stock-translations/server.py`](../mcp-servers/stock-translations/server.py), [`.mcp.json`](../.mcp.json) |
