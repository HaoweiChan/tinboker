# Module: podcast

> FastAPI service + batch CLI for podcast download, transcribe, summarize, upload pipeline.

## Responsibility

Ingests Spotify RSS feeds, downloads MP3s, transcribes via Groq Whisper or AssemblyAI, summarizes using `content_builder`, uploads to Google Cloud Storage and Firestore, and optionally writes wiki pages. Does NOT generate knowledge graphs—that is knowledge-graph/ responsibility.

## Where it runs

Netcup VPS `152.53.136.182:8003` under systemd unit `podcast-api.service`. Also deployable to Render as cron job.

## Public API (entry points)

- [app.py](app.py) — FastAPI shim for service startup
- [main.py](main.py) — CLI orchestrator (646 lines); entry point for batch processing
- FastAPI routers in [src/routers/](src/routers/) — `podcast`, `episode`, health check endpoints
- CLI flags: `--rerun-from {download,transcribe,summarize,upload,validate}`, `--episode-id`, `--fill-limit`, `--file-mode`
- Health: `GET /health`

## Internal structure

**Pipeline architecture:**
- [src/pipeline/processor.py](src/pipeline/processor.py) — EpisodeProcessor orchestrator
- [src/pipeline/config.py](src/pipeline/config.py) — PipelineConfig dataclass
- [src/pipeline/episode_data.py](src/pipeline/episode_data.py) — EpisodeData state object passed between steps
- [src/pipeline/service_container.py](src/pipeline/service_container.py) — service registry shared across steps
- [src/pipeline/steps/](src/pipeline/steps/) — step implementations (initialize, download, transcribe, summarize, gcs_upload, firestore, validate, wiki_ingest)

**Service layer:**
- [src/service/](src/service/) — speech_to_text, gcs_storage_service, etc.
- [src/secrets_bootstrap.py](src/secrets_bootstrap.py) — Google Secret Manager enumeration (_GSM_VARS tuple)
- [src/job_tracker.py](src/job_tracker.py) — episode processing state tracking
- [src/auth.py](src/auth.py) — authentication utilities

**Data models & routers:**
- [src/models/](src/models/) — Pydantic schemas
- [src/routers/](src/routers/) — FastAPI route handlers (podcast.py, episode.py)

**Integrations:**
- [src/spotify_podcast/](src/spotify_podcast/) — Spotify metadata fetcher
- [src/summarize/](src/summarize/) — content_builder wrapper
- [src/wiki_builder/](src/wiki_builder/) — wiki page ingestion after summarize

**Configuration & data:**
- [podcasts_to_download.json](podcasts_to_download.json) — list of podcasts with RSS links and limits
- [configs/default.yaml](configs/default.yaml) — LLM settings, GCP project, GCS bucket

## Dependencies

- **Internal:** `content_builder` (imported via `-e ../content` in requirements.txt)
- **External Python:** fastapi, uvicorn, assemblyai, groq, deepgram-sdk, openai, pydub, google-cloud-{secret-manager,storage,speech}, firebase-admin, zhconv
- **External services:** Groq Whisper API, AssemblyAI, Google Secret Manager, GCS, Firestore, Spotify API

## Configuration

- **Secrets (Google Secret Manager):** listed in [src/secrets_bootstrap.py](src/secrets_bootstrap.py) (_GSM_VARS tuple)
- **Env vars:** GCP project ID, GCS bucket in [configs/default.yaml](configs/default.yaml); episodes list in [podcasts_to_download.json](podcasts_to_download.json)
- **Service account:** `gcp-service-account.json` (NEVER commit)

## How to run locally

```bash
cd podcast
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Or start as API:
```bash
bash start_api.sh --port 8003
```

## How to run tests

```bash
python -m pytest tests/unit/ -x
python -m pytest tests/integration/ -x  # requires network
```

## Common tasks → file map

| Task | File(s) |
|---|---|
| Add STT provider | [src/service/speech_to_text.py](src/service/speech_to_text.py) |
| Add pipeline step | [src/pipeline/steps/](src/pipeline/steps/) + register in `__init__.py` |
| New API route | [src/routers/](src/routers/) |
| New GSM secret | [src/secrets_bootstrap.py](src/secrets_bootstrap.py) (_GSM_VARS tuple) |
| Configure LLM models | [configs/default.yaml](configs/default.yaml) |
| Adjust transcript format | [src/service/speech_to_text.py](src/service/speech_to_text.py) |

## Production safety rules

- Never commit `gcp-service-account.json` or any API keys.
- Port **8003 ONLY** (NOT 8002—backend-staging conflict). Systemd service hardcodes this.
- Always re-run `pip install -r requirements.txt` after editing requirements.txt.
- `--fill-limit` is idempotent—safe for cron jobs; deduplicates against Firestore before processing.
- Rerun flags (`--rerun-from`) control what data is re-fetched; respect step dependencies.

## See also

- [README.md](README.md) — user-facing setup and architecture (do not modify)
- [MIGRATION.md](../MIGRATION.md) — Dify integration deprecated in favor of content_builder
- [content/MODULE.md](../content/MODULE.md) — summarization engine consumed by this module
- [wiki/MODULE.md](../wiki/MODULE.md) — wiki_builder writes episode pages after summarization
