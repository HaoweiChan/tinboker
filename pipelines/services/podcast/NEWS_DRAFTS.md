# English news → reviewed Threads drafts

The existing six-hourly news ingest now ends with an optional draft step, even if
some individual articles failed. It reads persisted `news_article` pages referenced
by the current feed window, reuses this CLI's unchanged prefilter/Jev/writer gates,
and hands at most one zh-TW draft to the platform admin API. Nothing publishes
automatically. The standalone CLI below remains a local review/evaluation tool.

## Scheduled draft lane

Set `NEWS_THREADS_DRAFTS_ENABLED=true` in the existing news service environment.
The lane needs `TINBOKER_ADMIN_API_URL` pointing to the admin-serving backend
(staging, since production omits admin routes), `TINBOKER_SOCIAL_TOKEN`,
`OPENROUTER_API_KEY`, and the existing `WIKI_DATABASE_URL`. Secrets use the existing
bootstrap/environment mechanism. No new systemd unit or timer is required. The existing pipeline deployment installs
both `tinboker-podcast` and `tinboker-news` into the same workspace virtualenv, which
`run_news.sh` already uses; no additional package installation is needed.
`NEWS_THREADS_DRAFTS_CACHE_DIR` optionally selects a writable persistent cache;
the default is `.cache/news-threads-drafts` relative to the news service directory.
Jev requests can reuse this cache across runs. Scheduled writer requests include
the current run timestamp, so a later retry after a failed screenshot/handoff can spend
one writer call again; the six-Jev/one-writer per-run ceiling still applies.
A restart/reload of the existing service configuration is sufficient after deploy.

The feed/region metadata determines language. Only a raw feed `published` value
with an explicit timezone sets `publication_verified`; updated dates, missing dates,
and synthesized wiki dates cannot pass. Existing rows without this provenance are
skipped; there is no metadata backfill. Candidate lookup is bounded to articles
still present in this run's RSS window, including already-ingested unchanged pages.
Ingest also records the source lead image as `image_url` (`og:image`, then
`twitter:image`, then an RSS image). Drafts no longer use it: a lead photo is often
unrelated to the one detail a post is about.

**Media is a screenshot of the article at the quoted passage.** The writer returns
one or two `highlights`: verbatim source quotes (15-140 characters, validated as exact
substrings of the source text) that carry the post's main number or action.
`news/screenshot.py` opens the article in headless Chromium at a 600x750 viewport
(2x, so a 1200x1500 image), dismisses a consent wall, scrolls to the first quote,
removes scroll-triggered modals and pinned sign-up bars, frames the passage together
with the nearest photo above it when both fit, and draws a hand-style highlighter
swipe over each quote. It raises, and no draft is made, when the browser is missing,
a quote is not on the page, nothing could be highlighted, or something still covers
the passage. It drives the system `chromium` over DevTools with `websockets`; when
the run is root the browser runs as `nobody` with its sandbox on. The host needs the
`chromium` package (plus `fonts-liberation`); `NEWS_SCREENSHOT_BROWSER` overrides
the binary.

Before paid calls, the pipeline reads `/api/admin/promo/news-drafts/state`, checking
the daily allowance and stored article IDs, canonical URLs, and normalized content
hashes. Missing credentials/history fail closed. Backend creation enforces at most
two news drafts per Asia/Taipei day and deduplicates again before saving.
A hidden tombstone retains source identity and the daily count after publication
or deletion. The `news_source` column is added idempotently at backend boot; no
manual SQL is required.

`POST /api/admin/promo/news-drafts` takes that screenshot as `image_png_base64`,
checks it is a PNG of at most 4 MiB, stores it in the permanent promo media store and
creates a `PromoDraft` with Threads selected and the source URL as its first comment.
The backend fetches nothing. A bad or missing image returns `no_image` and creates no
draft or notification.
Existing admin notifications link
to the promo editor; the owner reviews/edits and explicitly publishes there.
Recipients must have a registered user account whose email appears in the backend
`ADMIN_EMAILS` configuration. Without a registered admin, creation skips. If the database/notification transaction
fails after storage, an unreferenced screenshot can remain in the media store;
the draft and notification roll back together.
The local CLI's `report.json` is an intermediate writing artifact, not an admin draft.

## Standalone CLI

Run from `pipelines/`:

```sh
# Free prefilter only; no credentials or model calls.
uv run --package tinboker-podcast python -m podcast.content_builder.news_drafts \
  --input /tmp/news.json --out /tmp/news-drafts

# Select with Jev, then draft at most one article using DeepSeek V4 Pro.
uv run --package tinboker-podcast python -m podcast.content_builder.news_drafts \
  --input /tmp/news.json --out /tmp/news-drafts --select-with-jev

# Alternatively, manually select a record that passes the same prefilter.
uv run --package tinboker-podcast python -m podcast.content_builder.news_drafts \
  --input /tmp/news.json --out /tmp/news-drafts --article-id example \
  --writer-model deepseek/deepseek-v4-pro
```

Paid modes use existing `shared.secrets.bootstrap()` for `OPENROUTER_API_KEY`.
Supply credentials through environment/Secret Manager, never input JSON. Jev uses
OpenRouter's [Decisions API](https://openrouter.ai/blog/tutorials/how-to-use-jev/)
with the model ID `typesafe/jev-1.13` and the shared `llm.decide()` adapter.
OpenRouter may roll this ID to a dated snapshot; cache keys use the requested ID,
so use a fresh output directory when evaluating a newer snapshot.

## Input contract

```json
{
  "already_posted_ids": [],
  "articles": [{
    "id": "example",
    "language": "en",
    "title": "A concrete company announcement",
    "url": "https://example.com/announcement",
    "published_at": "2026-10-02T08:00:00Z",
    "publication_verified": true,
    "paragraphs": [{"id": "0", "text": "Replace with full extracted English source text of at least 100 characters"}],
    "screenshot_path": "/absolute/path/source.png"
  }]
}
```

`language` and `publication_verified` are caller-verified metadata, not inferred
from a headline or guessed by a model. Keep paragraph IDs unique and the source
text unchanged. The CLI rejects dates without timezones, future dates, records
older than 48 hours, non-English records, short sources, and duplicates by canonical
URL or whitespace-normalized content. Include previously posted source records
and their IDs to deduplicate against them; no remote posting history is read.
The default clock is UTC now; `--as-of` provides a timezone-aware replay timestamp.

At most six eligible records enter selection. Jev answers relevance,
specificity and market consequence in a single call per article. All three probabilities must be at least 0.8;
uncertain records are skipped, malformed answers stop the run. This threshold is
an initial review gate, not a measured quality guarantee. The highest minimum
probability wins, with newest-first ties. Jev does not infer publication dates or
claim that Taiwan has not covered a story. Exact deduplication does not detect
semantically identical stories from different publishers.

## Limits and review

There are at most seven paid attempts per run (six Jev, one writer), with 24 KB
source / 32 KB serialized request limits, a 2,048-token writer output cap, and
30/60-second Jev/writer timeouts. No automatic retries or fallback model calls.
The writer uses the existing social-copy role with an invocation-local model
override. A provider requiring reasoning may fail; inspect rather than silently
spending on a fallback.

Requests/results, including failures, are cached under the output directory by
payload hash, including model and prompt. Reusing the same input, `--as-of`, model,
and output directory makes reruns free. Use a separate output directory for each
concurrent run. Failed cache entries require deliberate removal before retrying.
`report.json` records cache hits, duration, and available usage. The shared Jev
adapter returns only its answer map, so Jev usage/cost metadata is not available
in this CLI report; writer usage metadata is retained when the provider supplies it.
Only the article title and paragraphs are sent to Jev; local IDs, URLs, and paths
stay outside the request. For Jev, the 32 KB cap measures the ASCII-escaped JSON body sent on the wire;
for the writer it bounds the cached input payload, excluding SDK-added parameters.

Every output has `publish_ready: false` and requires human fact review. Paragraph
IDs prove provenance membership, not factual correctness. Check numeric qualifiers
such as “up to”, benchmark scope, event dates versus page dates, and planned versus
available products. The supplied screenshot path is preserved and checked for file
existence; no screenshot is fabricated or captured automatically. The URL stays in
`first_comment`, outside `post`. A missing screenshot never makes a draft ready.

Offline tests mock paid calls. A separate seven-case live selector pilot through
OpenRouter matched its frozen labels (three real articles and four synthetic
controls); it bypassed the CLI freshness prefilter and writer, so it does not
validate the end-to-end flow or calibrate the 0.8 threshold. Treat this as an
initial integration check, not a quality benchmark. The standalone CLI remains a
review/evaluation tool; the scheduled wrapper hands its validated prose to the
media-required admin draft endpoint.

```sh
uv sync --all-packages --group dev
uv run --no-sync pytest services/podcast/tests/unit/test_news_drafts.py -q
```
