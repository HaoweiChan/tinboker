# English news → local Threads drafts

This opt-in CLI accepts extracted English source records, filters them before paid
calls, optionally asks TypeSafe Jev two narrow questions through OpenRouter, and writes one zh-TW
draft with its original URL as a separate first comment. It does not fetch sources,
translate the whole ingestion feed, schedule posts, write databases, or publish.
Existing podcast ingestion and production model defaults are unchanged.

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
with the pinned model ID `typesafe/jev-1.13` and the shared `llm.decide()` adapter.

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

At most six eligible records enter selection. Jev answers both relevance and
specificity in a single call per article. Both probabilities must be at least 0.8;
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
initial integration check, not a quality benchmark. This CLI is a
review/evaluation tool, not a production publishing path.

```sh
uv sync --all-packages --group dev
uv run --no-sync pytest services/podcast/tests/unit/test_news_drafts.py -q
```
