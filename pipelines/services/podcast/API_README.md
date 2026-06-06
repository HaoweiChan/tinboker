# Podcast Downloader API

FastAPI-based REST API for triggering episode processing jobs.

## Endpoints

### Health Check
- **GET** `/health`
- Returns: `{"status": "healthy"}`

### Rerun Episode Summarize (GET)
- **GET** `/api/episodes/rerun-summarize/{episode_id}`
- Triggers: `python main.py --rerun-from summarize --episode <episode_id>`
- Example: `GET /api/episodes/rerun-summarize/Gooaye_859cc52dc1eaf2f0`
- Returns:
```json
{
  "message": "Episode rerun job started for episode_id: Gooaye_859cc52dc1eaf2f0",
  "episode_id": "Gooaye_859cc52dc1eaf2f0",
  "status": "started"
}
```

### Rerun Episode Summarize (POST)
- **POST** `/api/episodes/rerun-summarize`
- Body:
```json
{
  "episode_id": "Gooaye_859cc52dc1eaf2f0"
}
```
- Returns: Same as GET endpoint

## Running the Server

### Using the startup script:
```bash
./start_api.sh
```

### Manually:
```bash
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://<server-ip>:8000/docs`
- ReDoc: `http://<server-ip>:8000/redoc`

## Testing

### Using curl:

**GET request:**
```bash
curl http://<server-ip>:8000/api/episodes/rerun-summarize/Gooaye_859cc52dc1eaf2f0
```

**POST request:**
```bash
curl -X POST http://<server-ip>:8000/api/episodes/rerun-summarize \
  -H "Content-Type: application/json" \
  -d '{"episode_id": "Gooaye_859cc52dc1eaf2f0"}'
```

## Notes

- The command runs in the background, so the API returns immediately
- The actual processing happens asynchronously
- Check server logs to see the progress of the background job
- The server is configured with CORS to allow requests from any origin
