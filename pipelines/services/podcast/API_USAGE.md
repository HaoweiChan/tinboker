# Podcast Downloader API

FastAPI server for running episode processing commands remotely.

## Public URL

**Public URL:** `http://159.195.45.195:8002`

> **Note:** This is the direct public IP address of the server. The server is listening on port 8002 and is accessible from the internet. (Port 8000 is used by RMLJ Manga API)

## Authentication

All protected endpoints require API key authentication via the `X-API-Key` header.

### Setup

1. Create a `.env` file in the project root:
```bash
cd /root/mnt/Podcast-Downloader
cp .env.example .env
```

2. Generate a strong API key:
```bash
openssl rand -hex 32
```

3. Set the API key in `.env`:
```bash
PODCAST_API_KEY=your-generated-api-key-here
```

4. Restart the server for changes to take effect.

### Using Authentication

Include the `X-API-Key` header in all requests to protected endpoints:

```bash
curl -X POST http://159.195.45.195:8002/api/episodes/rerun-summarize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"episode_id": "Gooaye_859cc52dc1eaf2f0"}'
```

**Note:** Health check endpoints (`/health` and `/api/episodes/health`) are public and do not require authentication.

## Endpoints

### Health Check
- **GET** `/health` - Global health check
- **GET** `/api/episodes/health` - Episode processor health check

### Rerun Episode Summarize

Runs the command: `python main.py --rerun-from summarize --episode <episode_id>`

#### POST Endpoint
- **URL:** `/api/episodes/rerun-summarize`
- **Method:** POST
- **Content-Type:** `application/json`
- **Body:**
```json
{
  "episode_id": "Gooaye_859cc52dc1eaf2f0"
}
```

**Example:**
```bash
curl -X POST http://159.195.45.195:8002/api/episodes/rerun-summarize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"episode_id": "Gooaye_859cc52dc1eaf2f0"}'
```

#### GET Endpoint
- **URL:** `/api/episodes/rerun-summarize/{episode_id}`
- **Method:** GET

**Example:**
```bash
curl http://159.195.45.195:8002/api/episodes/rerun-summarize/Gooaye_859cc52dc1eaf2f0 \
  -H "X-API-Key: your-api-key-here"
```

### Job Status

Check the progress of an episode rerun job.

- **URL:** `/api/episodes/status/{episode_id}`
- **Method:** GET
- **Headers:** `X-API-Key: your-api-key-here`

**Example:**
```bash
curl http://159.195.45.195:8002/api/episodes/status/87a8b530_3d73511269382227 \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "episode_id": "87a8b530_3d73511269382227",
  "status": "running",  // or "completed", "failed"
  "started_at": "2026-01-18T16:59:47.062482",
  "updated_at": "2026-01-18T16:59:48.142156",
  "returncode": null,  // Process exit code (null if still running)
  "stdout": "...",     // Last 5000 chars of stdout
  "stderr": "...",     // Last 5000 chars of stderr
  "error": null        // Error message if failed
}
```

### All Jobs Status

Get status of all episode rerun jobs.

- **URL:** `/api/episodes/status`
- **Method:** GET
- **Headers:** `X-API-Key: your-api-key-here`

**Example:**
```bash
curl http://159.195.45.195:8002/api/episodes/status \
  -H "X-API-Key: your-api-key-here"
```

### API Documentation
- **URL:** `/docs` - Interactive Swagger UI documentation
- **URL:** `/redoc` - Alternative ReDoc documentation

## Response Format

All endpoints return JSON:

```json
{
  "message": "Episode rerun job started for episode_id: Gooaye_859cc52dc1eaf2f0",
  "episode_id": "Gooaye_859cc52dc1eaf2f0",
  "status": "started"
}
```

## Running the Server

### Start the FastAPI Server

**Option 1: Using the start script (recommended)**
```bash
cd /root/mnt/Podcast-Downloader
./start_api.sh
```

**Option 2: Manual start (default - accessible from internet)**
```bash
cd /root/mnt/Podcast-Downloader
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8002
```

**Option 3: Localhost only (not accessible from internet)**
```bash
cd /root/mnt/Podcast-Downloader
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8002
```

**Option 4: Custom port**
```bash
cd /root/mnt/Podcast-Downloader
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8080
```

### Network Configuration

- **`--host 0.0.0.0`**: Binds to all network interfaces, making the server accessible from the internet (default)
- **`--host 127.0.0.1`**: Binds to localhost only, making the server accessible only from the server itself
- **`--port 8002`**: The port number (default: 8002). Change if you need a different port.

**Note:** The server is running on the remote server (159.195.45.195), not on your local machine. Port 8002 is used for the Podcast Downloader API (port 8000 is used by RMLJ Manga API).

## Project Structure

```
Podcast-Downloader/
├── app.py                    # FastAPI main application
├── .env                      # Environment variables (API key) - NOT in git
├── .env.example              # Example environment file
└── src/
    ├── auth.py               # Authentication module
    └── routers/
        ├── __init__.py
        └── episode.py        # Episode processing router
```

## Implementation Details

- The API uses FastAPI with async/await for non-blocking operations
- Episode processing runs in background tasks
- The router uses the virtual environment's Python executable (`/root/mnt/Podcast-Downloader/.venv/bin/python3`)
- CORS is enabled for all origins to allow testing from any client
- The command executed is: `python3 main.py --rerun-from summarize --episode <episode_id>`
- **Security:** API key authentication is required for all protected endpoints via `X-API-Key` header
- API key is configured via `PODCAST_API_KEY` environment variable (loaded from `.env` file)