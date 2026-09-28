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
| `commit_regen` | Persist to Postgres and local media storage; refresh platform caches |
| `discard_regen` | Drop the draft |

Steps — required: `extractor → writer → key_insights → ticker_extractor → marp_writer`;
optional: `ticker_marp_writer` (ticker slides).

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

The launcher lives at `mcp-servers/podcast-regen/server.py` and is registered as
`podcast_regen` in both repo-root `.mcp.json` (Claude) and `.codex/config.toml`
(Codex):

```jsonc
"podcast_regen": {
  "type": "stdio",
  "command": "uv",
  "args": ["run", "--directory", "pipelines", "--package", "tinboker-podcast",
           "python", "../mcp-servers/podcast-regen/server.py"],
  "env": {
    "GCP_PROJECT_ID": "gen-lang-client-0901363254",
    "TINBOKER_PLATFORM_API_URL": "https://api.tinboker.com",
    "PIPELINE_LLM_MODEL": "openrouter:deepseek/deepseek-v4-pro"
  }
}
```

| Env var | Purpose |
|---|---|
| `EPISODE_DATABASE_URL` | Required Postgres connection for episode reads and writes; supplied by the local environment or secrets bootstrap |
| `MEDIA_STORAGE_ROOT`, `MEDIA_PUBLIC_BASE` | Media directory and public URL. `commit_regen` requires the mounted VPS tree at `/srv/tinboker-media`; a local fallback supports preview only |
| `GCS_BUCKET_NAME` | Legacy directory name (`graphfolio-articles`) under the media root, not a GCS bucket |
| `GCP_PROJECT_ID` | Secret Manager fallback in pipeline bootstrap; no Firestore access |
| `PIPELINE_LLM_MODEL` | Model used by inline pipeline verification steps |
| `TINBOKER_PLATFORM_API_URL` | Backend base URL for cache invalidation on commit; registered as the production API |
| `TINBOKER_WRITE_TOKEN` | **Required for the commit cache-bust.** The content-writer service token the backend's `PATCH /api/podcast/.../episodes/...` accepts. Without it the PATCH 403s and Redis/CDN stay stale until TTL. Not hardcoded in `.mcp.json` (it's a secret) — inherited from the shell/GSM env |
| `TINBOKER_REGEN_WORK_DIR` | Where per-episode working drafts are persisted (default: system temp) |

## Persistence & cache on `commit_regen`

> A local checkout can run `preview_regen`, but `commit_regen` must run on the VPS
> with `/srv/tinboker-media` mounted. It refuses to write Postgres when the media
> directory is missing or points elsewhere. The registered cache target is production.
> Run `preview_regen` first and check `EPISODE_DATABASE_URL` before committing.

- **Episode doc** (Postgres JSONB merge): only the fields whose steps you completed
  (`summary_content`, `key_insights`, `tags`, `related_tickers`, `events_markdown`,
  `marp_markdown`, `ticker_marp_markdown`, `social_cards`).
- **Media artifacts** (rewrite): the backend serves `marp`/`events`/`ticker_marp` (and
  `summary`) by hydrating each `*_content` field from its `*_url` when the inline
  doc field is empty. Commit rewrites those files and repoints the doc's `*_url`
  at the fresh upload. The report calls this `gcs_content_uploaded` for legacy
  compatibility. Without this the page keeps rendering the old slides/events
  even though the doc fields changed.
- **Rich ticker sentiment** → Postgres through the pipeline's exporter.
- **Cache** → one PATCH to `TINBOKER_PLATFORM_API_URL` (authenticated with
  `TINBOKER_WRITE_TOKEN`) busts the **episode Redis cache**, the
  **`ticker_insights:by_ticker` sentiment cache** (when `related_tickers` changed),
  **and** the **Cloudflare edge** for that env's API host — so the regen shows
  immediately, no manual SSH/CF steps. The result reports `cache_refreshed`
  `{via, surfaces}`; if the token is missing or the bust is disabled/unreachable it
  returns `manual_invalidation` with the exact copy-paste commands (including the
  `Authorization` header) instead.
- PNG social-card rendering stays in the normal pipeline (only the slide *markdown*
  is saved here).

## Tests

```bash
cd pipelines
uv run --package tinboker-podcast --with pytest python -m pytest \
  services/podcast/tests/test_regen_orchestrator.py -q
```
