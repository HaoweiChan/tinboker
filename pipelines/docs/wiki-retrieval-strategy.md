# Wiki Retrieval Strategy — Research Report

**Context:** TinBoker's wiki stores episode summaries, entity pages, topic pages, and graph links
in a Postgres database. As the corpus grows, the core risk is that retrieving relevant content
requires loading every row into Python memory and filtering there — an O(n) scan on every request.
This document surveys the current state, the Karpathy LLM-wiki pattern that surfaced the same
problem, and the concrete steps to fix it.

---

## 1. The Karpathy LLM-Wiki Pattern

In April 2026 Andrej Karpathy published a gist ([llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f))
describing a pattern for LLM-maintained knowledge bases that went viral because it named a problem
everyone was quietly hitting: **if you give an LLM a growing corpus, it eventually has to read all
of it on every query.**

### Three-layer architecture

```
raw/          ← immutable source documents (the LLM reads but never modifies)
wiki/         ← LLM-owned markdown pages (summaries, entities, topics, comparisons)
CLAUDE.md     ← schema: conventions, ingest workflow, page templates
```

### Three operations

| Operation | What it does |
|-----------|-------------|
| **Ingest** | Read new source → extract knowledge → update 10–15 existing wiki pages in one pass |
| **Query** | Read `index.md` (the routing map), load only the relevant pages, synthesize answer |
| **Lint** | Periodic health check: contradictions, orphan pages, stale claims, missing cross-refs |

### The key insight: `index.md` as a routing map

The mechanism that makes Karpathy's pattern scale without vector infrastructure is the
**index file**: a single document listing every wiki page with a one-line summary, the category
it belongs to, and its slug. When a query arrives the LLM reads the index (~few thousand tokens)
to decide which 3–5 pages to fetch, then reads only those. At moderate corpus sizes (hundreds of
pages) this is **cheaper than embedding search** — one context read, no vector round-trip, full
transparency.

```markdown
## Episodes
- [[episodes/the-chaikin-podcast_ep42]] — NVDA supply chain risk, 2026-05-01 (tickers: NVDA, TSM)
- [[episodes/money-talk_ep88]] — Fed rate outlook, 2026-04-28 (tickers: SPY, TLT)

## Entities
- [[entities/nvda]] — NVIDIA; US semiconductors; 47 episode mentions
- [[entities/tsm]] — TSMC; TW semiconductors; 31 episode mentions

## Topics
- [[topics/ai]] — AI & compute; 120 episode mentions; dominant sentiment: bull
```

The LLM routes by **reading this index, not by scanning all pages.** This is the key
technique for avoiding token-expensive full scans at small-to-medium scale.

### Compounding: the other key property

Karpathy's ingest prompt enforces: *"Preserve and extend existing content — never discard
information already on the page."* Each new source enriches existing pages rather than
overwriting them. Knowledge compounds. This is exactly how our `ingest_episode` builds entity
and topic pages — it appends episode mentions and extends "Ticker History" tables rather than
replacing. **We already have this property.**

---

## 2. The Problem in Our Repo

### What we have

Our current retrieval path (as of this branch) for almost every query:

```python
# wiki.py — episode feed
for page in repo.list_pages(kind="episode", limit=1_000_000):  # load ALL episodes
    if podcast and item["podcast"] not in podcast: continue     # filter in Python
    if tag and tag not in item["tags"]: continue
    if want_ticker and ...: continue
items.sort(...)
return items[offset : offset + limit]                           # paginate in Python
```

And every stats aggregate:

```python
# stats.py — top_tickers, top_shows, topics, pulse, entity_aggregate
def _episodes(repo, days):
    all_eps = repo.list_pages(kind="episode", limit=1_000_000)  # full scan every call
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return [e for e in all_eps if _parse_date(e.frontmatter.get("date","")) >= cutoff]
```

**Every single read-path is O(n) on the entire episode table, computed in Python.**

### Scale breakpoints

| Episode count | Current behaviour | Symptom |
|--------------|------------------|---------|
| < 2,000 | Fine | No problem today |
| 5,000–10,000 | Noticeable | `/episodes` and `/stats/*` start taking seconds |
| 50,000+ | Broken | Memory pressure; Python GIL; timeouts |
| 100,000+ | Unusable | OOM or request timeout on every stats call |

The Postgres GIN index on `frontmatter` exists but is **never used** — because filtering happens
after the rows are already in Python memory.

### What we're missing vs. the Karpathy pattern

| Karpathy pattern | Our current state |
|-----------------|------------------|
| `index.md` — one-line summary per page for LLM routing | `GET /api/wiki/index` exists but is a raw dump, not optimized as a routing aid |
| SQL-side filtering with pushed-down WHERE | All filtering is Python-side after full SELECT |
| Compounding: append-only page enrichment | ✓ We have this (entity/topic pages accumulate mentions) |
| Graph links (`wiki_links` table) for traversal | ✓ We have this; DST index exists |
| Full-text search on body prose | Not present |
| Vector / semantic search | Not present |
| Stats caching | Not present; recomputed every request |

---

## 3. Retrieval Strategies — a Taxonomy

### 3.1 Index-file routing (Karpathy's approach, zero infrastructure)

An LLM reads a structured `index.md` containing one-line summaries and metadata for every
page. It picks which slugs to fetch, then does direct `GET /api/wiki/pages/{kind}/{slug}` calls.

**Pros:** No embedding pipeline, no vector DB, transparent, works well up to ~1,000 pages.  
**Cons:** Index grows with corpus; at 10k+ pages the index itself becomes too large for a single
context window.

**Fits TinBoker at:** current scale (hundreds to low thousands of episodes).

### 3.2 SQL-side filtering (push WHERE into Postgres)

Replace Python-side loops with proper SQL:

```sql
-- Episodes by ticker
SELECT * FROM wiki_pages
WHERE kind = 'episode'
  AND frontmatter @> '{"tickers": ["NVDA"]}'::jsonb   -- uses GIN index
  AND (frontmatter->>'date')::date >= now() - '7 days'::interval
ORDER BY (frontmatter->>'date')::date DESC
LIMIT 20 OFFSET 0;
```

Add composite indexes:

```sql
-- Date range queries on episodes
CREATE INDEX ix_wiki_pages_episode_date
  ON wiki_pages ((frontmatter->>'date') DESC)
  WHERE kind = 'episode';

-- Ticker presence (GIN already covers @> containment)
-- Already exists: ix_wiki_pages_frontmatter USING GIN (frontmatter)
```

**Pros:** O(log n) retrieval for date-range + ticker queries; no new infrastructure.  
**Cons:** Some query types (complex sentiment thresholds, multi-hop graph joins) are awkward in SQL.

**Fits TinBoker at:** 1k–100k episodes; this is the most important near-term fix.

### 3.3 Postgres full-text search (tsvector)

Add a generated tsvector column on `body + title` for prose search:

```sql
ALTER TABLE wiki_pages
  ADD COLUMN body_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,''))
  ) STORED;

CREATE INDEX ix_wiki_pages_tsv ON wiki_pages USING GIN (body_tsv);
```

Queries:

```sql
SELECT slug, title, kind,
       ts_rank(body_tsv, query) AS rank
FROM wiki_pages, plainto_tsquery('english', 'semiconductor supply chain') query
WHERE body_tsv @@ query
ORDER BY rank DESC
LIMIT 10;
```

**Pros:** Searches episode summaries and entity prose, not just frontmatter keys; built into Postgres.  
**Cons:** Keyword match only (no semantic similarity); English stemming won't help with Chinese text.

**Fits TinBoker at:** 1k–500k pages; enables `GET /api/wiki/search?q=...`.

### 3.4 Vector embeddings + pgvector (semantic search)

Embed each page's body (or summary) and store the embedding vector in Postgres:

```sql
-- Requires: CREATE EXTENSION vector;
ALTER TABLE wiki_pages ADD COLUMN embedding vector(1536);
CREATE INDEX ix_wiki_pages_embedding
  ON wiki_pages USING hnsw (embedding vector_cosine_ops);
```

Query:

```sql
SELECT slug, title, 1 - (embedding <=> $1::vector) AS similarity
FROM wiki_pages
WHERE kind = 'episode'
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

Embed at ingest time with `text-embedding-3-small` (OpenAI) or `text-embedding-004` (Gemini).

**Pros:** Semantic similarity — "semiconductor supply chain risk" finds episodes that never use
those exact words; scales to millions of rows with HNSW index (sub-millisecond query).  
**Cons:** Embedding pipeline cost; embedding regeneration on body updates; English embeddings
work poorly on Chinese text without a multilingual model.

**Fits TinBoker at:** 10k+ episodes; enables "find similar episodes" and "related content" features.

### 3.5 GraphRAG — vector entry point + graph traversal

The 2026 practitioner consensus is a hybrid pattern:

```
Query → embed query → vector search → top-k seed pages
       ↓
       wiki_links graph → traverse 1–2 hops → expand result set
       ↓
       Synthesize answer from seed + neighbors
```

We already have the graph (`wiki_links` table with `(src_kind, src_slug, dst_kind, dst_slug)`)
and the DST index. GraphRAG would use our existing edges as the traversal layer, with vector
search as the entry point.

**Example:** Query "NVDA supply chain risk" →
1. Vector search finds top 5 episode pages mentioning supply chain.
2. Graph traversal from those episodes through `wiki_links` → fetches `entities/nvda`,
   `entities/tsm`, `supply_chain/nvda`.
3. Answer synthesized from the expanded subgraph.

**Pros:** Best recall for multi-hop relational queries (which companies are in NVDA's supply
chain and what did recent episodes say about them?).  
**Cons:** Requires embeddings pipeline; graph traversal adds latency; recursive CTEs in Postgres
can be slow for deep graphs.

**Fits TinBoker at:** when the platform needs "related content" and entity relationship queries.

### 3.6 Hybrid BM25 + vector (full production RAG)

Tools like `pgai` / `pg_search` offer combined BM25 keyword ranking + vector cosine scoring
with a single SQL call. This is the "kitchen sink" option — high quality but complex to operate.

---

## 4. How Our Architecture Compares to the Karpathy Pattern

### What we're doing right

| Property | Status |
|----------|--------|
| **Compounding ingestion** | Entity and topic pages accumulate episode mentions via `ingest_episode`; append-only enrichment, never overwrites |
| **Graph edges as first-class data** | `wiki_links` is a proper relation with indexed reverse lookups |
| **Content-agnostic storage** | `frontmatter` is opaque JSONB; schema does not change with content model |
| **Repository abstraction** | Null/InMemory/Postgres backends; pipeline is resilient if DB is unavailable |
| **Index endpoint** | `GET /api/wiki/index?format=md` renders a `build_index_markdown` view — the skeleton of Karpathy's `index.md` already exists |

### What we're NOT doing

| Gap | Risk |
|-----|------|
| SQL-side filtering | Every list query is a full table scan in Python — the dominant scaling problem |
| Stats caching | `/stats/top-tickers`, `/stats/pulse` etc. recompute from all episodes on every HTTP request |
| Optimized LLM routing index | `/api/wiki/index` exists but isn't structured for LLM navigation (no category grouping, no mention counts, no date ranges) |
| Full-text search | No way to search episode body prose; only frontmatter key/value matching |
| Vector embeddings | No semantic similarity retrieval |
| Keyset pagination | Offset pagination fetches all rows before slicing |

### Why our current approach resembles an early-stage LLM wiki

We built a clean three-layer pattern — raw sources (GCS MP3/transcript), wiki (Postgres pages),
schema (CLAUDE.md + wiki-schema.md). The ingest pipeline compiles raw transcripts into
structured wiki pages, exactly as Karpathy describes. The gap is that we treated **retrieval as
a later problem** and left it as Python-side scans. For the corpus sizes encountered so far
(hundreds of episodes) this has been invisible. It becomes the bottleneck at 5k+ episodes.

---

## 5. Recommendations — Tiered by Urgency

### Tier 1 — Immediate (no new infrastructure, pure SQL/Python changes)

**A. Push filtering into SQL**

Replace the Python-side frontmatter loop in `list_pages` and the episode feed endpoint with
proper SQL WHERE clauses using the existing GIN index:

```python
# postgres_repo.py — replace the current scan
def list_pages(self, kind=None, frontmatter_filter=None, limit=100, offset=0):
    conditions = ["kind = :kind"] if kind else []
    params = {"kind": kind, "limit": limit, "offset": offset}
    if frontmatter_filter:
        for key, val in frontmatter_filter.items():
            # Use Postgres @> containment for list values, = for scalars
            conditions.append(f"frontmatter @> :{key}_filter::jsonb")
            params[f"{key}_filter"] = json.dumps({key: val})
    sql = f"""
        SELECT * FROM wiki_pages
        {'WHERE ' + ' AND '.join(conditions) if conditions else ''}
        ORDER BY kind, slug
        LIMIT :limit OFFSET :offset
    """
    ...
```

**B. Add a date expression index for episode date-range queries**

```sql
CREATE INDEX CONCURRENTLY ix_wiki_pages_episode_date
  ON wiki_pages ((frontmatter->>'date') DESC)
  WHERE kind = 'episode';
```

**C. Fix stats to use SQL aggregates instead of Python Counter**

```sql
-- top_tickers: expand tickers array in SQL, count, filter by date
SELECT ticker, COUNT(*) AS mentions
FROM wiki_pages,
     jsonb_array_elements_text(frontmatter->'tickers') AS ticker
WHERE kind = 'episode'
  AND (frontmatter->>'date')::date >= now() - (:days || ' days')::interval
GROUP BY ticker
ORDER BY mentions DESC
LIMIT :limit;
```

**D. Add a materialized stats cache table** (or a simple Redis TTL, 1h)

Stats (`top_tickers`, `top_shows`, `pulse`) are read-heavy and can tolerate 1–24h staleness.
Refresh them in the pipeline after each batch ingest, not on every HTTP request.

### Tier 2 — Medium-term (0 new services, Postgres extension)

**E. Add Postgres full-text search index**

```sql
ALTER TABLE wiki_pages
  ADD COLUMN body_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,''))
  ) STORED;
CREATE INDEX ix_wiki_pages_tsv ON wiki_pages USING GIN (body_tsv);
```

Expose as `GET /api/wiki/search?q=semiconductor+supply+chain`.

**F. Improve the LLM routing index**

The existing `build_index_markdown` function is the right idea. Make it useful for LLM navigation:
- Group pages by kind with one-line descriptions (already mostly there)
- For episodes: include date, ticker list, and tag list in the one-liner
- For entities: include mention count and dominant sentiment
- Add a `?since=2026-04-01` filter so an LLM can ask for "what's new since last week"
- Serve it at `GET /api/wiki/index?format=md&since=YYYY-MM-DD`

This turns the index into Karpathy's `index.md` — the LLM reads this ~10k-token document,
identifies which 5–10 slugs to fetch, and only reads those. No vector infrastructure needed.

**G. Implement keyset pagination for the episode feed**

Replace `OFFSET n` with:
```sql
WHERE kind = 'episode'
  AND (frontmatter->>'date')::date < :cursor_date
  AND slug < :cursor_slug    -- tiebreak
ORDER BY (frontmatter->>'date')::date DESC, slug DESC
LIMIT :limit
```

### Tier 3 — Long-term (new infrastructure: pgvector)

**H. Add vector embeddings with pgvector**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE wiki_pages ADD COLUMN embedding vector(1536);
CREATE INDEX ix_wiki_pages_embedding
  ON wiki_pages USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

- Embed at ingest time (Gemini `text-embedding-004` is already in the stack; add a pipeline step).
- Re-embed only on body change (track with a `embedding_updated_at` column).
- Expose as `GET /api/wiki/similar/{kind}/{slug}?limit=5`.

**I. GraphRAG on top of existing wiki_links**

The `wiki_links` table is already a proper knowledge graph. Once embeddings exist:
1. Vector search for top-k seed pages.
2. One-hop graph expansion via `wiki_links`.
3. Return the union as the context window for the synthesizing LLM.

This is a native Postgres query (recursive CTE or two sequential queries) — no external graph DB.

---

## 6. Graphify — A Karpathy-pattern Realization We Already Use

[Graphify](https://github.com/safishamsi/graphify) is a Karpathy-style "LLM wiki" realization
that turns a folder of code, docs, PDFs, and images into a queryable knowledge graph. We've
already run it against this repo — the artifacts live in [graphify-out/](../graphify-out/).
This is important because it gives us concrete evidence of which graphify ideas survive when
applied to our content, and which don't.

### 6.1 What graphify produced for *this* repo

From [graphify-out/GRAPH_REPORT.md](../graphify-out/GRAPH_REPORT.md) (2026-05-13 run on 150 files,
~118k words):

```
1232 nodes · 1896 edges · 102 communities · 21% edges INFERRED (avg confidence 0.5)
```

**Artifacts** (~2.3 MB total, committed to git for team-wide AI-assistant use):

- [graph.json](../graphify-out/graph.json) — full graph (`nodes`, `links`, `hyperedges`, `community` ids)
- [graph.html](../graphify-out/graph.html) — interactive D3 visualization
- [GRAPH_REPORT.md](../graphify-out/GRAPH_REPORT.md) — "god nodes," surprising connections, communities
- [manifest.json](../graphify-out/manifest.json) — file mtimes for incremental rebuilds
- [cache/](../graphify-out/cache/) — per-file LLM extraction cache

**Node schema** (from inspection of `graph.json`):
```json
{
  "label": "test_tickers.py",
  "file_type": "code",
  "source_file": "libs/shared/tests/test_tickers.py",
  "source_location": "L1",
  "id": "test_tickers",
  "community": 6
}
```

**Edge schema:**
```json
{
  "relation": "contains",
  "confidence": "EXTRACTED",
  "source_file": "...",
  "weight": 1.0,
  "source": "test_tickers",
  "target": "test_tickers_test_lookup_by_canonical_and_alias",
  "confidence_score": 1.0
}
```

**God nodes** (centrality leaders graphify identified): `GCSStorageService` (64 edges),
`FirebaseService` (52), `Sentence` (50), `PodcastEpisode` (43), `WikiRepository` (30),
`EpisodeData` (30), `PipelineConfig` (29).

**Hyperedges** (LLM-extracted concept groupings): "End-to-End Podcast Pipeline RSS to Wiki,"
"VPS Production Topology," "Wiki Content API Serving Stack," "STT Service Options."

### 6.2 Graphify's pipeline — what it actually does

```
Input files (code, docs, PDFs, images)
   ↓
Tree-sitter AST extraction (local, free) ──┐
   ↓                                       │
LLM semantic extraction (docs/PDFs/images) ┤  hybrid
   ↓                                       │
Merge into directed graph                  ┘
   ↓
Leiden community detection ──→ topical clusters
   ↓
Centrality scoring ──→ "god nodes"
   ↓
LLM relationship inference ──→ INFERRED edges with confidence
   ↓
LLM labeling of communities + hyperedges
   ↓
Static artifacts: graph.json / graph.html / GRAPH_REPORT.md
```

The retrieval model is fundamentally **static-artifact-based**: graphify is run periodically,
the artifacts are committed to git, and AI coding assistants read `graph.json` /
`GRAPH_REPORT.md` directly. No live query endpoint, no embedding store, no vector search —
just a snapshot the LLM navigates.

### 6.3 Two different problems — graphify ≠ note DB

The first thing to be honest about: **graphify and our wiki solve different problems with
different shapes.**

| Dimension | Graphify (as used in this repo) | Our wiki (note DB) |
|----------|--------------------------------|---------------------|
| **What is indexed** | Source code + repo docs (this codebase) | Podcast episode summaries, entities, topics |
| **Who reads it** | AI coding assistants (Claude Code, Cursor) navigating *this repo* | The TinBoker platform webui via HTTP API |
| **Update model** | Periodic batch rebuild (or AST-only on commit hook) | Continuous, near-real-time per episode ingest |
| **Storage** | Static JSON files in git (`graphify-out/`) | Live Postgres rows with frontmatter JSONB |
| **Query model** | LLM reads the JSON snapshot, no live API | HTTP API with filters, pagination, stats |
| **Scale** | Bounded (~1k nodes today, grows slowly) | Unbounded (episodes accumulate daily) |
| **Latency budget** | Doesn't matter (offline AI assistant context) | <500ms p99 for webui requests |

**Implication:** we cannot just point graphify at our Postgres wiki and have it work. The
`/graphify` skill writes to disk, not Postgres; it expects a bounded folder, not a growing
table; its outputs are for an AI coding assistant, not a React frontend. **Direct adoption
is the wrong question.** The right question is: *which of graphify's algorithms and patterns
should we port into our wiki?*

### 6.4 What from graphify *does* transfer — and is high value

Graphify's value isn't the tree-sitter extraction (irrelevant to us — our content is already
structured); it's the **graph-analytics layer applied after extraction**. Every one of these
techniques maps cleanly onto our existing `wiki_pages` + `wiki_links` schema.

#### A. Leiden community detection on `wiki_links`

We already have a knowledge graph: every episode → ticker, ticker → ticker via `supply_chain`,
episode → topic. What we *don't* have is auto-discovered clustering. Graphify ran Leiden over
the codebase and produced 102 communities (e.g., "Wiki Stats Aggregation," "LangGraph Content
Builder," "Spotify Auth"). Running the same algorithm over `wiki_links` would auto-discover
**topical entity communities** — "AI semiconductors," "Taiwan supply chain," "US megacaps,"
"fintech," etc. — without any manual tagging.

This is far more powerful than our current `tags` array, which is LLM-extracted per episode
and not unified across the corpus. Communities discovered structurally would be stable, naming-
agnostic, and reveal relationships the LLM didn't explicitly tag.

**Implementation:** Python `networkx` + `python-igraph` (Leiden), run as a nightly job:

```python
import igraph as ig
import leidenalg

# Build graph from wiki_links (entity ↔ entity via co-mention in episodes)
edges = repo.execute("""
  SELECT a.dst_slug AS e1, b.dst_slug AS e2, COUNT(*) AS weight
  FROM wiki_links a
  JOIN wiki_links b ON a.src_kind='episode' AND a.src_slug=b.src_slug
  WHERE a.dst_kind='entity' AND b.dst_kind='entity' AND a.dst_slug < b.dst_slug
  GROUP BY a.dst_slug, b.dst_slug
""")
g = ig.Graph.TupleList(edges, weights=True, directed=False)
partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
# Persist community assignments to a wiki_communities table
```

Store the result in a new `wiki_communities` table and a `community_id` column on entity
frontmatter, or as a denormalized `wiki_graph_snapshot.json` file (graphify-style).

#### B. Centrality-based "god nodes" for entity importance

Our current `top_tickers` ranks by raw mention count. Centrality scoring (PageRank or
eigenvector centrality) ranks entities by **structural importance in the graph**: an entity
mentioned 5 times in episodes that *also mention many other important entities* is more
"central" than one mentioned 20 times in isolated episodes.

This is a strictly better signal for "what matters in our corpus." Graphify identified
`WikiRepository` and `GCSStorageService` as god nodes in our codebase precisely because they
are bridges between many subgraphs — the same logic surfaces hub-companies (NVDA, TSM) over
flash-in-the-pan mentions.

```python
import networkx as nx
G = nx.Graph()
# load wiki_links as edges
pagerank = nx.pagerank(G, weight='weight')
# top 10 = "god node" entities
```

Expose as `GET /api/wiki/entities/top?metric=pagerank&limit=20`.

#### C. LLM-extracted hyperedges (group concepts)

Graphify's hyperedges — "End-to-End Podcast Pipeline RSS to Wiki" linking 7 components, "VPS
Production Topology" linking 5 — are LLM-generated *named groupings* of related nodes. They
solve the "this set of things belongs together but no pairwise edge captures it" problem.

For our wiki, hyperedges would be auto-discovered **supply chain groupings, sector themes,
event clusters**. We currently hand-author `supply-chain/*` pages; an LLM hyperedge extractor
could propose new ones from co-mention patterns (e.g., "AI Memory Stack: HBM + Samsung + SK
Hynix + Micron + NVDA"). Each accepted hyperedge becomes a new `kind=topic` or
`kind=supply_chain` page.

This is the *compounding* property of Karpathy's pattern realized at the graph level —
new sources don't just enrich existing pages, they suggest new pages worth creating.

#### D. Static graph-snapshot artifact as the LLM routing index

This is the single biggest takeaway. Graphify's `GRAPH_REPORT.md` is exactly what Section 1
called Karpathy's `index.md` — a single document an LLM reads to navigate the corpus, with:
- God nodes (most-connected entities)
- Surprising connections (low-confidence INFERRED edges flagged)
- Community summaries (each community's name + member count + cohesion)
- Hyperedges (concept groupings)

We should build the equivalent for our wiki: a **`wiki_graph_snapshot`** rebuilt nightly that
contains community labels, centrality rankings, hyperedge groupings, and per-entity 1-line
summaries. Serve it as `GET /api/wiki/graph-snapshot` (or write to GCS as a static file). LLM
agents query *this snapshot* instead of scanning `/api/wiki/episodes` — three orders of
magnitude fewer tokens, and the snapshot is **structurally meaningful** rather than just a
list.

#### E. Incremental rebuild via manifest

Graphify's `manifest.json` is just `{file_path: mtime}` — a trivial change-detection layer.
We have the same primitive for free: `wiki_pages.updated_at`. The nightly graph job only needs
to recompute community membership for pages updated since the last run, and Leiden supports
incremental partition refinement. This is a cheap operational pattern worth copying.

#### F. Confidence-tagged edges

Graphify edges carry `confidence: EXTRACTED | INFERRED | AMBIGUOUS` and a `confidence_score`.
Our `wiki_links` edges are all binary — they exist or they don't. Adding a confidence field
distinguishes "ticker explicitly in `frontmatter.tickers`" (EXTRACTED, 1.0) from "ticker
inferred from prose mention via LLM" (INFERRED, 0.6). This makes future relaxed-precision
features (e.g., "show me episodes that *probably* discuss NVDA") possible without polluting
the strict-match path.

### 6.5 What from graphify *does not* transfer

| Graphify capability | Why it doesn't fit our note DB |
|--------------------|--------------------------------|
| Tree-sitter AST extraction | We have no source code to parse; our nodes are already structured records |
| Whole-corpus batch re-extraction | Our wiki grows continuously; we need incremental ingest, not periodic full rebuilds |
| `graph.html` interactive viz | The platform webui owns visualization; serving 1 MB of D3 HTML from `/api/wiki` is the wrong shape |
| MCP server interface | Consumers are the webui via HTTP, not Claude Code via MCP |
| `.graphifyignore` file globbing | Our "files" are Postgres rows with explicit `kind` filtering |
| Committing artifacts to git | Wiki content lives in Postgres on the VPS by design; graph snapshots belong there too or in GCS |

### 6.6 Conclusion — should we apply graphify?

**Not as a runtime dependency, but yes as a design source.** The existing `graphify-out/` is
the right use of graphify-the-tool: a static snapshot of the codebase for AI coding assistants.
That is unrelated to the note DB.

For the note DB, **port the algorithms, not the tool**:

1. ✅ **Adopt Leiden community detection** on `wiki_links` (nightly job) — auto-discover topical
   entity communities, expose as `community_id` on entity pages.
2. ✅ **Adopt centrality scoring** (PageRank) for entity importance — better ranking than raw
   mention count.
3. ✅ **Adopt the static-snapshot pattern** — produce `wiki_graph_snapshot.json` nightly with
   communities + god nodes + hyperedges, serve as the LLM routing index (the missing
   `index.md` from Section 1). This is the single most impactful change to enable LLM-driven
   retrieval without full-table scans.
4. ✅ **Adopt confidence-tagged edges** — add `confidence` and `confidence_score` to
   `wiki_links` for the eventual mix of strict and inferred relationships.
5. ⚠️ **Optionally adopt LLM hyperedge extraction** — high value (auto-discovers new supply
   chain / theme pages), but requires careful prompt design and human review before
   materializing as wiki pages. Defer until communities + centrality are in place.
6. ❌ **Do not run graphify at request time** against the wiki — its model is batch, ours is
   streaming.

This makes the system **a true Karpathy LLM wiki**: persistent compounding pages (already have),
graph edges between them (already have), nightly community + centrality computation (port from
graphify), and a single LLM-readable snapshot artifact (port from graphify's `GRAPH_REPORT.md`)
that lets the LLM route without scanning the whole corpus.

---

## 7. Priority Order

Given current corpus size (hundreds to low thousands of episodes) and the platform roadmap:

1. **Now:** Tier 1A–C (SQL-side filtering + stats SQL aggregates) — eliminates O(n) scans,
   unblocks growth to 50k+ episodes, zero new infrastructure.

2. **Before 10k episodes:** Tier 1D (stats caching) + Tier 2F (improved LLM routing index) —
   protects the API under load and gives LLM agents a clean navigation surface.

3. **Before semantic search features ship:** Tier 2E (full-text search) — lets the platform
   webui expose a keyword search box without needing an embedding pipeline.

4. **When "related episodes" / similarity features are needed:** Tier 3H–I (pgvector +
   GraphRAG) — at this point the investment is justified by the product need.

---

## 8. Quick Reference — Retrieval Strategy by Scale

| Corpus size | Retrieval approach | Infrastructure |
|-------------|-------------------|----------------|
| < 1,000 pages | LLM reads full index (`index.md`) + direct slug lookups | None |
| 1,000–50,000 pages | SQL-side filtering + full-text search + LLM routing index | Postgres only |
| 50,000–500,000 pages | SQL + full-text + keyset pagination + stats materialized views | Postgres only |
| 500,000+ pages | pgvector HNSW semantic search + GraphRAG on wiki_links | Postgres + pgvector |

---

## Sources

- [Karpathy LLM-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Beyond RAG: Karpathy's Wiki Pattern Builds Knowledge That Compounds](https://levelup.gitconnected.com/beyond-rag-how-andrej-karpathys-llm-wiki-pattern-builds-knowledge-that-actually-compounds-31a08528665e)
- [LLM Wiki — Karpathy's Local Knowledge Base Setup](https://www.kunalganglani.com/blog/llm-wiki-karpathy-local-knowledge-base)
- [LLM Wiki v2 — extending Karpathy's pattern with agentmemory lessons](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2)
- [What Is the LLM Knowledge Base Index File?](https://www.mindstudio.ai/blog/llm-knowledge-base-index-file-no-vector-search)
- [Graph RAG vs Vector RAG for Agent Memory 2026](https://agentmarketcap.ai/blog/2026/04/07/graph-rag-vs-vector-rag-agent-memory-neo4j-pgvector)
- [GraphRAG on Postgres: A Builder's Guide](https://medium.com/@duckweave/graphrag-on-postgres-a-builders-guide-1c6d2ecf2eed)
- [Build a RAG System with pgvector on Managed PostgreSQL (2026)](https://danubedata.ro/blog/pgvector-rag-managed-postgres-2026)
- [Beyond Vector Databases: RAG Without Embeddings](https://www.digitalocean.com/community/tutorials/beyond-vector-databases-rag-without-embeddings)
- [Why LLMs Fail and How Knowledge Graphs Save Them](https://medium.com/@visrow/why-llms-fail-and-how-knowledge-graphs-save-them-the-complete-guide-6979a564c1b8)
