# Content-Regeneration MCP server

A stdio MCP server (`content-regen`) that lets a capable agent **re-generate an
already-transcribed episode's content using the pipeline's real prompts** — the
agent itself plays the LLM roles (replacing the cheap `invoke_json` call), and the
server runs the deterministic glue and persists everything through the pipeline's
existing write paths.

## Why this stays consistent with the automated pipeline

`content_builder/graph.py` runs `app.invoke()` synchronously and can't pause to
round-trip to an MCP client mid-node, so the DAG is re-expressed as a host-driven
sequence (`regen/orchestrator.py`). **Prompt rendering, output parsing, and the glue
all reuse the same node functions** (`build_messages` / `postprocess`,
`cluster_sentences`, `transform_to_markdown`, `derive_tags_tickers`, `convert_marp`,
the `ticker_insights` exporter) the automated `run_pipeline` uses — so the agent path
is byte-identical to a real pipeline run for the same inputs. This is enforced by
`tests/test_regen_orchestrator.py`:
- `test_prompt_parity_*` — the rendered prompts match each node's.
- `test_episode_doc_parity_pipeline_vs_regen` — for identical per-step outputs,
  `run_pipeline` and the regen orchestrator assemble **identical** episode-doc fields.

**Whisper/transcription is out of scope** — the episode must already have a stored
transcript. Prompts are read live from `content_builder/prompts/*.yaml` (the same
files the admin "Prompts" editor writes).

## Tools & flow

| Tool | Purpose |
|---|---|
| `list_regen_candidates` | Transcribed episodes with missing/placeholder content |
| `start_regen` | Open a draft → returns the first (extractor) **full prompt** |
| `get_role_prompt` | A step's full `system`+`user` prompt **+ `output_schema` + `example`** |
| `submit_role` | Submit your JSON (validated); returns a lightweight `next` pointer |
| `preview_regen` | Show exactly what will be written (no write) |
| `commit_regen` | Persist to Firestore + refresh the platform caches |
| `discard_regen` | Drop the draft |

Steps — required: `extractor → writer → key_insights → ticker_extractor`;
optional: `marp_writer` (episode slides), `ticker_marp_writer` (ticker slides).

### Producing each step's output (least effort, no source-reading)

- Every prompt carries an **`output_schema`** (exact field names + enums) and a tiny
  **`example`** — follow them; you never need to read pipeline source for shapes.
- `submit_role` **validates** your JSON and returns an actionable error if the shape is
  wrong (so you fix it immediately, not at commit).
- `submit_role`'s response is **lightweight**: `next` is just `{step, instructions,
  output_schema, example}` — NO transcript body. Fetch the heavy prompt for that step
  with `get_role_prompt` only when you're ready to fill it. (Keeps responses small
  regardless of transcript length.)
- **Write all Chinese as literal UTF-8** — never `\uXXXX` escapes.
- **Tags are ASCII slugs.** Use `[顯示名](#tag:Slug)` — the `#tag:` slug must be ASCII
  (`[A-Za-z0-9_]`); non-ASCII slugs are silently dropped. Chinese goes in the display
  text only. Prefer a slug from the curated vocabulary in
  [`content_builder/tag_vocabulary.py`](../content_builder/tag_vocabulary.py)
  (injected into the writer prompt) so episodes about the same theme cluster on the
  same tag — free-text Chinese tags fragment clustering (美股 vs 美國股市, 半導體 vs 晶片…).

## Run

Registered in the repo-root `.mcp.json` as `podcast_regen`:

```jsonc
"podcast_regen": {
  "type": "stdio",
  "command": "uv",
  "args": ["run", "--directory", "pipelines", "--package", "tinboker-podcast",
           "python", "services/podcast/regen_mcp.py"],
  "env": {
    "GCP_PROJECT_ID": "gen-lang-client-0901363254",
    "FIRESTORE_DATABASE_ID": "graphfolio-db",
    "TINBOKER_PLATFORM_API_URL": "https://api.tinboker.com"
  }
}
```

| Env var | Purpose |
|---|---|
| `GCP_PROJECT_ID`, `FIRESTORE_DATABASE_ID` | Firestore (episode read + write) — `graphfolio-db` is the **shared production** store |
| `TINBOKER_PLATFORM_API_URL` | Backend base URL for cache invalidation on commit. Points at the env whose caches should refresh — defaults to **prod** because commit writes the shared prod Firestore |
| `TINBOKER_REGEN_WORK_DIR` | Where per-episode working drafts are persisted (default: system temp) |

## Persistence & cache on `commit_regen`

> ⚠️ Writes to the **shared production Firestore** (`graphfolio-db`) and, by default,
> busts the **production** caches. Run `preview_regen` first.

- **Episode doc** (Firestore merge): only the fields whose steps you completed
  (`summary_content`, `key_insights`, `tags`, `related_tickers`, `events_markdown`,
  `marp_markdown`, `ticker_marp_markdown`, `social_cards`).
- **Rich ticker sentiment** → `ticker_insights/{episode_id}/tickers/{ticker}` via the
  pipeline's exporter.
- **Cache** → one PATCH to `TINBOKER_PLATFORM_API_URL` busts the **episode Redis
  cache**, the **`ticker_insights:by_ticker` sentiment cache** (when `related_tickers`
  changed), **and** the **Cloudflare edge** for that env's API host — so the regen
  shows immediately, no manual SSH/CF steps. The result reports `cache_refreshed`
  `{via, surfaces}`; if the bust is disabled/unreachable it returns
  `manual_invalidation` with the exact copy-paste commands instead.
- PNG social-card rendering stays in the normal pipeline (only the slide *markdown*
  is saved here).

## Tests

```bash
cd pipelines
uv run --package tinboker-podcast --with pytest python -m pytest \
  services/podcast/tests/test_regen_orchestrator.py -q
```
