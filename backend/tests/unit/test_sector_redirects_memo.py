"""sector_redirects() must not hit tag_registry once per call.

resolve_sector_exposure_id() is called per exposure entry across hundreds of
episodes on the by-sector page and thousands on the board scan; each call used to
open a session and scan the registry (cold /episodes/by-sector 21-50s, 2026-09-05).
"""
from unittest.mock import MagicMock

from src import tag_registry
from src.database import postgres


def test_sector_redirects_reads_registry_once_per_ttl(monkeypatch):
    reads: list[int] = []

    def _read(_session):
        reads.append(1)
        return {"sector_old": "sector_new"}

    monkeypatch.setattr(tag_registry, "_sector_redirects_from_session", _read)
    monkeypatch.setattr(postgres, "SessionLocal", MagicMock())

    assert tag_registry.sector_redirects() == {"sector_old": "sector_new"}
    assert tag_registry.sector_redirects() == {"sector_old": "sector_new"}
    assert len(reads) == 1

    # An explicit session bypasses the memo (admin flows read-after-write).
    tag_registry.sector_redirects(MagicMock())
    assert len(reads) == 2


def test_sector_redirects_does_not_cache_a_failed_read(monkeypatch):
    def _boom(_session):
        raise RuntimeError("db down")

    monkeypatch.setattr(tag_registry, "_sector_redirects_from_session", _boom)
    monkeypatch.setattr(postgres, "SessionLocal", MagicMock())

    assert tag_registry.sector_redirects() == {}
    assert tag_registry._redirects_cache == (0.0, {})
