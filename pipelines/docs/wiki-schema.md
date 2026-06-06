# Knowledge Wiki — schema

The knowledge wiki is **content**, so it lives in a **Postgres database on the VPS**, not in
this repo. The code that reads/writes it is content-agnostic infra:

- Library: [`libs/shared/src/shared/wiki_builder/`](../libs/shared/src/shared/wiki_builder/) —
  `WikiRepository` (`PostgresWikiRepository`, `InMemoryWikiRepository`, `NullWikiRepository`),
  `ingest_episode` / `ingest_supply_chain`, `render_*_page`, markdown *views*.
- HTTP API: `services/podcast` exposes `/api/wiki/...` (see
  [`services/podcast/src/routers/wiki.py`](../services/podcast/src/routers/wiki.py)).
- The podcast pipeline writes through the repository in
  [`services/podcast/src/pipeline/steps/wiki_ingest.py`](../services/podcast/src/pipeline/steps/wiki_ingest.py)
  (best-effort; no-op if `WIKI_DATABASE_URL` is unset).

Set `WIKI_DATABASE_URL` (e.g. `postgresql+psycopg://user:pass@127.0.0.1:5432/tinboker_wiki`)
via Google Secret Manager / `bootstrap()`.

## Database schema

```sql
CREATE TABLE wiki_pages (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,                       -- 'episode' | 'entity' | 'topic' | 'supply_chain'
    slug        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    frontmatter JSONB NOT NULL DEFAULT '{}'::jsonb,  -- opaque content metadata (see below)
    body        TEXT NOT NULL DEFAULT '',            -- rendered prose (markdown view source)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kind, slug)
);
CREATE INDEX ix_wiki_pages_kind ON wiki_pages (kind);
CREATE INDEX ix_wiki_pages_frontmatter ON wiki_pages USING GIN (frontmatter);

CREATE TABLE wiki_links (              -- a projection of page content, rebuilt on every upsert
    src_kind TEXT NOT NULL, src_slug TEXT NOT NULL,
    dst_kind TEXT NOT NULL, dst_slug TEXT NOT NULL,
    context  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (src_kind, src_slug, dst_kind, dst_slug),
    FOREIGN KEY (src_kind, src_slug) REFERENCES wiki_pages (kind, slug) ON DELETE CASCADE
);
CREATE INDEX ix_wiki_links_dst ON wiki_links (dst_kind, dst_slug);
```

`metadata.create_all()` on `PostgresWikiRepository` creates these idempotently (see
`scripts/wiki_migrate.sh`). The `wiki_builder` layer never inspects `frontmatter` semantics —
everything content-specific is pass-through JSONB, so the schema does not change when the
content model evolves. `wiki_links` is derived: on each `upsert_page`, the repo re-extracts
`[[prefix/slug|label]]` links from `body` (and `tickers`/`tags` from an episode's frontmatter)
and rewrites the edge rows for that source page.

## Frontmatter conventions (by `kind`) — informational, not enforced

| kind | typical `frontmatter` keys | `title` |
|------|---------------------------|---------|
| `episode` | `podcast`, `episode_number`, `date`, `tickers[]` (canonical symbols), `tags[]`, `source_urls{mp3,transcript,summary}`, `ticker_sentiment{sym: bull\|bear\|neut}` | episode title |
| `entity` | `id` (= slug), `name`, `entity_type` (`company`/`etf`/`person`/`product`/`country`), `tickers[]`, `market` (`TW`/`US`/…, when known), `sector` (when known) | entity name |
| `topic` | `id` (= slug), `name` | topic name |
| `supply_chain` | `entity` (= slug of the source entity) | `"{name} — Supply Chain"` |

**Ticker registry** — `ingest_episode` canonicalizes ticker symbols (e.g. `2330.TW` → `2330`) and,
for tickers in [`libs/shared/src/shared/data/tickers.json`](../libs/shared/src/shared/data/tickers.json),
sets the entity page's `name` (Traditional Chinese), `market`, `sector`, and `entity_type` from that
registry; unknown tickers fall back to the raw symbol. Lookup helpers: `shared.tickers.lookup_ticker` /
`canonical_symbol`. Extend `tickers.json` freely. (TODO: have `services/knowledge_graph` ticker
seeding use the same registry.)

Slugs: lowercase, hyphens for spaces (CJK preserved); ticker slugs lowercase with `.`→`-`;
episode slug = `{slugified_podcast}_ep{number}` (or `{slugified_podcast}_{slugified_title[:60]}`).

## Markdown view

`shared.wiki_builder.page_to_markdown(page)` reconstructs an Obsidian-style `.md` document
(`---` YAML frontmatter with a `type: {kind}` field, then `body`). `build_index_markdown(pages)`
renders the equivalent of the old `wiki/index.md`. These are *views* for browsing/export only —
the database is the source of truth. The HTTP API serves them at
`GET /api/wiki/pages/{kind}/{slug}.md` and `GET /api/wiki/index?format=md`.

## HTTP API summary

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/wiki/health` | — | `{status, backend}` |
| `GET /api/wiki/pages?kind=&q=&limit=&offset=` | — | list pages (`q` = frontmatter contains, e.g. `tickers:TSM`) |
| `GET /api/wiki/pages/{kind}/{slug}` | — | one page (JSON) |
| `GET /api/wiki/pages/{kind}/{slug}.md` | — | one page (`text/markdown`) |
| `GET /api/wiki/index?format=json\|md` | — | index summary |
| `GET /api/wiki/links?src_kind=&src_slug=` / `?dst_kind=&dst_slug=` | — | list edges |
| `PUT /api/wiki/pages/{kind}/{slug}` | X-API-Key | upsert (`{title, frontmatter, body}`) |
| `DELETE /api/wiki/pages/{kind}/{slug}` | X-API-Key | delete |
| `POST /api/wiki/ingest/episode` | X-API-Key | high-level `ingest_episode(**body)` |
| `GET /api/wiki/episodes?podcast=&ticker=&tag=&limit=&offset=` | — | structured episode feed (date-desc), filterable by show / ticker / tag |
| `GET /api/wiki/episodes/{slug}` | — | full episode detail (summary, events, ticker recs, related links, source urls; `bullets`/`chapters`/`clips` are slice-D placeholders) |
| `GET /api/wiki/stats/top-tickers?days=&limit=` | — | tickers by # episodes in window + sentiment split |
| `GET /api/wiki/stats/top-shows?days=&limit=` | — | podcasts by # episodes in window + delta vs. prev window |
| `GET /api/wiki/stats/topics?days=&limit=` | — | topics by # episodes + normalized weight + dominant sentiment |
| `GET /api/wiki/stats/pulse?date=` | — | one day: episode count, distinct tickers, sentiment split |
| `GET /api/wiki/stats/dashboard?days=` | — | `{pulse, top_tickers, top_shows, topics}` in one call |
| `GET /api/wiki/stats/entity/{slug}?days=` | — | per-entity rollup: mentions, last-mentioned-at, sentiment split, recent episodes |

The `/stats/*` aggregates are content-derived (`shared.wiki_builder.stats`) — computed on the fly
from episode dates, `tickers`/`tags` membership, and `ticker_sentiment`. They never include
prices / `change` % (that's the platform's quote source).

## Knowledge-graph (follow-up, deferred)

`services/knowledge_graph` used to also write `wiki/entities/*.md` + `wiki/supply-chain/*.md`
from its `WikiStore`; that markdown writing has been removed. Its graph still persists to the
local JSON store `wiki-graph/kg_store.json`. A follow-up will have it push entities/supply-chain
to the wiki via `PUT /api/wiki/pages/...` (it runs on Cloud Run and can't share a process with
the VPS Postgres) and move `kg_store.json` into Postgres.
