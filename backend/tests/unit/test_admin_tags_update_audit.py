from types import SimpleNamespace

import pytest

from src.auth.admin_auth import AdminAccess
from src.database.models import TagRegistry
from src.routers import admin_tags
from src.routers.admin_tags import TagUpdate, update_tag
from src.tag_registry import KIND_SECTOR, TIER_TRENDING


class _PostgresBind:
    dialect = SimpleNamespace(name="postgresql")


class _Query:
    def __init__(self, row: TagRegistry):
        self.row = row

    def filter(self, *_args):
        return self

    def first(self):
        return self.row


class _Session:
    def __init__(self, row: TagRegistry):
        self.row = row
        self.events: list[tuple[str, str | None, dict | None]] = []

    def get_bind(self):
        return _PostgresBind()

    def execute(self, statement, params=None):
        self.events.append(("execute", str(statement), params or {}))

    def query(self, _model):
        return _Query(self.row)

    def commit(self):
        self.events.append(("commit", None, None))

    def refresh(self, _row):
        self.events.append(("refresh", None, None))


@pytest.mark.asyncio
async def test_update_tag_sets_audit_guc_before_commit(monkeypatch):
    async def _noop_invalidate():
        return None

    monkeypatch.setattr(admin_tags, "_invalidate_tag_caches", _noop_invalidate)
    row = TagRegistry(
        id=1,
        slug="sector_a",
        display_zh="Sector A",
        tier=TIER_TRENDING,
        kind=KIND_SECTOR,
        exposure_id="sector_a",
    )
    db = _Session(row)

    await update_tag(
        1,
        TagUpdate(display_zh="Sector A Updated"),
        admin=AdminAccess(email="owner@example.com"),
        db=db,
    )

    event_names = [event[0] for event in db.events]
    assert event_names[:2] == ["execute", "execute"]
    assert event_names.index("commit") > 1
    assert "SET LOCAL app.taxonomy_actor" in db.events[0][1]
    assert db.events[0][2] == {"actor": "admin:owner@example.com"}
    assert "SET LOCAL app.taxonomy_note" in db.events[1][1]
    assert row.field_owners == {"display_zh": "admin:owner@example.com"}
