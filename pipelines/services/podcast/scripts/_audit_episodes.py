"""One-off audit: inspect episode Firestore docs + summary markdown format compliance.

Run on the VPS:
  cd /root/tinboker-agents/services/podcast
  GOOGLE_APPLICATION_CREDENTIALS=$PWD/gcp-service-account.json \
  FIRESTORE_DATABASE_ID=graphfolio-db \
  /root/tinboker-agents/.venv/bin/python scripts/_audit_episodes.py
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

SPECIFIC = [
    "87a8b530_ba4557e2f6254af1",
    "87a8b530_e0f6e0299c5a49a2",
]
TARGET_PODCAST = "財經一路發"
WINDOW_DAYS = 35  # a bit over a month

cred = credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass
db = firestore.client(database_id=DB_ID)
gcs = storage.Client(project=PROJECT)


def fetch_gcs(gs_url: str) -> str | None:
    if not gs_url or not gs_url.startswith("gs://"):
        return None
    rest = gs_url[len("gs://"):]
    bucket, _, key = rest.partition("/")
    try:
        blob = gcs.bucket(bucket).blob(key)
        if not blob.exists():
            return "__MISSING__"
        return blob.download_as_text()
    except Exception as e:  # noqa: BLE001
        return f"__ERR__:{e}"


def analyze_summary(md: str | None) -> dict:
    if md is None:
        return {"state": "NO_SUMMARY_URL"}
    if md == "__MISSING__":
        return {"state": "GCS_FILE_MISSING"}
    if md.startswith("__ERR__"):
        return {"state": "GCS_ERROR", "err": md}
    stripped = md.strip()
    chars = len(stripped)
    h1 = len(re.findall(r"(?m)^# ", md))
    h2 = len(re.findall(r"(?m)^## ", md))
    time_markers = len(re.findall(r"#time:\d+", md))
    ticker_links = len(re.findall(r"#ticker:", md))
    tag_links = len(re.findall(r"#tag:", md))
    has_conclusion = "## 結論" in md
    # Heuristic placeholder detection
    placeholder = chars < 200
    return {
        "state": "OK" if (chars >= 1200 and h2 >= 2) else ("THIN" if chars >= 200 else "EMPTY/PLACEHOLDER"),
        "chars": chars,
        "h1": h1,
        "h2_sections": h2,
        "time_markers": time_markers,
        "ticker_links": ticker_links,
        "tag_links": tag_links,
        "has_conclusion": has_conclusion,
        "placeholder": placeholder,
        "head": stripped[:160].replace("\n", " ⏎ "),
    }


def inspect(doc_id: str, data: dict) -> dict:
    summary_gs = data.get("summary_url")
    md = fetch_gcs(summary_gs)
    a = analyze_summary(md)
    return {
        "id": doc_id,
        "title": data.get("episode_title"),
        "podcast": data.get("podcast_name"),
        "created_time": data.get("created_time"),
        "released_at_ms": data.get("released_at_ms"),
        "summary_url": summary_gs,
        "summary_public_url": data.get("summary_public_url"),
        "has_marp": bool(data.get("marp_markdown_url")),
        "has_ticker_marp": bool(data.get("ticker_marp_markdown_url")),
        "related_tickers": data.get("related_tickers"),
        "fields_present": sorted(data.keys()),
        "summary_analysis": a,
    }


print("=" * 70)
print("PART 1 — the two reported episodes")
print("=" * 70)
for eid in SPECIFIC:
    snap = db.collection("episodes").document(eid).get()
    if not snap.exists:
        print(json.dumps({"id": eid, "EXISTS": False}, ensure_ascii=False))
        continue
    print(json.dumps(inspect(eid, snap.to_dict()), ensure_ascii=False, indent=2))
    print("-" * 70)

print("\n" + "=" * 70)
print(f"PART 2 — last {WINDOW_DAYS}d episodes, ALL shows (format audit)")
print("=" * 70)

cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
# created_time stored as ISO string; query all and filter in python (collection is small ~ hundreds)
rows = []
for snap in db.collection("episodes").stream():
    d = snap.to_dict()
    ct = d.get("created_time")
    dt = None
    if isinstance(ct, str):
        try:
            dt = datetime.fromisoformat(ct)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            dt = None
    elif isinstance(ct, datetime):
        dt = ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
    if dt is None or dt < cutoff:
        continue
    rows.append((dt, snap.id, d))

rows.sort(key=lambda r: r[0], reverse=True)
print(f"Episodes in window: {len(rows)}\n")
summary_rows = []
for dt, eid, d in rows:
    info = inspect(eid, d)
    a = info["summary_analysis"]
    summary_rows.append({
        "date": dt.strftime("%Y-%m-%d"),
        "id": eid,
        "podcast": info["podcast"],
        "title": (info["title"] or "")[:30],
        "state": a.get("state"),
        "chars": a.get("chars"),
        "h2": a.get("h2_sections"),
        "time": a.get("time_markers"),
        "ticker": a.get("ticker_links"),
        "tag": a.get("tag_links"),
        "concl": a.get("has_conclusion"),
    })

for r in summary_rows:
    print(json.dumps(r, ensure_ascii=False))

print("\n--- STATE TALLY ---")
tally: dict[str, int] = {}
for r in summary_rows:
    tally[r["state"]] = tally.get(r["state"], 0) + 1
print(json.dumps(tally, ensure_ascii=False, indent=2))
