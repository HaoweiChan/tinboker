# Content API roadmap — what the TinBoker webui needs from this backend

`tinboker-agents` is the content/infra backend; the **TinBoker「聽播客」webui lives in a separate
"platform" repo**. This doc records what that frontend consumes, what this repo exposes today, the
gaps, and the plan to close them. It is the single place to look when deciding what to build here.

## Ownership boundary

| The **platform repo** owns | This repo (`tinboker-agents`) owns |
|---|---|
| The webui, routing, theming, the「」logo | Content: episodes, summaries, entities, topics, supply chain |
| Users, follows, saved episodes, comments, notification prefs | Content-derived aggregates (mention counts, sentiment distributions) |
| Live market quotes (`price`, the `change` %) | Stable IDs the platform references: episode/entity/topic **slug**, show **name** |
| Mapping content → presentation (avatar `kind`/`initial`, `dist` bars) | Structured episode "detail" (bullets, chapters, clips) the pipeline produces |

## Gap analysis (design ↔ today ↔ gap)

1. **Episode feed** (Home `今天聽什麼`, cards): paginated, recency-sorted episodes with
   `{show, epNo, timeAgo, minutes, isNew, title, summary, tickers:[{sym,sentiment}], tags, commentCount}`.
   - *Have:* `episodes` in Firestore (title/show/number/created_time/urls); wiki episode pages with
     summary + tickers + tags + ticker-recommendations (which carry sentiment) — but as markdown, unsorted.
   - *Gap:* a `GET /api/episodes` (or `/api/wiki/feed`) returning a paginated, date-sorted episode
     list with structured fields (incl. per-ticker sentiment + duration). `commentCount` and `change` aren't ours.

2. **Episode detail page**: `{summary, bullets[], chapters:[{label,time}], clips:[{time,sentiment,quote,refs}],
   tickers:[{sym,sentiment,thesis}], tags, mp3Url, transcriptUrl}`.
   - *Have:* wiki episode body = summary + events timeline + ticker-recommendations table; GCS has
     mp3/transcript/summary; the pipeline keeps sentence-level timestamps in the transcript.
   - *Gap:* the content pipeline doesn't emit **key bullets**, **chapters with timestamps**, or
     **representative clips (timestamp + sentiment + quote + ticker refs)** — a `content_builder`
     enhancement + somewhere to store it, then surfaced via `GET /api/episodes/{slug}/detail`.

3. **個股 (ticker/entity) list + detail**: list of ~128 with
   `{sym, 中文 name, market(TW/US), recentMentions, sentimentDist:{bull,bear,neut}, price, change}`;
   detail adds a sentiment timeline `[{day,sentiment,podcaster,title}]` + related episodes + supply chain.
   - *Have:* wiki entity pages (id, `name` = the ticker symbol like "AAPL", entity_type, tickers; body
     = episode mentions + a "Ticker History" table date/sentiment/score/thesis); `wiki_links` (episode→entity);
     the KG service has supply-chain + real company names in `entity.props.name`.
   - *Gap:* (a) **Chinese display names + market + sector** — entity pages currently store the ticker
     symbol as the name; need a ticker registry. (b) **mention counts + sentiment distribution +
     last-mentioned-at** — aggregate from `wiki_links` + ticker recs. (c) the "Ticker History" table *is*
     the sentiment timeline, just needs to be served structurally, not parsed from markdown. (d)
     `price`/`change` = the platform's quote source.

4. **話題 (topics)**: `{tag, count, sentiment, weight}` + topic detail (related episodes).
   - *Have:* wiki topic pages + `wiki_links` (episode→topic). `count` = link count; `sentiment`/`weight` not computed.
   - *Gap:* an aggregation that returns count + dominant sentiment + normalized weight per topic.

5. **Home rail widgets**: `這幾天大家在聊` (top tickers, 7d mentions + sentiment dist),
   `本週更新最勤` (top shows, this-week episode count + delta), `今天的市場` (episodes today, tickers
   mentioned, overall sentiment + dist).
   - *Have:* the raw data (episode dates, `wiki_links`, ticker recs). *Gap:* aggregation endpoints —
     `GET /api/wiki/stats/{top-tickers,top-shows,pulse}` (or one `/api/wiki/dashboard`).

6. **節目 (shows) list + detail**: `{name, episodeCount, avgLen, blurb, followerCount}` + show detail.
   - *Have:* `GET /api/podcast/shows` (Firestore `podcasts`: name/thumbnail/publisher/description/total_episodes).
   - *Gap:* `avgLen` (compute from episode durations); `blurb` (`description` works). `followerCount` = platform.

7. **Search** (`搜尋集數、個股、節目`): full-text across episode titles/summaries + ticker names + show names.
   - *Have:* `GET /api/wiki/pages?q=` does frontmatter-contains only. *Gap:* Postgres `tsvector`
     full-text search over `wiki_pages` + ticker/show names (or hand to the platform).

8. **Sentiment, surfaced structurally** — per-episode-per-ticker sentiment exists only in the
   `ticker_recommendations` JSON (GCS) and a markdown table. *Gap:* store it structurally — a
   `sentiment` map in the wiki episode `frontmatter`, or a `context`/column on `wiki_links`, or a small
   `episode_ticker_sentiment` table — so feed/ticker endpoints don't parse markdown.

9. **Users / follows / comments / settings, and live quotes** — out of scope here; the platform repo
   owns them. This repo just exposes stable referenceable IDs (already true).

## Plan (A–F)

- **A. Episode feed + detail endpoints** — `GET /api/episodes` (paginated, date-sorted, structured)
  and `GET /api/episodes/{slug}/detail`. Backed by the wiki Postgres store (+ Firestore for show
  metadata). Depends on #8 (structured sentiment) and, for the rich detail, D.
- **B. Ticker registry** *(recommended first slice)* — Chinese names + market + sector, seeded once and
  used by `ingest_episode` when it creates/updates entity pages (so `wiki/entities/2330` gets
  `name: 台積電, market: TW` instead of `2330`). Add a `tickers.json` registry; have
  `shared.wiki_builder` consult it. *(Done — see Status below.)*
- **C. Aggregation/stats router** on the podcast service — `/api/wiki/stats/{top-tickers,top-shows,pulse,topics}`
  and per-entity aggregates (mention count, sentiment dist, last-mentioned-at). All from `wiki_pages` +
  `wiki_links` + ticker recs; no pipeline changes.
- **D. Content-pipeline enhancement** — have `content_builder` emit
  `{bullets[], chapters:[{label,start_ms}], clips:[{start_ms,sentiment,quote,ticker_refs}]}` from the
  timestamped transcript + extractor output; persist it (new wiki episode sections or a GCS `detail.json`);
  expose via A.
- **E. Full-text search** — `tsvector` columns on `wiki_pages`, a `GET /api/wiki/search?q=` endpoint.
- **F. Data-contract doc** — keep this file (and [docs/wiki-schema.md](wiki-schema.md)) current as the
  contract the platform team builds against.

**First slice:** B (small; unblocks real names everywhere) → C (high value; no pipeline changes) →
A's `GET /api/episodes` feed (with whatever sentiment we can derive) → keep F updated. D (chapters/clips)
and E (search) as a second pass since D touches the LLM pipeline.

## Status

| Item | Status |
|---|---|
| Wiki → Postgres store + `/api/wiki` routes | Done (see [docs/wiki-schema.md](wiki-schema.md)) |
| B — ticker registry | Done — `libs/shared/src/shared/data/tickers.json` (~60 tickers) + `shared.tickers`; `ingest_episode` canonicalizes symbols and stamps entity pages with zh `name` / `market` / `sector` / `entity_type`; `services/podcast/scripts/reenrich_entities_from_registry.py` backfills those onto existing pages (re-run after extending the registry). The wiki Postgres migration has been executed on the VPS (DB + `WIKI_DATABASE_URL` secret + schema + backfill + re-enrich done — 51/59 entity pages enriched; ~8 long-tail/noise symbols still uncovered: `009150, 3548, 6324, 8035, elon, kem, openai, spcx`). `/api/wiki` is live in prod (`{"status":"healthy","backend":"postgres"}`). Follow-up: cover the 8 bare symbols (or mark them noise); consider a `GET /api/wiki/tickers` registry dump. |
| C — stats/aggregation router | Done — `shared.wiki_builder.stats` + `/api/wiki/stats/{top-tickers,top-shows,topics,pulse,dashboard,entity/{slug}}` on the podcast service. Episodes now carry a structured `ticker_sentiment` map in frontmatter (`render_episode_page`); `services/podcast/scripts/backfill_ticker_sentiment.py` parses the existing markdown rec-tables to fill it for old pages. Aggregates: top tickers/shows/topics by mention count in a window + sentiment split, daily pulse, per-entity rollup (mentions / last-mentioned-at / sentiment / recent episodes). No prices/`change` % — that's the platform's quote source. |
| A — episode feed + detail | Done — `shared.wiki_builder.episode_view` + `GET /api/wiki/episodes` (date-desc feed, filter by `podcast`/`ticker`/`tag`, paginated) and `GET /api/wiki/episodes/{slug}` (full detail: summary, events, parsed ticker recommendations, related entity/topic links, source urls). `bullets`/`chapters`/`clips` are returned as empty placeholders pending slice D; `duration_minutes` is in the response shape but only populated for episodes ingested with it. (Lives under `/api/wiki/episodes` to keep all the content-read API together and avoid collision with the existing `/api/episodes/*` rerun routes.) |
| D — pipeline emits bullets/chapters/clips + zh tags | Not started |
| E — full-text search | Not started |
