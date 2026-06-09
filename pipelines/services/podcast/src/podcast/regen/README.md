# Content-Regeneration MCP server

A stdio MCP server (`content-regen`) that lets a capable agent **re-generate an
already-transcribed episode's content using the pipeline's real prompts** — the
agent itself plays the LLM roles (replacing the cheap `invoke_json` call), and the
server runs the deterministic glue and persists everything through the pipeline's
existing write paths.

It replaces the toil of hand-pasting agent output episode-by-episode (cf. the old
`scripts/fill_content.py`).

## Why

`content_builder/graph.py` runs `app.invoke()` synchronously and can't pause to
round-trip to an MCP client mid-node, so the DAG is re-expressed as a host-driven
sequence (`regen/orchestrator.py`): the agent produces each role's JSON via tool
calls; the server runs clustering / markdown-transform / tag-ticker extraction /
marp conversion between submissions. Prompt rendering + output parsing reuse each
node's `build_messages` / `postprocess`, so the agent path is byte-identical to a
real pipeline run for the same inputs.

**Whisper/transcription is out of scope** — the episode must already have a stored
transcript. Prompts are read live from `content_builder/prompts/*.yaml` (the same
files the admin "Prompts" editor writes), so prompt edits are picked up
automatically.

## Tools

| Tool | Purpose |
|---|---|
| `list_regen_candidates` | Transcribed episodes with missing/placeholder content |
| `start_regen` | Open a draft for an episode → returns the first (extractor) prompt |
| `get_role_prompt` | The rendered system+user prompt for a step (you generate the output) |
| `submit_role` | Submit your generated JSON; runs the glue; returns the next prompt |
| `preview_regen` | Show exactly what will be written (no write) |
| `commit_regen` | Persist to Firestore + bust the platform cache |
| `discard_regen` | Drop the draft |

Steps — required: `extractor → writer → key_insights → ticker_extractor`;
optional: `marp_writer` (episode slides), `ticker_marp_writer` (ticker slides).

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
    "TINBOKER_PLATFORM_API_URL": "http://localhost:5174"
  }
}
```

Firestore credentials come from the package's normal GSM `bootstrap()` /
firebase-admin setup (the env must have GCP ADC or `GCP_CREDENTIALS_JSON`/
`GOOGLE_APPLICATION_CREDENTIALS` available, same as a pipeline run).

| Env var | Purpose |
|---|---|
| `GCP_PROJECT_ID`, `FIRESTORE_DATABASE_ID` | Firestore (episode read + write) |
| `TINBOKER_PLATFORM_API_URL` | Backend base URL for cache invalidation on commit (default `http://localhost:5174`) |
| `TINBOKER_REGEN_WORK_DIR` | Where per-episode working drafts are persisted (default: system temp) |

## Persistence on `commit_regen`

- **Episode doc** (merge): `summary_content`, `key_insights`, `tags`,
  `related_tickers`, `marp_markdown`, `ticker_marp_markdown`, `events_markdown`,
  `social_cards` — only the fields whose steps you completed.
- **Rich ticker sentiment** → `ticker_insights/{episode_id}/tickers/{ticker}` via
  the pipeline's exporter.
- **Cache** → replays the four user-visible fields through the backend's PATCH
  (`notify_platform=True`) so the platform's Redis cache refreshes immediately.
- PNG social-card rendering stays in the normal pipeline (only the slide *markdown*
  is saved here).

## Tests

```bash
cd pipelines/services/podcast
uv run --package tinboker-podcast --extra dev pytest tests/test_regen_orchestrator.py -q
```
