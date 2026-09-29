"""Coordinate MP3 writes with retention finalization on the media host."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from shared.db import libpq_url


@contextmanager
def mp3_media_lock(root: Path) -> Iterator[None]:
    """Serialize MP3 replacement and unlink across local service processes."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".mp3-retention.lock").open("a+b") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def mp3_is_retired(media_key: str) -> bool:
    """Fail closed when an installed tombstone ledger cannot be checked."""
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return False  # Local development without a mirror database.
    try:
        with psycopg.connect(libpq_url(url)) as conn:
            with conn.cursor() as cur:
                if cur.execute("SELECT to_regclass('mp3_retention.tombstones')").fetchone()[0] is None:
                    return False  # The dormant migration has not been installed yet.
                return bool(cur.execute(
                    "SELECT 1 FROM mp3_retention.tombstones WHERE media_key = %s",
                    (media_key,),
                ).fetchone())
    except Exception:
        # Driver exceptions may include a credential-bearing DSN.
        raise RuntimeError("MP3 retention ledger is unavailable") from None
