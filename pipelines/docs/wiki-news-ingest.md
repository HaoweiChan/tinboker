# Wiki news-ingest — design plan

Add a financial-news ingest path to the existing Postgres wiki, so a TSMC entity
page reflects both what podcasts said and what news articles said — with
citation traceability down to the source paragraph.

## Context

`tinboker-agents` already implements ~70% of Karpathy's LLM-Wiki pattern, but
only for podcasts: the LangGraph content pipeline derives tickers/sentiment/
entities from episodes and `ingest_episode()` compounds them into a Postgres
wiki (`wiki_pages` + `wiki_links`). News is a blind spot — the previous
`services/knowledge_graph/` tried to fill it, but its output was never wired
into `/api/wiki`, so it was retired in May 2026. This plan adds a **news ingest
path** that writes into the *same* wiki. The hard constraint: extend the one
existing wiki — do not stand up a second wiki system, a new store, or anything
the Netcup VPS systemd setup can't reach.

## What the existing repo already gives us

The wiki is deliberately content-agnostic: `wiki_pages(kind, slug, title,
frontmatter JSONB, body, timestamps)` with `frontmatter` opaque and a GIN index
on it; `wiki_links` is a *projection* table rebuilt on every `upsert_page()`
from `extract_links()`. `WikiRepository` (Postgres / InMemory / Null) is the
only storage seam; `ingest_episode()` in `libs/shared/.../wiki_builder/` is the
high-level pattern to mirror — it renders a page, upserts it, then **append-only
enriches** shared `entity`/`topic` pages (never overwrites). Entity identity
already canonicalizes through `shared/tickers.py` + `data/tickers.json`
(symbol → zh/en name, market, sector, aliases). LLM calls already route through
OpenRouter via `content_builder/llm.py` (`openrouter:` model prefix; model is a
per-role env-var config; `OPENROUTER_API_KEY` is already an optional GSM
secret). `/api/wiki/*` is served by `podcast-api.service` (port 8003, systemd)
and `secrets.bootstrap()` already knows `WIKI_DATABASE_URL`. So the news path
needs **no new store, no new secret, no new API service** — only a new ingest
package, a new `kind`, and new read routes on the existing router.

## Patterns worth stealing from the external repos

- **Kompl** — steal the *cascade idea* (cheap deterministic match → LLM only for
  residuals) and "discovered aliases persist." Skip the embedding layer and
  spaCy: at 20–100 articles/day the ticker registry itself is the deterministic
  dictionary, and embeddings/vector infra are explicitly out of scope.
- **akbp** — steal the typed-claim record shape (subject / predicate / object /
  event_type / confidence / evidence-by-reference / status / supersedes). Skip
  the full 7-state lifecycle; collapse to `active | superseded | contested`.
- **swarmvault** — steal `context build`: topic + token budget → cited excerpts
  packed to bound, with an explicit "omitted N items" signal. Skip the CLI/
  binary and on-disk context-pack files; it becomes one HTTP endpoint.
- **nvk/llm-wiki** — steal dual-linking (every claim links to its raw source URL
  *and* the wiki path resolves through `wiki_links`) and per-*claim* confidence.
  Skip one-confidence-per-page and the Obsidian markdown link syntax.
- **qmd** — steal the retrieval primitive: return IDs + paragraph hashes/ranges,
  not full pages. Skip running qmd and its BM25+vector RRF fusion (overkill
  here).
- **Karpathy gist** — steal contradiction-as-first-class and compounding
  append-only enrichment (already have the latter). Skip the filesystem
  `raw/ wiki/` layout — we are Postgres-backed.

## Architecture

A new uv-workspace package `services/news/` (`tinboker-news`), parallel to
`services/podcast/`, depending on `tinboker-shared`. It is **ingest-only — a
batch CLI, no HTTP server.** It shares the wiki exactly the way the podcast
service does: through the `tinboker-shared` workspace dependency, calling a new
`ingest_news_article()` added alongside `ingest_episode()` in `wiki_builder`.
The webui keeps reading the *same* `/api/wiki/*` on `podcast-api.service`; the
new read routes are added to that existing router. Entity and topic pages are
**shared** between podcasts and news — that sharing is the whole point.

```
 RSS feeds (services/news/feeds.json, git-committed)
        │
        ▼
 [1 fetch_feeds]   feedparser → new article URLs + feed metadata
        │
        ▼
 [2 dedup]         deterministic slug = hash(canonical URL);
                   skip if news_article page exists w/ same content hash
        │
        ▼
 [3 extract]       hybrid: trafilatura full-page extract → paragraphs,
                   each with (index, sha1 hash); fall back to RSS
                   content:encoded/summary when the page is unreachable
        │
        ▼
 [4 dict_prepass]  match paragraph text against the ticker registry +
                   entity-page alias index → candidate canonical entities
                   (the "NLP before LLM" cheap pass)
        │
        ▼
 [5 llm_enrich]    one OpenRouter call (model = config):
                   → typed claims (subject/predicate/object/event_type/
                     sentiment/confidence + paragraph_index + quote span)
                   → tags, plus entity mentions the dictionary missed
        │
        ▼
 [6 resolve]       canonical entity slug per mention:
                   L1 registry/alias exact → L3 LLM disambiguation for
                   genuine residuals only (L2 embeddings deferred);
                   newly-confirmed aliases appended to entity frontmatter
        │
        ▼
 [7 wiki_write]    ingest_news_article():
                   • upsert kind='news_article' page (claims in frontmatter)
                   • append-only enrich shared entity pages (## News
                     Mentions, claim_index, aliases)
                   • create/extend topic pages
                   • wiki_links projection rebuilt as today
        │
        ▼
 Postgres wiki_pages / wiki_links  ──read──▶  /api/wiki/* on podcast-api:8003
```

Steps live in `services/news/src/news/pipeline/steps/` mirroring
`services/podcast/src/pipeline/steps/`. Deployment is a **systemd timer**
(`tinboker-news.timer` → oneshot `tinboker-news.service`, runs a
`run_news.sh` analogous to `run_nightly.sh`), every ~6 h — no port, no
long-running process.

## Schema delta (minimal — frontmatter is the store)

**No new tables, no new columns.** `frontmatter` is opaque JSONB; new content
rides inside it. Concretely:

- **New `kind` value `news_article`.** Needs no DDL.
- **Claims live in the article page's `frontmatter.claims`** — an array of
  akbp-shaped records: `{id, subject (canonical slug), predicate, object,
  event_type (controlled vocab: earnings | guidance | m_and_a | regulatory |
  product | rating | macro | other), sentiment, confidence, claim_date,
  source_url, paragraph_index, paragraph_hash, quote?, status, superseded_by}`.
- **Denormalized top-level frontmatter arrays** `tickers`, `event_types`, and
  scalar `date` — same convention episodes already use — so the existing GIN
  index on `frontmatter` answers `@>` containment queries cheaply ("articles
  mentioning 2330 with an m_and_a event"). Detailed claim objects are read
  only after the page set is narrowed.
- **Entity pages gain frontmatter fields** (append-only, opaque): `aliases`
  (the live, machine-extended alias store — curated seed stays in
  `tickers.json`), `claim_index` (compact rollup of claims about this entity
  from all sources), and `conflicts` (contradiction flags — Phase 2).
- **One index** to add: an expression index on `(frontmatter->>'date')` to make
  date-range/ordering cheap for both news and episodes. `metadata.create_all`
  does *not* add indexes to existing tables, so this ships as an idempotent
  `CREATE INDEX IF NOT EXISTS` appended to `wiki_migrate.sh`.

Alias resolution location: **both** — `tickers.json` is the curated seed;
`entity` page `frontmatter.aliases` is the live store. Resolution builds an
in-memory `alias → slug` index per ingest run from registry + a one-time scan
of entity-page frontmatter (few hundred pages, cheap). This is the only place
"TSMC = 台積電 = 2330.TW = Taiwan Semiconductor" is reconciled, and the result
is visible on the page itself.

A `wiki_claims` *projection* table (same idea as `wiki_links`, rebuilt on
upsert) is a documented Phase-3 option **only if** claim-query volume outgrows
JSONB unnesting — not part of this plan's committed scope.

## Phased rollout

### Phase 1 — vertical slice (small, shippable)
End-to-end RSS → wiki, no contradiction logic yet.
- New `services/news/` package; add to root `pyproject.toml` workspace
  `members`. New deps: `feedparser`, `trafilatura`. `feeds.json` config
  (git-committed, like `podcasts_tw.json`).
- Pipeline steps 1–7 above. **Hybrid fetch** (full-text extract, RSS-content
  fallback).
- New `render_news_article_page()` + `ingest_news_article()` in
  `libs/shared/.../wiki_builder/` (`records.py` + `ingest.py`), reusing
  `_canonical_tickers`, `_append_line_to_section`, `lookup_ticker`,
  `ticker_slug`, `slugify`, and `WikiRepository.upsert_page`.
- Entity-page alias index + L1/L3 entity resolution.
- Claims written to `frontmatter.claims` with full paragraph-level citations
  (source URL + paragraph hash + verbatim quote) — satisfies requirement #1.
- Read routes on the existing wiki router: `GET /api/wiki/news` (paginated,
  date-sorted, filter by ticker/event_type/source/date) and
  `GET /api/wiki/news/{slug}` (detail with claims + citations).
- Deploy: `tinboker-news.timer`/`.service`, `run_news.sh`; extend
  `deploy_vps.sh` to `uv sync` the news package and install the timer.
- **Delivers requirements #1 (citations), #2 (multilingual resolution),
  #5 (date field).**

### Phase 2 — contradiction detection + structured query
- On ingest, for each new claim find prior claims on the same
  `(subject, predicate)` in the entity page's `claim_index`; when objects
  differ, one focused OpenRouter yes/no conflict check decides. Confirmed
  conflicts write a `conflicts` flag onto the entity page frontmatter and set
  the older claim's `status` to `superseded` (newer ≥ confidence) or
  `contested`. Scope: **news-vs-news typed claims + news-vs-podcast sentiment
  cross-check** (no podcast typed-claim backfill).
- `GET /api/wiki/claims` (SQL-answerable structured query — ticker /
  event_type / date range / status, no LLM) and `GET /api/wiki/contradictions`.
- Add the `(frontmatter->>'date')` expression index via `wiki_migrate.sh`.
- **Delivers requirements #3 (contradictions) and #4 (structured query).**

### Phase 3 — context endpoint + followups
- `GET /api/wiki/context?topic=<...>&tokens=<N>` — resolve topic → entity/topic
  slugs → gather linked `news_article` + `episode` pages via `wiki_links` →
  rank by recency + confidence → pack paragraph-level cited excerpts to the
  token budget (heuristic token count) → return excerpts + `omitted:{count,
  reason}` signal. swarmvault budget + qmd ID/hash precision.
- Followups (not committed): `GET /api/wiki/search` full-text (`tsvector`,
  roadmap slice E); a nightly `wiki_lint` pass (orphan links, unsourced claims,
  stale `contested`); `wiki_claims` projection table if needed.

## Critical files

- `libs/shared/src/shared/wiki_builder/ingest.py` — add `ingest_news_article()`.
- `libs/shared/src/shared/wiki_builder/records.py` — add
  `render_news_article_page()`; entity-page render gains `aliases`/`claim_index`.
- `libs/shared/src/shared/wiki_builder/postgres_repo.py` /
  `services/podcast/scripts/wiki_migrate.sh` — the one new index.
- `services/podcast/src/routers/wiki.py` — new `news` / `claims` /
  `contradictions` / `context` read routes (no new API service).
- `services/news/` (new) — `feeds.json`, `pipeline/steps/`, CLI, `run_news.sh`.
- Root `pyproject.toml` — add `services/news` to workspace members.
- `services/podcast/scripts/deploy_vps.sh` — sync news package + install timer.
- `libs/shared/src/shared/tickers.py` / `data/tickers.json` — curated alias seed
  (reused as-is; extend the JSON for any new seed companies).

## Verification

- **Unit (offline):** new `services/news/tests/` + `libs/shared/tests/` cases,
  run with `uv run --package tinboker-news pytest` and existing
  `test_wiki_*` — use `InMemoryWikiRepository`; mock OpenRouter and HTTP fetch.
  Assert: paragraph hashes stable; claims carry source URL + paragraph hash;
  zh/en mentions of one company collapse to one entity slug; re-ingesting the
  same article is idempotent (`upsert` by deterministic slug).
- **Integration:** point `WIKI_DATABASE_URL` at a local/throwaway Postgres,
  run `wiki_migrate.sh`, ingest 2–3 fixture articles, confirm `wiki_pages` has
  `kind='news_article'` rows and shared `entity` pages show a `## News
  Mentions` section alongside `## Episode Mentions`.
- **API:** start the podcast app locally; `GET /api/wiki/news` returns the
  ingested articles date-sorted; `GET /api/wiki/news/{slug}` shows claims with
  citations; for an existing ticker, `GET /api/wiki/pages/entity/<slug>`
  reflects both podcast and news mentions.
- **Deploy smoke:** `systemctl start tinboker-news.service` once on the VPS;
  confirm a fresh `news_article` row and `curl :8003/api/wiki/news`.
- Phase 2: ingest two articles with conflicting claims on one ticker; confirm a
  `conflicts` flag on the entity page and `GET /api/wiki/contradictions`.

## Open questions before Phase 1

1. **Feed list** — which RSS feeds / sources (TW vs US weighting)? Plan is to
   scaffold `services/news/feeds.json` to populate; nothing else blocks on it.
2. **OpenRouter model default** — which model for the enrichment call (it is a
   config value; suggest a cheap, capable default mirroring the podcast path's
   Flash-Lite-for-extraction choice)?
3. **Timer cadence** — every 6 h assumed; confirm or set daily.
4. **`event_type` vocabulary** — the controlled list above
   (earnings/guidance/m_and_a/regulatory/product/rating/macro/other) — any
   categories to add or drop?
