# Weekly Threads editorial

The scheduled `weekly_movers` slot now requests a sourced editorial carousel instead
of the mention-count caption and leaderboard image. Its format ID, week-based ledger
key and cooldowns remain unchanged. This document describes the implementation;
live model quality and rendered-layout validation are pending the evaluation report.

## Production path

`scheduled_social_worker` → `social_formats.select_weekly_movers()` → authenticated
`POST /api/podcast/weekly-editorial` → writer, evidence review and Marp rendering →
three public image URLs → `ThreadsService.publish_carousel()`.

The backend publishes only a matching-week bundle containing a caption and three
distinct HTTPS images. The weekly page link is the first reply. The pipeline endpoint
generates and stores media but does not publish to Threads; publication remains behind
the backend's existing ledger claim. Failed generation, insufficient source material,
failed review or incomplete media skips the weekly draft. There is no leaderboard or
generic-copy fallback. Other eligible formats may still fill the scheduled slot.

## Sources and dates

The selector uses the last completed Monday–Sunday week in `Asia/Taipei`, including
the ISO week-year. It loads the release-scoped episode list, applies the allowed
podcast names, then hydrates only that week's summaries with the existing episode
service. Edited summaries take precedence over original summaries.

Publication dates come from `released_at_ms`, converted to Taipei time, or an exact
`spotify_release_date`. Ingestion timestamps never establish eligibility. Hydrated
details are checked again for programme identity and publication date.

The request contains `week`, `start`, `end` and `episodes`. Each episode supplies
`episode_id`, `podcast_name`, `title`, `date` and `summary`. Input is bounded to
3–80 episodes, 100–24,000 characters per summary and 240,000 summary characters in
total. Summaries are not silently truncated. The pipeline verifies week boundaries,
unique IDs and source dates. The backend owns the deployment's programme allowlist;
the endpoint trusts its authenticated caller to supply that scope.

The backend sends `X-API-Key` using its configured podcast API credential. The
pipeline endpoint uses the existing `verify_api_key` dependency. The HTTP bridge has
a 300-second timeout and a 5-second connection timeout.

## Content and review gates

The writer produces a 250–350-character Traditional Chinese caption and exactly
three distinct cards. Each card contains two attributed claims with evidence excerpts
and a substantive synthesis tied to those claims. Structural validation checks text
budgets, source references, quoted evidence and generic observation phrases.
An independent review call receives the source material and draft to assess support
for the claims and synthesis.

There is **one repair total**, shared across structural and semantic failures. The
longest path is writer → reviewer → repair → independent re-review: at most four
logical model stages, separate from bounded transport retries. A failed repair or
review rejects the draft. A structural failure that consumes the repair does not
permit another repair after review.

Explicit `weekly_copy_writer_model` configuration or `WEEKLY_COPY_WRITER_MODEL` selects
the weekly role; otherwise generation uses the configured `social_copy_writer` role.
The reviewer is a separate call, not a promise that a different model is used.

Model results are cached by pipeline version, stage, resolved model and full messages,
with file locks and atomic replacement. The endpoint's cache directory defaults to
`.weekly-editorial-cache` under the media root; `WEEKLY_EDITORIAL_CACHE_DIR` overrides
it. Repeated identical previews reuse model results. Preview also reuses its selected
draft when showing what would publish. Rendering can run again, while media uses
content-versioned paths with `skip_existing=True`.

## Card contract

The deck reuses the existing `tinboker-cards` Marp theme and renders three
1080×1080 PNGs. Every card shows `週報 Wxx｜MM/DD–MM/DD`, two programme/date source
labels, and a visually separated highlighted panel named **聽播客觀點**, with the
qualifier **綜合節目內容**. The panel identifies the brand's synthesis separately from
what the programmes said. There is no empty cover card or optional filler observation.

## Local generation without publication

Prepare a JSON request using the input contract above. From `pipelines/`, run:

```sh
uv run --package tinboker-podcast python -m podcast.weekly_editorial \
  --input /tmp/weekly-sources.json \
  --out-dir /tmp/weekly-editorial-preview \
  --cache-dir /tmp/weekly-editorial-cache
```

The CLI may incur model costs and requires the configured model credentials. Rendering
uses `MARP_SERVICE_URL` (default `http://localhost:5004`). It writes `editorial.json`,
`weekly.md`, `theme.css` and `weekly.001.png` through `weekly.003.png` locally; it never
uploads media or publishes. `--no-render` runs copy/review and writes the deck without
requesting PNGs. `--candidate-file` reuses a saved model candidate for bounded repair
evaluation; it still validates and reviews the candidate against the supplied sources.

The authenticated HTTP endpoint differs from this CLI: it uploads generated images.
Use the CLI for local editorial and layout review, and evaluate multiple real weeks
before claiming equivalent quality to the accepted sample.

## Validation recorded on 2026-09-28

- 28 backend selector/publisher tests and 52 pipeline/editorial/rendering tests passed;
  Ruff and `git diff --check` passed.
- W38 used 36 public episode summaries. The final field-level reviewer rejected a
  previously generated draft, the single model repair corrected it, and a new review
  accepted it. An independent source-fidelity review accepted the corrected claims.
- W39 used 35 public episode summaries in a fresh writer-to-render run. Its final
  draft passed the ten-field review and independent source-fidelity review.
- Both runs used the configured social-copy model, `openrouter:google/gemini-3.7-flash`,
  and the repository's local HTTP Marp service to produce three 1080px-square PNGs.
  All six cards and a maximum-density fixture were visually inspected for overflow.
- No test published a Threads post or uploaded media. Generated model caches, full
  source summaries and PNGs are local evaluation artifacts, not committed fixtures.

These runs establish end-to-end capability on the tested material, not a guarantee
that every future week passes. Insufficient or rejected output is skipped. Fidelity
is checked against supplied episode summaries, not independent company filings.
