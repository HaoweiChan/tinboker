---
name: pipeline-debug
description: >-
  Debug and A/B-test the podcast content pipeline (pipelines/services/podcast) offline —
  run one stored episode through the real extractor→writer→markdown pipeline with any
  OpenRouter model, score JSON reliability / Traditional-Chinese fidelity / ticker+tag
  linking / chapter consolidation, find genuinely-failed (placeholder) episodes, and
  backfill them. Use when changing the pipeline LLM/model, diagnosing bad or
  placeholder summaries, or evaluating a new OpenRouter model.
---

# Pipeline debug & model A/B

The content pipeline lives in `pipelines/services/podcast`. Episodes are LangGraph runs:
`extract_events → cluster_sentences → consolidate_chapters → write_article →
transform_to_markdown` (+ tickers / marp / key-insights branches). All roles call
`invoke_json` in `src/podcast/content_builder/llm.py`, which builds **one OpenRouter
client** (`ChatOpenAI` at `https://openrouter.ai/api/v1`). There is no Google/Gemini
code path anymore — every model is an OpenRouter id, default `deepseek/deepseek-v4-pro`.

## Hard-won gotchas (read first)

- **Reasoning models truncate JSON.** deepseek-v4-flash / minimax-m3 / hy3-preview emit
  hidden chain-of-thought that eats the `max_tokens` budget, so the JSON truncates
  mid-array → `invoke_json` fails after retries → the episode falls back to a placeholder
  summary. `get_model` passes `extra_body={"reasoning": {"enabled": False}}` to prevent
  this. If you test a new model and it "fails JSON," check the log for `reasoning_tokens`
  and `length limit was reached` before blaming the model.
- **The live model is the DB override, not the code default.** `llm.py` reads
  `pipeline_config_overrides` (Postgres, namespace `default`) FIRST; the `_DEFAULT_MODEL`
  constant is only the fallback when that table is empty. After changing the default,
  confirm the DB override isn't pinning an old model (it's set via the admin config plane).
- **TW-fidelity metrics are noisy.** An opencc `s2t` diff flags `台→臺`, `群→羣`, `才→纔`
  — all standard, correct Taiwan forms (false positives). `疲` is identical in both
  scripts. Judge Traditional-Chinese quality by reading, not by the raw counts.
- **No `timeout` on macOS.** Use a bash watchdog (`run_to`) — see the harness below.
- Run everything from the `pipelines/` dir with
  `uv run --package tinboker-podcast …` (the workspace resolves `shared`, `opencc`, the
  Firestore client). `uv` is at `/Users/willychan/.local/bin/uv`.

## Env needed

```bash
export OPENROUTER_API_KEY=$(gcloud secrets versions access latest \
  --secret=OPENROUTER_API_KEY --project=gen-lang-client-0901363254)
export FIRESTORE_DATABASE_ID=graphfolio-db
export GCP_PROJECT_ID=gen-lang-client-0901363254   # ADC via `gcloud auth` for Firestore reads
```

## 1. Run one episode through the real pipeline (offline, no writes)

`scripts/run_episode_offline.py` (in this skill dir) sets every `*_MODEL` env to the
chosen OpenRouter model BEFORE importing `llm`, loads the episode transcript from
Firestore, runs extractor→…→markdown, and prints/saves the result. **Writes nothing to
Firestore/GCS.**

```bash
cd pipelines
uv run --package tinboker-podcast python \
  ../.claude/skills/pipeline-debug/scripts/run_episode_offline.py \
  <episode_id> "<podcast_name>" deepseek/deepseek-v4-pro /tmp/out.json
# -> /tmp/out.json (metrics) + /tmp/out.md (full summary to read)
```

Metrics captured: `json_ok`, `chapter_count`/`writer_section_count` (consolidation —
should scale ~1 per 5 min, floor 4, cap 12), `ticker_links`/`tag_links`,
`simplified_glyphset_count`/`opencc_changed_count` (treat as noisy — read the `.md`),
`runtime_s`, `prompt_tokens`/`completion_tokens` (× OpenRouter price = per-episode cost).

## 2. A/B several models

Loop §1 over models **sequentially** (parallel load causes spurious JSON failures), each
under a `run_to 420` watchdog. Resolve exact OpenRouter ids and pricing from
`https://openrouter.ai/api/v1/models`. Score the big ticker-heavy episode
(`Gooaye_a97bb9b3a55e0cf5`, "Gooaye 股癌") AND a short one — a model can ace tags on a
short episode yet collapse on tickers on a long one (hy3-preview did: 23 tags → 1 ticker).

## 3. Find genuinely-failed episodes (BEFORE backfilling — saves cost)

Don't reprocess working episodes. A "failed" episode has an empty/placeholder summary.
The `podcast_regen` MCP exposes this directly:

```
list_regen_candidates(only_placeholder=True)   # episodes whose summary is empty/placeholder
```

Or check Firestore: `summary_content` empty, or contains a placeholder marker
(`摘要生成中`, `內容生成中`, `生成失敗`, `摘要產生中`, …), or `key_insights` empty.
Verify each candidate is really broken (read its current `summary_content`) before running
the pipeline on it.

## 4. Backfill the failed episodes (real pipeline, writes to PROD)

Backfill = run the REAL pipeline (new model, real OpenRouter call — cheap $, no
hand-authoring) on the confirmed-failed episodes and write to Firestore. Use
`main.py --config podcasts_tw.json --fill-limit N` (sweeps unprocessed/placeholder
episodes), or the `podcast_regen` MCP `commit_regen` per episode. This writes to the
**shared production Firestore** (`graphfolio-db`) + GCS and busts caches — preview first.

## Reference

A/B harness pattern, per-model results, and the watchdog live alongside this skill in
`scripts/`. Model decision (2026-06): `deepseek/deepseek-v4-pro` — best ticker linking,
meaningful tags, concise, clean TW, fully open (no Google dependency). Eliminated:
hy3-preview (ticker collapse), minimax-m3 (drops tags), v4-flash (weak tags), gemini-2.5-flash
(over-tags with invented slugs + Google dependency).
