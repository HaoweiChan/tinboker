#!/usr/bin/env python3
"""Seed the podcast_shows table from podcasts_tw.json.

Run once after deploying to populate the DB for the first time:

    cd /opt/tinboker-agents
    uv run python scripts/seed_shows.py

Subsequent runs are idempotent (upserts by slug).
"""

import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root / "services" / "podcast"))
sys.path.insert(0, str(_repo_root / "libs" / "shared" / "src"))

from src.secrets_bootstrap import bootstrap  # noqa: E402

bootstrap()

import os  # noqa: E402

import sqlalchemy as sa  # noqa: E402
from shared.wiki_builder.shows import PodcastShow, PostgresShowRepository  # noqa: E402
from shared.wiki_builder.slugify import slugify  # noqa: E402

db_url = os.environ.get("WIKI_DATABASE_URL")
if not db_url:
    print("Error: WIKI_DATABASE_URL is not set. Run bootstrap() or set the env var.")
    sys.exit(1)

config_file = _repo_root / "services" / "podcast" / "podcasts_tw.json"
if not config_file.exists():
    print(f"Error: {config_file} not found")
    sys.exit(1)

podcasts = json.loads(config_file.read_text(encoding="utf-8"))
engine = sa.create_engine(db_url, pool_pre_ping=True, future=True)

# Ensure the table exists (idempotent)
from shared.wiki_builder.postgres_repo import metadata  # noqa: E402

metadata.create_all(engine)

repo = PostgresShowRepository(engine)

print(f"Seeding {len(podcasts)} shows into podcast_shows...\n")
for p in podcasts:
    name = p.get("name", "").strip()
    if not name or not p.get("link"):
        print(f"  Skipping invalid entry: {p}")
        continue
    show = PodcastShow(
        slug=slugify(name),
        name=name,
        rss_url=p["link"],
        spotify_url=p.get("spotify_show_link"),
        episode_limit=int(p.get("limit", 10)),
        active=True,
    )
    repo.upsert_show(show)
    print(f"  OK  {show.slug}  ({show.name})")

print(f"\nDone. {len(podcasts)} show(s) seeded.")
