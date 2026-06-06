"""Classify every episode summary: PLACEHOLDER / EMPTY / SHORT_REAL / OK.

Identifies the precise set of episodes that need reprocessing (placeholder or empty),
separate from legitimately-short real summaries (e.g. lifestyle episodes).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import storage

PROJECT = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "gen-lang-client-0901363254"
DB_ID = os.getenv("FIRESTORE_DATABASE_ID", "graphfolio-db")

PLACEHOLDER_SIGNATURES = (
    "This is a placeholder summary",
    "Placeholder content - real summary generation pending",
    "This is placeholder content",
    "Actual AI-generated summary coming soon",
    "real summary generation pending",
)

cred = credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass
db = firestore.client(database_id=DB_ID)
gcs = storage.Client(project=PROJECT)

_cache: dict[str, str] = {}


def fetch_gcs(gs_url: str) -> str | None:
    if not gs_url or not gs_url.startswith("gs://"):
        return None
    if gs_url in _cache:
        return _cache[gs_url]
    rest = gs_url[len("gs://"):]
    bucket, _, key = rest.partition("/")
    try:
        blob = gcs.bucket(bucket).blob(key)
        if not blob.exists():
            v = "__MISSING__"
        else:
            v = blob.download_as_text()
    except Exception as e:  # noqa: BLE001
        v = f"__ERR__:{e}"
    _cache[gs_url] = v
    return v


def classify(md: str | None) -> str:
    if md is None:
        return "NO_URL"
    if md == "__MISSING__":
        return "GCS_MISSING"
    if md.startswith("__ERR__"):
        return "GCS_ERROR"
    head = md[:600]
    if any(sig in head for sig in PLACEHOLDER_SIGNATURES):
        return "PLACEHOLDER"
    stripped = md.strip()
    if len(stripped) < 150:
        return "EMPTY"
    h2 = len(re.findall(r"(?m)^## ", md))
    if len(stripped) < 1200 or h2 < 2:
        return "SHORT_REAL"
    return "OK"


def parse_dt(ct):
    if isinstance(ct, str):
        try:
            dt = datetime.fromisoformat(ct)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if isinstance(ct, datetime):
        return ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
    return None


buckets: dict[str, list] = {}
all_rows = []
# Drain the Firestore stream FIRST (fast, no slow work inside the cursor loop —
# a per-doc GCS fetch stalls the stream past its deadline). Then fetch GCS.
docs = [(snap.id, snap.to_dict()) for snap in db.collection("episodes").stream()]
n = 0
for doc_id, d in docs:
    n += 1
    md = fetch_gcs(d.get("summary_url"))
    cls = classify(md)
    dt = parse_dt(d.get("created_time"))
    row = {
        "id": doc_id,
        "podcast": d.get("podcast_name"),
        "title": (d.get("episode_title") or "")[:40],
        "created": dt.strftime("%Y-%m-%d") if dt else None,
        "chars": len((md or "").strip()) if md and not md.startswith("__") else 0,
        "cls": cls,
        "tickers": len(d.get("related_tickers") or []),
    }
    all_rows.append(row)
    buckets.setdefault(cls, []).append(row)

print(f"TOTAL EPISODES SCANNED: {n}\n")
print("=== CLASSIFICATION TALLY (all-time) ===")
for k in sorted(buckets, key=lambda x: -len(buckets[x])):
    print(f"  {k:14s} {len(buckets[k])}")

for cls in ("PLACEHOLDER", "EMPTY", "GCS_MISSING", "GCS_ERROR", "NO_URL"):
    rows = buckets.get(cls, [])
    if not rows:
        continue
    print(f"\n=== {cls} — {len(rows)} episodes (NEED REPROCESS) ===")
    rows.sort(key=lambda r: (r["created"] or "", r["podcast"] or ""))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))

# Format compliance among REAL summaries in last 35 days (by created_time)
cutoff = datetime.now(timezone.utc) - timedelta(days=35)
print("\n=== FORMAT NOTE: SHORT_REAL in last 35d (by podcast) ===")
short_recent = [r for r in buckets.get("SHORT_REAL", []) if r["created"] and datetime.fromisoformat(r["created"]).replace(tzinfo=timezone.utc) >= cutoff]
by_pod: dict[str, int] = {}
for r in short_recent:
    by_pod[r["podcast"]] = by_pod.get(r["podcast"], 0) + 1
print(json.dumps(by_pod, ensure_ascii=False, indent=2))

# Emit a plain id list for the reprocess step
reprocess_ids = [r["id"] for cls in ("PLACEHOLDER", "EMPTY") for r in buckets.get(cls, [])]
print("\n=== REPROCESS_IDS ===")
print(json.dumps(reprocess_ids, ensure_ascii=False))
