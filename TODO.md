# Tinboker TODO

Last updated: 2026-09-05

## North Star

Tinboker turns podcast content into stock and sector intelligence.

The current product direction is:

1. Build proprietary content intelligence from podcast transcripts and summaries.
2. Convert that intelligence into Threads-native discovery content.
3. Bring users back to tinboker.com through ticker pages, sector pages, episode pages, and newsletter pages.
4. Use AI agents later as a premium analysis layer, not as the first product surface.

## Source of Truth Rule

This file is the single source of truth for Tinboker product and engineering tasks.

GitHub Issues and GitHub Projects are derived mirrors. Do not treat them as the authoritative roadmap.

When task status, priority, scope, or acceptance criteria change, update this file first.

## Priority Rules

Each task should be ranked by:

- Impact: Does this improve the core user experience or business outcome?
- Distribution: Does this create traffic, sharing, SEO, or retention?
- Moat: Does this accumulate Tinboker-specific data?
- Urgency: Is there a timing advantage to shipping this soon?
- Effort: How much engineering work is required?
- Risk: Are there platform, legal, data quality, infra, or UX risks?

Suggested scoring:

```text
score = 2*Impact + 2*Distribution + Moat + Urgency - Effort - Risk
```

## Status Values

Use only these status values:

```text
idea
ready
in_progress
blocked
review
done
wont_do
```

Meaning:

- idea: Interesting, but not ready for implementation.
- ready: Scope is clear enough for an agent or engineer to implement.
- in_progress: Currently being implemented.
- blocked: Waiting on data, access, API, design, or product decision.
- review: PR or implementation exists and needs review.
- done: Merged, deployed, or intentionally completed.
- wont_do: Explicitly decided not to do.

## Priority Values

Use only these priority values:

```text
P0
P1
P2
icebox
```

Meaning:

- P0: Current focus. Do before other work unless there is a production incident.
- P1: Next stage. Important, but not blocking the current loop.
- P2: Valuable, but only after P0/P1.
- icebox: Keep for reference, but do not implement yet.

## Roadmap Order

## P0: Content intelligence loop

1. TKB-001 Podcast ticker / sector performance tracking
2. TKB-008 Wiki graph intelligence layer
3. TKB-002 Threads draft queue for episode summaries and market topics
4. TKB-003 Newsletter web edition

## P1: Discovery and distribution

5. TKB-010 SEO: crawler-visible content, JSON-LD, wider stock sitemap
6. TKB-011 Stock page charts: price × mention overlay, sentiment split
7. TKB-012 Institutional-flow chart, sector and podcaster charts
8. TKB-013 Weekly rollup pages, selective tag indexing, co-mention graph
9. TKB-004 Threads topic discovery and clustering
10. TKB-005 Ticker / sector discussion pages

## P2: AI analysis layer

11. TKB-006 TradingAgents Lite
12. TKB-007 Full TradingAgents-style multi-agent report

---

# Active Tasks

## TKB-001 Podcast ticker / sector performance tracking

```yaml
id: TKB-001
status: in_progress
priority: P0
area:
- pipelines
- backend
- frontend
type: feature
effort: L
risk: medium
github_issue: https://github.com/HaoweiChan/tinboker/issues/405
github_project_item: PVTI_lAHOAP_gz84BcROAzgxhes4
pr: https://github.com/HaoweiChan/tinboker/compare/develop...feat/ticker-mention-performance
```

### Goal

Track ticker and sector mentions from podcast episodes and calculate later market performance.

Tinboker should be able to answer questions like:

- Which stocks were mentioned by podcasts recently?
- Which sectors are being discussed more often?
- What happened 1D / 5D / 20D / 60D after a ticker was mentioned?
- Which podcast episodes mentioned a ticker before a move?

### Why now

This is Tinboker's core proprietary data asset.

It can power:

- ticker pages
- sector pages
- episode pages
- Threads posts
- newsletter issues
- TradingAgents Lite reports
- SEO landing pages

### Acceptance criteria

- [x] Extract ticker / company / sector mentions from episode transcripts and summaries.
- [x] Store mentions in PostgreSQL.
- [x] Store source episode, timestamp if available, confidence score, and extraction method.
- [x] Support TW stocks and US stocks.
- [x] Calculate 1D / 5D / 20D / 60D return after mention date.
- [x] Expose backend API for ticker mentions and sector mentions.
- [x] Show mention performance on ticker and/or sector pages.
- [x] Include disclaimer that podcast mentions are not investment recommendations.
- [x] Add basic tests for extraction and API output.
- [x] Add migration script for new database tables.

### Suggested implementation

#### pipelines/

- Add entity extraction job for ticker / company / sector mentions.
- Use transcript, episode title, show name, and existing summaries as input.
- Normalize ticker aliases and company names.
- Add confidence score and extraction reason.

#### backend/

Potential endpoints:

```text
GET /api/tickers/{ticker}/mentions
GET /api/sectors/{sector}/mentions
GET /api/episodes/{episode_id}/mentions
```

Potential tables:

```text
content_mentions
ticker_performance_snapshots
sector_performance_snapshots
```

#### frontend/

Potential surfaces:

- ticker detail page
- sector detail page
- episode page mention block
- homepage discovery module

### Risks

- Ticker ambiguity, especially Chinese company names and concept stocks.
- Sector taxonomy may drift between TW and US markets.
- Mention does not mean recommendation.
- Need to avoid misleading users with cherry-picked performance.

### Implementation notes

Start simple. First version can be daily batch only.

Do not build real-time tracking yet.

**2026-07-03 (branch `feat/ticker-mention-performance`):** Implemented daily-batch only, per the note above.

- Mentions are *derived*, not re-extracted: the pipelines already extract per-episode ticker insights (LLM) and sector exposures (alias matching), so a backend sync job (`backend/src/services/mention_sync.py`, every 6h) folds both into a new `content_mentions` table, stamping `extraction_method` (`pipeline_llm` / `alias_match`) and `confidence` (0.9 for LLM rows until the extractor emits per-row scores; the exposures' own score otherwise). Sources: the pipeline-written Postgres `ticker_insights` table + the existing projected episode scan (no new Firestore read paths).
- 1D/5D/20D/60D are **trading-day** windows computed from `stock_daily_closes` into `ticker_performance_snapshots` / `sector_performance_snapshots` (sector = equal-weight average of resolved members). Windows stay NULL until elapsed; recompute stops ~130 days post-mention. Coverage is bounded by the close-warmer's tracked set (~400 tickers).
- API: `GET /api/tickers/{ticker}/mentions`, `/api/sectors/{exposure_id}/mentions`, `/api/episodes/{episode_id}/mentions` — every response carries a zh-TW non-investment-advice `disclaimer`.
- UI: ticker page 「播客提及後續表現」 section, episode rail 「提及後續表現」 block, `/picks` inline disclaimer → `/disclaimer`. Return chips use the user's stock color convention.
- Migration: `backend/src/database/migrations/add_mention_tables.py` (also auto-created on startup). Tests: `backend/tests/unit/test_mention_sync.py`, `test_mentions_api.py`.

---

## TKB-008 Wiki graph intelligence layer

```yaml
id: TKB-008
status: ready
priority: P0
area:
- pipelines
- backend
type: feature
effort: L
risk: medium
github_issue: https://github.com/HaoweiChan/tinboker/issues/412
github_project_item: PVTI_lAHOAP_gz84BcROAzgxjq8g
pr: null
```

### Goal

Turn the existing wiki Postgres store into a first-class knowledge graph intelligence layer.

Tinboker already has persistent wiki pages and `wiki_links` edges. This task ports the useful
Graphify ideas into that live wiki model: community detection, centrality scoring, confidence-tagged
edges, and a nightly graph snapshot that agents and product surfaces can use without scanning every
episode.

### Why now

This is part of Tinboker's core content moat.

The existing docs already conclude that Graphify should not be used as a runtime dependency for the
wiki. Instead, Tinboker should port Graphify's graph analytics patterns onto `wiki_pages` and
`wiki_links`.

References:

- `pipelines/docs/wiki-retrieval-strategy.md`
- `pipelines/docs/wiki-schema.md`
- `pipelines/docs/content-api-roadmap.md`

### Acceptance criteria

- [ ] Add schema support for graph analytics output, such as `wiki_communities`,
      `wiki_graph_snapshots`, or equivalent Postgres/GCS-backed storage.
- [ ] Add confidence metadata to wiki graph edges, distinguishing `EXTRACTED`, `INFERRED`, and
      `AMBIGUOUS` relationships with a confidence score.
- [ ] Build an entity co-mention graph from `wiki_links`.
- [ ] Run community detection over entity/topic relationships and persist community assignments.
- [ ] Compute centrality scores such as PageRank or weighted degree for entities and topics.
- [ ] Generate a nightly `wiki_graph_snapshot` containing communities, central nodes, notable
      relationships, and one-line entity/topic summaries.
- [ ] Expose read APIs for graph snapshot, communities, and top entities.
- [ ] Keep Graphify itself out of the request path; port the algorithmic pattern, not the tool.
- [ ] Add tests for graph construction, persistence, and API output.
- [ ] Update `pipelines/docs/wiki-schema.md` and `pipelines/docs/wiki-retrieval-strategy.md` with
      the implemented data contract.

### Suggested implementation

#### pipelines/

- Add a graph analytics module under `shared.wiki_builder`.
- Build weighted co-mention edges from episode-to-entity and episode-to-topic links.
- Start with deterministic graph analytics before LLM-generated hyperedges.
- Run the graph job nightly or after content batch ingest.
- Use `wiki_pages.updated_at` as the change-detection primitive, similar to Graphify's manifest.

Potential tables:

```text
wiki_communities
wiki_graph_snapshots
wiki_graph_metrics
```

Potential dependency options:

```text
networkx
python-igraph
leidenalg
```

#### backend / API

Potential endpoints:

```text
GET /api/wiki/graph-snapshot
GET /api/wiki/communities
GET /api/wiki/communities/{id}
GET /api/wiki/entities/top?metric=pagerank&limit=20
```

### Risks

- Community names can become misleading if generated too early or without review.
- Inferred relationships must not pollute strict ticker/entity matching.
- Graph jobs can become expensive if every run scans the whole wiki.
- New graph fields must stay compatible with the existing `/api/wiki` consumers.

### Implementation notes

Do not resurrect the old retired `services/knowledge_graph` service as-is.

Do not run Graphify against the live wiki at request time.

First version should ship deterministic communities, centrality, and snapshot output. Defer
LLM-generated hyperedges until the deterministic graph is stable.

---

## TKB-002 Threads draft queue for episode summaries and market topics

```yaml
id: TKB-002
status: ready
priority: P0
area:
- pipelines
- backend
- frontend
type: feature
effort: M
risk: medium
github_issue: https://github.com/HaoweiChan/tinboker/issues/406
github_project_item: PVTI_lAHOAP_gz84BcROAzgxheus
pr: null
```

### Goal

Generate Threads-native post drafts from new podcast episodes, ticker mentions, sector trends, and market topics.

First version should be semi-automatic: generate drafts, then require manual review before publishing.

### Why now

Threads is currently a strong discovery channel for Taiwanese stock discussion.

Tinboker needs a repeatable distribution loop:

```text
podcast intelligence -> short Threads content -> tinboker.com -> newsletter / returning users
```

### Acceptance criteria

- [ ] Generate Threads draft for new episode summary.
- [ ] Generate Threads draft for ticker / sector mention insight.
- [ ] Generate Threads draft for notable performance after podcast mention.
- [ ] Store generated drafts in backend.
- [ ] Admin UI can list, edit, approve, reject, and mark as posted.
- [ ] Each draft stores source episode / ticker / sector references.
- [ ] Each draft has a tracking URL back to tinboker.com.
- [ ] Use a less polished, more conversational tone suitable for Threads.
- [ ] Do not publish automatically in the first version.

### Suggested implementation

#### pipelines/

- Add post draft generation job.
- Input sources:
  - new episode summaries
  - top ticker mentions
  - top sector mentions
  - notable price moves
- Output to backend `post_drafts`.

#### backend/

Potential endpoints:

```text
GET /api/admin/post-drafts
POST /api/admin/post-drafts
PATCH /api/admin/post-drafts/{id}
POST /api/admin/post-drafts/{id}/approve
POST /api/admin/post-drafts/{id}/reject
POST /api/admin/post-drafts/{id}/mark-posted
```

Potential table:

```text
post_drafts
```

Fields:

```text
id
platform
status
title
body
source_type
source_refs
tracking_url
created_at
updated_at
approved_at
posted_at
```

#### frontend/

Add internal admin page:

```text
/admin/post-drafts
```

### Risks

- Content may sound too AI-generated.
- Fully automated posting may create platform or brand risk.
- Threads API access and behavior may change.
- Need clear source attribution and no misleading investment language.

### Implementation notes

Do not implement automatic publishing first.

The first version should optimize for:

- fast review
- easy editing
- repeatable daily workflow
- source traceability

---

## TKB-003 Newsletter web edition

```yaml
id: TKB-003
status: ready
priority: P0
area:
- backend
- frontend
- pipelines
type: feature
effort: M
risk: low
github_issue: https://github.com/HaoweiChan/tinboker/issues/407
github_project_item: PVTI_lAHOAP_gz84BcROAzgxhewg
pr: null
```

### Goal

Publish a weekly Tinboker investment intelligence newsletter as a web page first.

Email delivery can come later.

### Why now

Threads traffic should not stay only on Threads.

Newsletter web pages create:

- owned audience
- SEO pages
- reusable content
- weekly recap format
- conversion target from Threads posts

### Acceptance criteria

- [ ] Create newsletter issue model.
- [ ] Generate weekly issue draft from podcast mentions, sector trends, and episode highlights.
- [ ] Publish web version at `/newsletter/{slug}`.
- [ ] Add newsletter index page.
- [ ] Include email signup component.
- [ ] Generate Threads teaser draft after newsletter publish.
- [ ] Add SEO metadata for newsletter pages.
- [ ] Add basic Open Graph image support or fallback.
- [ ] Add clear disclaimer.

### Suggested implementation

#### pipelines/

- Weekly digest generator.
- Inputs:
  - top ticker mentions
  - top sectors
  - notable episodes
  - notable post-mention performance
  - editorial notes

#### backend/

Potential endpoints:

```text
GET /api/newsletter/issues
GET /api/newsletter/issues/{slug}
POST /api/admin/newsletter/issues
PATCH /api/admin/newsletter/issues/{id}
POST /api/admin/newsletter/issues/{id}/publish
```

Potential table:

```text
newsletter_issues
```

#### frontend/

Potential pages:

```text
/newsletter
/newsletter/{slug}
```

### Risks

- Content quality may be inconsistent.
- Email sending infrastructure can distract from core MVP.
- Avoid building a full ESP too early.

### Implementation notes

First version should be web-only.

Use manual publish.

Email capture is enough for first iteration.

---

## TKB-004 Threads topic discovery and clustering

```yaml
id: TKB-004
status: idea
priority: P1
area:
- pipelines
- backend
type: feature
effort: L
risk: high
github_issue: https://github.com/HaoweiChan/tinboker/issues/408
github_project_item: PVTI_lAHOAP_gz84BcROAzgxheyM
pr: null
```

### Goal

Discover investment topics from Threads or curated social sources, then cluster them into ticker / sector / theme groups.

### Why later

This can greatly improve discovery, but it has higher platform and data risk.

Start with manually curated sources before large-scale scraping.

### Acceptance criteria

- [ ] Support curated source accounts or keywords.
- [ ] Cluster posts into ticker / sector / theme groups.
- [ ] Generate daily topic digest.
- [ ] Link each topic to source references.
- [ ] Do not copy full original posts into Tinboker output.
- [ ] Support transformation into Threads draft ideas.
- [ ] Add source and compliance notes.

### Risks

- Threads access limitations.
- Scraping risk.
- Noisy topic clustering.
- Meme content may pollute ticker discussions.
- Need moderation and content quality control.

### Implementation notes

Start with curated watchlist, not open-ended crawling.

---

## TKB-005 Ticker / sector discussion pages

```yaml
id: TKB-005
status: idea
priority: P1
area:
- frontend
- backend
type: feature
effort: L
risk: medium
github_issue: https://github.com/HaoweiChan/tinboker/issues/409
github_project_item: PVTI_lAHOAP_gz84BcROAzgxhe08
pr: null
```

### Goal

Create lightweight discussion spaces around tickers and sectors.

The discussion format should support both serious analysis and meme-style participation.

### Why later

Discussion pages need traffic first.

If launched too early, they may look empty.

### Acceptance criteria

- [ ] Add discussion tab to ticker pages.
- [ ] Add discussion tab to sector pages.
- [ ] Support comments.
- [ ] Support reactions.
- [ ] Support source links from podcast episodes or newsletter sections.
- [ ] Add moderation controls.
- [ ] Add spam protection.
- [ ] Avoid real-time chat in first version.

### Risks

- Empty community problem.
- Moderation cost.
- Investment advice and misinformation risk.
- Spam and low-quality posts.

### Implementation notes

Do not build Discord-like chat first.

Start with lightweight comment threads.

---

## TKB-006 TradingAgents Lite

```yaml
id: TKB-006
status: idea
priority: P2
area:
- backend
- pipelines
- frontend
type: feature
effort: L
risk: high
github_issue: https://github.com/HaoweiChan/tinboker/issues/410
github_project_item: PVTI_lAHOAP_gz84BcROAzgxhe10
pr: null
```

### Goal

Build a Tinboker-specific AI stock analysis report using multiple specialist agents.

This should be explanation-first, not trading-advice-first.

### Why later

TradingAgents is attractive, but it should sit on top of Tinboker's own content intelligence layer.

Without podcast mentions, sector tracking, and performance data, it becomes a generic stock chatbot.

### First-version agent roles

- Podcast Analyst: How podcasts discussed this company or sector.
- Market Data Analyst: Recent price and performance context.
- Sector Analyst: Related sector and peer context.
- Sentiment Analyst: Social and news summary, if available.
- Risk Analyst: Bear case, uncertainty, and counterarguments.
- Editor Agent: Final report structure and tone.

### Acceptance criteria

- [ ] User can input ticker.
- [ ] Report includes podcast mention context.
- [ ] Report includes recent market performance.
- [ ] Report includes sector context.
- [ ] Report includes bull case.
- [ ] Report includes bear case.
- [ ] Report includes risks and uncertainty.
- [ ] Report includes source links.
- [ ] Report includes disclaimer.
- [ ] Report does not output buy / sell / target price in first version.

### Risks

- Generic output if Tinboker-specific data is weak.
- Hallucinated financial claims.
- Regulatory and compliance risk.
- Cost and latency from multi-agent orchestration.

### Implementation notes

Do not build trading execution, portfolio manager, or automated recommendations in first version.

---

## TKB-007 Full TradingAgents-style multi-agent report

```yaml
id: TKB-007
status: idea
priority: P2
area:
- backend
- pipelines
type: feature
effort: XL
risk: high
github_issue: https://github.com/HaoweiChan/tinboker/issues/411
github_project_item: PVTI_lAHOAP_gz84BcROAzgxhe38
pr: null
```

### Goal

Build a richer TradingAgents-style multi-agent research flow with debate, critique, risk control, and final investment report.

### Why later

This is expensive and complex.

It should only be implemented after Tinboker has:

- strong ticker / sector intelligence
- reliable source citation
- returning users
- evidence that people want deeper AI reports

### Acceptance criteria

- [ ] Multiple analyst agents.
- [ ] Bull / bear debate.
- [ ] Risk review.
- [ ] Report editor.
- [ ] Source-grounded output.
- [ ] Cost and latency monitoring.
- [ ] Cache repeated ticker reports.
- [ ] Human-readable trace.
- [ ] No trading execution.

### Risks

- High LLM cost.
- Slow response time.
- Hard-to-debug agent behavior.
- Potentially misleading financial output.

### Implementation notes

This is not MVP.

Do not implement before TKB-001, TKB-002, and TKB-003 are shipped.

---

## TKB-009 Sector curation, per-sector member reasons, stock-page membership

```yaml
id: TKB-009
status: done
priority: P1
area:
- pipelines
- backend
- frontend
type: feature
effort: L
risk: medium
github_issue: null
github_project_item: null
pr: https://github.com/HaoweiChan/tinboker/pull/432
```

### Goal

Structurally fix the sector/industry grouping: TinBoker-owned curation layer over the
tide-tw-data input (exclude/include/merge/reclassify overlay + machine-checked policy),
purge the ~30 audited far-fetched memberships (2330-in-HBM class), merge the 4 redundant
`jp_*` sectors with URL redirects, rebuild industries as roll-ups of their themes, fill
the 73%-empty per-(ticker, sector) reasons with sector-specific text, show each stock's
memberships (with reasons) on the stock page, and replace the dead weekly refresh chain
with an audit+fill maintenance workflow.

### Plan

Full milestone plan (M0–M5, one PR each, in order):
`docs/fix-plans/2026-07-06-sector-curation-and-reasons.md` (v2, structural).
Evidence base: `docs/fix-plans/2026-07-06-sector-universe-audit.md` (full 103-sector
audit) and `docs/fix-plans/2026-07-06-grouping-logic-spec.md` (every generation rule,
file:line). Read the plan before writing any code.

### Acceptance criteria

- [x] M0: dead weekly cron disabled; tag_registry drift inventoried (PR #433/#434).
- [x] M1: curation engine + POL validators + redirects + authoritative sync (PR #435).
- [x] M2: content pass — 21 purges, jp_* merges, HBM rebuild, roll-ups, enforcement, follows migration (PR #436).
- [x] M2.5 (v3): Postgres becomes source of truth — audit trigger table, taxonomy changelog, validate-on-write admin API (draft→publish), one-time import, sync/seed demoted to bootstrap, reasons served from registry, private GCS export. See plan §1 governance rules G1–G6.
- [x] M3 (v3): LLM fill of ~1,870 reasons + ~94 descriptions via the bulk draft API; Willy reviews the dry-run report before publish; zero-empty enforced at write path afterward.
- [x] M4: `GET /api/sectors/by-ticker/{ticker}` + 「所屬產業與題材」 card on StockDashboard (Zod-validated); reasons from registry.
- [x] M5: monthly audit+fill as drafts from a PRIVATE context (no public-repo PRs); dead Chain-B files deleted.

### Risks

- Merges/renames touch follows, which are SERVER-SIDE and keyed by DISPLAY NAME (SectorPage.tsx:198 → /api/user/subscriptions/tags/{name}/toggle) — M2.6 migration is mandatory or users silently lose subscriptions.
- Membership changes only reach existing episodes after a manual `backfill_sector_exposures.py --commit` run.
- `sync_sectors` never overwrites non-empty tag_registry members until M1.5 ships — a plain redeploy does NOT propagate seed fixes.
- v3 (Postgres-as-truth) is a deliberate IP decision: this repo is PUBLIC and the curated taxonomy/reasons are proprietary — nothing taxonomy-shaped gets committed to git anymore (the pre-v3 snapshot in git history is an accepted loss). `generate_sector_reasons.py` and the Chain-B scripts are dead code — never run them.
- Industry roll-ups (POL-1) visibly change /topics industry cards (member counts grow ~7x for semiconductor); flagged as D4 for Willy.
- Audit Part-2 judgments are INFERRED market calls — every purge/merge beyond the pre-approved defaults goes through Willy's line-by-line review in M2.2.

---

## TKB-010 SEO: crawler-visible content, JSON-LD, wider stock sitemap

```yaml
id: TKB-010
status: review
priority: P0
area:
- frontend
- backend
- seo
type: feature
effort: M
risk: low
github_issue: null
github_project_item: null
pr: https://github.com/HaoweiChan/tinboker/pull/591
```

### Goal

Every public data page currently serves an empty body and zero JSON-LD to crawlers (verified 2026-09-05: ~600 chars of script residue per page). Render the entity the middleware already fetches as real HTML inside `#root` plus schema.org JSON-LD, make stock descriptions live, and index every ticker mentioned by at least 2 episodes in the release window.

Plan and evidence: `docs/seo-data-presentation-plan.md`.

### Acceptance criteria

- [ ] `curl -A Googlebot` on one URL each of `/episode`, `/stock`, `/sector`, `/podcaster`, `/` returns ≥2,000 body characters and ≥1 `application/ld+json` block.
- [ ] `/stock/:ticker` description contains live mention counts and sentiment tally, not the template string.
- [ ] Sitemap `/stock` family lists every ticker with ≥2 mentions in the window (expected ≥250 URLs, was 101).
- [ ] `/articles` linked from the sidebar; `/contact` and `/disclaimer` linked from the footer.
- [ ] `scripts/validate-crawler-meta.mjs` asserts body length and JSON-LD presence per family; `npm run validate:seo` green in CI.
- [ ] Post-deploy crawler-UA check on production recorded in the PR.

### Implementation notes

Single file for the crawler block: `frontend/functions/_middleware.js`. Sitemap change in `backend/src/routers/seo.py:160-166`. Copy the sector-page pattern (`_middleware.js:186-205`), which is the only family already doing this right. No React component changes needed.

Shipped in PR #591 (merged to `develop` 2026-09-05). Verified on dev.tinboker.com with
`curl -A Googlebot` after deploy: episode 14,263 crawler-visible chars / 2 JSON-LD
blocks / 7 Clips; stock 5,266 chars; home 2,382; sector 3,521 (warm API) or title +
description only when `by-sector` misses its 8 s deadline; podcaster 1,110 (10 episode
titles + top tickers — below the 2,000 floor, the payload has no summaries to show).
Dev sitemap `/stock` family 250 URLs (was 101). Remaining: the same check on
production after the next `v*` tag, then Search Console sitemap resubmit.

---

## TKB-011 Stock page charts: price × mention overlay, sentiment split

```yaml
id: TKB-011
status: review
priority: P1
area:
- frontend
type: feature
effort: M
risk: low
github_issue: null
github_project_item: null
pr: https://github.com/HaoweiChan/tinboker/pull/593
```

### Goal

Put the two charts with the best SEO-value-to-cost ratio on `/stock/:ticker`: daily candles with a marker at every podcast mention coloured by sentiment (hover shows the thesis and podcaster), and a 30/90-day bullish/neutral/bearish plus time-horizon split.

Plan and evidence: `docs/seo-data-presentation-plan.md`.

### Acceptance criteria

- [ ] Mention markers render on the existing `lightweight-charts` price chart from `/api/ticker-insights/by-ticker/{t}`; no new charting dependency.
- [ ] Sentiment and time-horizon split renders for any ticker with ≥1 insight; empty state for the rest.
- [ ] The tally numbers are the same ones the TKB-010 crawler sentence uses (one source).
- [ ] `npm run build && npm run lint` green; screenshot of both charts on dev attached to the PR.

### Implementation notes

Data already public: `/api/stocks/{t}` chartData + `/api/ticker-insights/by-ticker/{t}`. Use series markers, not a second chart. Reuse `SimpleSparkline` / existing chart components before adding anything.

Shipped in PR #593 (merged to `develop` 2026-09-06, dev deploy green, bundle carries the
new card). `TradingViewChart` got a `markers` prop; `MentionSplitCard` is the new card.
by-ticker insights now request an explicit 90-day window (API default is 7 days), and the
crawler middleware asks for the same window, so page and description count the same
rows. Verified in headless Chrome against dev-api: 2330 (222 insights) and 2327 (79)
render dots + hover tooltip; tsc, eslint, production build, validate:seo all clean.
Follow-up idea, not scheduled: aggregate dots per week when the visible range exceeds
~6 months, since daily-discussed tickers still cluster at a 1Y zoom.

---

## TKB-012 Institutional-flow chart, sector and podcaster charts

```yaml
id: TKB-012
status: in_progress
priority: P1
area:
- frontend
- backend
type: feature
effort: M
risk: low
github_issue: null
github_project_item: null
pr: null
```

### Goal

Surface three datasets that exist but have no page: 三大法人 daily net buy/sell (`stock_institutional_daily`, 2,089 tickers, internal-key only today), per-sector heat-vs-return on `/sector/:id` (from `/api/sectors/board`), and podcaster top-10 tickers + sector mix on `/podcaster/:id` (from `/api/ticker-insights/by-podcaster`).

Plan and evidence: `docs/seo-data-presentation-plan.md`.

### Acceptance criteria

- [ ] Public read path for institutional data (fold into `/api/stocks/{ticker}/history` or add `/api/stocks/{ticker}/institutional`), cached with the same TTL as OHLC; returns rows for 2330 on staging.
- [ ] Net buy/sell bar chart on `/stock/:ticker` under the price chart.
- [ ] `HeatReturnValidation` single-sector variant on every `/sector/:id`.
- [ ] Top-10 tickers + sector-mix chart on every `/podcaster/:id`.
- [ ] Backend tests for the new endpoint; `npm run build && npm run lint` green.

### Implementation notes

`stock_daily_ohlc` and `stock_institutional_daily` models: `backend/src/database/models.py:227-282`. Internal-key gate to keep: `backend/src/routers/stock.py:77,110` — add a separate public per-ticker path rather than removing the gate on the bulk endpoints.

---

## TKB-013 Weekly rollup pages, selective tag indexing, co-mention graph

```yaml
id: TKB-013
status: ready
priority: P2
area:
- frontend
- backend
- seo
type: feature
effort: L
risk: medium
github_issue: null
github_project_item: null
pr: null
```

### Goal

Add dated `/weekly/YYYY-Www` pages (episode count, top tickers, sentiment shifts, sector heat) built from the payload syndication already composes; lift the blanket `noindex` on `/topics/:tag` for tags with a description and ≥5 episodes in the window; revive `ForceGraph` for ticker co-mention on sector pages.

Plan and evidence: `docs/seo-data-presentation-plan.md`.

### Acceptance criteria

- [ ] `/weekly/*` in the sitemap with crawler-visible content and `Article` JSON-LD.
- [ ] Tag pages meeting the threshold are indexable; others stay `noindex`; validator updated.
- [ ] Search Console impressions for `/weekly/*` and `/topics/*` reviewed 14 days after deploy; AdSense low-value-content status unchanged.
- [ ] Co-mention graph renders on sector pages from `related_tickers`; no SEO dependency.

### Implementation notes

Tag `noindex` lives in `frontend/functions/_middleware.js:28-34` and `backend/src/routers/seo.py:127-137`. Post-mention N-day return charts are deliberately excluded here: they depend on TKB-001 populating `content_mentions` in production (0 rows on 2026-09-05).

---

# Agent Working Rules

When an agent starts work:

1. Read this file first.
2. Pick only one task with `status: ready`, unless the user explicitly chooses a task.
3. Update that task from `ready` to `in_progress`.
4. Implement only the acceptance criteria for that task.
5. Do not change task priority unless explicitly instructed.
6. Do not create new tasks unless explicitly instructed.
7. Open or update a PR.
8. Update `pr:` and implementation notes.
9. Move status to `review` when implementation is ready.
10. Run `python scripts/sync_todo_to_github.py` if GitHub Issues / Project should be updated.

GitHub Issues and GitHub Projects are mirrors.

If there is a conflict between this file and GitHub, this file wins.
