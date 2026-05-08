# Content API (GCS) Tutorial

Goal: expose your GCS-hosted supply-chain content (Markdown + SVG) through the FastAPI backend so the frontend can render it without touching local repo files.

## 1) Prerequisites
- Bucket: `tinboker-articles` (private; no `allUsers` bindings).
- Python deps: FastAPI stack plus `google-cloud-storage`.
- Credentials: a service account with `roles/storage.objectViewer` on the bucket (or higher). Use Workload Identity on GCP if available; otherwise a JSON key via env.

## 2) Install dependency
```
pip install google-cloud-storage
```
Add it to your requirements file if needed.

## 3) Environment variables
Add to `.env` (or your deployment env):
```
CONTENT_BUCKET=tinboker-articles
CONTENT_PREFIX=content       # optional; leave empty if objects live at bucket root
CONTENT_URL_TTL=3600         # seconds for signed URLs (1h typical)

# Credentials (choose one approach)
# A) Workload Identity / Default Creds (recommended on GCP):
#    No extra env needed if the runtime has access.
# B) JSON key (local/dev):
# GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/sa-key.json
```

## 4) Object layout assumptions in GCS
- SVG path: `content/{ticker}/{ticker}_supply_chain.svg`
- Markdown path: `content/{ticker}/{ticker}_supply_chain_article.md`
Adjust `CONTENT_PREFIX` or code if your structure differs.

## 5) Router implementation (FastAPI)
Create `src/routers/content.py`:
```python
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from google.cloud import storage
import os

router = APIRouter(prefix="/api/content", tags=["content"])

BUCKET = os.getenv("CONTENT_BUCKET")
PREFIX = os.getenv("CONTENT_PREFIX", "").strip("/ ")
TTL = int(os.getenv("CONTENT_URL_TTL", "3600"))

client = storage.Client()

def _blob_path(*parts: str) -> str:
    parts = [p for p in parts if p]
    return "/".join(parts)

def _signed_url(path: str) -> str:
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(path)
    if not blob.exists():
        raise HTTPException(status_code=404, detail=f"Object not found: {path}")
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=TTL),
        method="GET",
    )

@router.get("/index")
def list_content():
    bucket = client.bucket(BUCKET)
    prefix = f"{PREFIX}/" if PREFIX else ""
    tickers = {}
    for blob in client.list_blobs(bucket, prefix=prefix):
        name = blob.name
        if not name.endswith((".md", ".svg")):
            continue
        rel = name[len(prefix):] if name.startswith(prefix) else name
        parts = rel.split("/")
        if len(parts) < 2:
            continue
        ticker = parts[0]
        tickers.setdefault(ticker, []).append(rel)
    return {"tickers": sorted(tickers.keys())}

@router.get("/{ticker}")
def get_ticker_content(ticker: str):
    svg_path = _blob_path(PREFIX, ticker, f"{ticker}_supply_chain.svg")
    md_path = _blob_path(PREFIX, ticker, f"{ticker}_supply_chain_article.md")
    return {
        "ticker": ticker,
        "svg_url": _signed_url(svg_path),
        "article_url": _signed_url(md_path),
        "ttl_seconds": TTL,
    }
```

Notes:
- Returns signed URLs (v4) valid for `CONTENT_URL_TTL` seconds.
- If your bucket becomes public/CDN-backed, you can skip signing and instead return public URLs composed from a `CONTENT_CDN_BASE`.

## 6) Register the router
In `src/main.py`, after other router imports:
```python
from routers import content

app.include_router(content.router)
```
Ensure CORS in `main.py` allows your frontend origin so it can call these endpoints.

## 7) Frontend usage
- Call `GET /api/content/{ticker}` to obtain `article_url` and `svg_url`.
- Markdown: fetch `article_url`, parse/render with your markdown component.
- SVG: use `<img src={svg_url} />` or fetch+inline if you need DOM access; signed URLs are cross-origin-friendly if CORS on the bucket is default (private read via signed URL does not require CORS for simple GET by <img>).

## 8) Optional: stricter shapes / errors
- Add Pydantic response models if you want stronger typing.
- Handle `google.auth.exceptions.DefaultCredentialsError` with a 500 + guidance to set credentials.

## 9) Local test
```
uvicorn src.main:app --reload --port 5174
curl http://localhost:5174/api/content/index
curl http://localhost:5174/api/content/tsmc
```
You should see signed URLs; opening them in a browser should download/preview the asset.

## 10) Deployment tips
- On GCP, prefer Workload Identity over JSON keys.
- If you front the bucket with Cloud CDN and make it public, replace signed URLs with `CONTENT_CDN_BASE` + object path for longer caching and no signing overhead.

