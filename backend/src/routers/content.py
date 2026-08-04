"""Supply-chain article store (VPS local disk since the GCS decommission).

The ``graphfolio-articles`` bucket was copied verbatim to
``{MEDIA_STORAGE_ROOT}/graphfolio-articles/`` (docs/firestore-contract.md § 11.7),
keeping the bucket-era layouts (``blog/md/…`` + ``blog/svg/…``, and the older
``articles/{ticker}/…``), so lookups glob the whole tree instead of assuming one
structure. Signed URLs died with GCS — Caddy serves the tree publicly, so the
endpoints return stable media URLs (``ttl_seconds`` stays in the response shape
for the frontend, pinned to 0 = never expires).
"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.services.gcs_content import media_root, media_url

router = APIRouter(prefix="/api/content", tags=["content"])

BUCKET = "graphfolio-articles"

# Ticker is interpolated into a glob pattern — allow only symbol characters
# (AMD, 2330, BRK.B), which also closes traversal/wildcard input.
_TICKER_RE = re.compile(r"[A-Za-z0-9.\-]{1,12}")


def _bucket_dir() -> Path:
    return media_root() / BUCKET


def _url(path: Path) -> str:
    return media_url(BUCKET, path.relative_to(_bucket_dir()).as_posix())


def _find(pattern: str) -> Path | None:
    # min() = deterministic pick if a file exists at more than one legacy layout
    return min(_bucket_dir().rglob(pattern), default=None)


@router.get("/index")
def list_content():
    tickers: set[str] = set()
    for p in _bucket_dir().rglob("*_supply_chain*"):
        if p.suffix in (".md", ".svg"):
            tickers.add(p.name.split("_supply_chain")[0].upper())
    return {"tickers": sorted(tickers)}


@router.get("/{ticker}")
def get_ticker_content(ticker: str):
    if not _TICKER_RE.fullmatch(ticker):
        raise HTTPException(status_code=404, detail=f"Invalid ticker: {ticker!r}")
    t = ticker.lower()
    md = _find(f"{t}_supply_chain.md") or _find(f"{t}_supply_chain_article.md")
    svg = _find(f"{t}_supply_chain.svg")
    if not (md and svg):
        raise HTTPException(status_code=404, detail=f"Content not found for ticker {ticker}")
    return {
        "ticker": ticker.upper(),
        "svg_url": _url(svg),
        "article_url": _url(md),
        "ttl_seconds": 0,
    }
