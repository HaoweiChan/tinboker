from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    TagRegistry,
    TaxonomyChangelog,
    TaxonomyDraft,
    TaxonomyVersion,
)
from src.routers.admin_taxonomy import (
    BulkTaxonomyRequest,
    SectorPayload,
    create_taxonomy_draft,
    publish_taxonomy_draft,
)
from src.tag_registry import KIND_SECTOR, TIER_TRENDING


def _member(ticker: str) -> dict:
    return {"ticker": ticker, "name": ticker, "market": "TW", "source": "test"}


def _payload(exposure_id: str, description: str, ticker: str) -> SectorPayload:
    return SectorPayload(
        exposure_id=exposure_id,
        display_name=exposure_id,
        exposure_type="theme",
        description=description,
        members=[_member(ticker)],
    )


def _session():
    engine = create_engine("sqlite:///:memory:")
    for table in (
        TagRegistry.__table__,
        TaxonomyDraft.__table__,
        TaxonomyVersion.__table__,
        TaxonomyChangelog.__table__,
    ):
        table.create(bind=engine)
    return sessionmaker(bind=engine)()


def test_bulk_draft_publish_survivorship_force_and_structural_changelog():
    db = _session()
    try:
        db.add(TagRegistry(
            slug="sector_a",
            display_zh="sector_a",
            tier=TIER_TRENDING,
            kind=KIND_SECTOR,
            exposure_id="sector_a",
            exposure_type="theme",
            description="human description",
            members=[_member("1001")],
            field_owners={
                "description": "admin:owner@example.com",
                "members": "bot:import",
            },
            updated_by="admin:owner@example.com",
        ))
        db.commit()

        body = BulkTaxonomyRequest(
            actor="bot:import",
            sectors=[
                _payload("sector_a", "bot description", "1001"),
                _payload("sector_b", "new sector", "2002"),
            ],
            entry="Add sector_b",
            rationale="structural add in test",
        )
        draft, diff = create_taxonomy_draft(db, body, actor="bot:import")

        assert diff.added == 1
        assert diff.changed == 1
        assert [sample["action"] for sample in diff.samples] == ["added", "changed"]

        response = publish_taxonomy_draft(db, draft.id, force=False)

        row_a = db.query(TagRegistry).filter_by(exposure_id="sector_a").one()
        row_b = db.query(TagRegistry).filter_by(exposure_id="sector_b").one()
        assert row_a.description == "human description"
        assert row_a.members == [_member("1001")]
        assert row_b.description == "new sector"
        assert response.skipped == [{"exposure_id": "sector_a", "fields": ["description"]}]
        assert response.version == 1
        assert db.query(TaxonomyChangelog).one().entry == "Add sector_b"

        force_body = BulkTaxonomyRequest(
            actor="bot:import",
            sectors=[_payload("sector_a", "forced description", "1001")],
        )
        force_draft, _ = create_taxonomy_draft(db, force_body, actor="bot:import")
        force_response = publish_taxonomy_draft(db, force_draft.id, force=True)

        db.refresh(row_a)
        assert row_a.description == "forced description"
        assert force_response.skipped == []
        assert force_response.version is None
        assert db.query(TaxonomyChangelog).count() == 1
    finally:
        db.close()


def test_publish_same_draft_twice_conflicts_and_versions_once():
    db = _session()
    try:
        body = BulkTaxonomyRequest(
            actor="bot:import",
            sectors=[_payload("sector_once", "new sector", "1001")],
            entry="Initial import",
        )
        draft, _ = create_taxonomy_draft(db, body, actor="bot:import")

        first = publish_taxonomy_draft(db, draft.id)
        assert first.version == 1

        try:
            publish_taxonomy_draft(db, draft.id)
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "already published or publishing"
        else:
            raise AssertionError("second publish should conflict")

        assert db.query(TaxonomyVersion).one().version == 1
        assert db.query(TaxonomyChangelog).count() == 1
        assert db.query(TagRegistry).filter_by(exposure_id="sector_once").count() == 1
    finally:
        db.close()


def test_bootstrap_identical_publish_creates_version_one_changelog():
    db = _session()
    try:
        db.add(TagRegistry(
            slug="sector_bootstrap",
            display_zh="sector_bootstrap",
            tier=TIER_TRENDING,
            kind=KIND_SECTOR,
            exposure_id="sector_bootstrap",
            exposure_type="theme",
            description="already seeded",
            members=[_member("1001")],
            updated_by="bootstrap:seed",
        ))
        db.commit()

        body = BulkTaxonomyRequest(
            actor="bot:import",
            sectors=[_payload("sector_bootstrap", "already seeded", "1001")],
            entry="Bootstrap import",
        )
        draft, diff = create_taxonomy_draft(db, body, actor="bot:import")
        assert diff.added == 0
        assert diff.removed == 0
        assert diff.changed == 0

        response = publish_taxonomy_draft(db, draft.id)

        assert response.version == 1
        assert db.query(TaxonomyVersion).one().version == 1
        assert db.query(TaxonomyChangelog).one().entry == "Bootstrap import"
    finally:
        db.close()


def test_bot_publish_skips_admin_description_but_updates_members():
    db = _session()
    try:
        db.add(TagRegistry(
            slug="sector_a",
            display_zh="sector_a",
            tier=TIER_TRENDING,
            kind=KIND_SECTOR,
            exposure_id="sector_a",
            exposure_type="theme",
            description="admin description",
            members=[_member("1001")],
            field_owners={
                "description": "admin:owner@example.com",
                "members": "bot:import",
            },
            updated_by="admin:owner@example.com",
        ))
        db.add(TaxonomyVersion(id=1, version=1))
        db.commit()

        body = BulkTaxonomyRequest(
            actor="bot:import",
            sectors=[
                SectorPayload(
                    exposure_id="sector_a",
                    display_name="sector_a",
                    exposure_type="theme",
                    description="bot description",
                    members=[_member("1001"), _member("2002")],
                )
            ],
        )
        draft, _ = create_taxonomy_draft(db, body, actor="bot:import")
        response = publish_taxonomy_draft(db, draft.id)

        row = db.query(TagRegistry).filter_by(exposure_id="sector_a").one()
        assert row.description == "admin description"
        assert [member["ticker"] for member in row.members] == ["1001", "2002"]
        assert row.field_owners["description"] == "admin:owner@example.com"
        assert row.field_owners["members"] == "bot:import"
        assert response.skipped == [{"exposure_id": "sector_a", "fields": ["description"]}]
    finally:
        db.close()


def test_reasons_fill_merges_into_admin_owned_members_without_reordering():
    db = _session()
    try:
        existing_members = [_member("1001"), _member("2002")]
        db.add(TagRegistry(
            slug="sector_reasons",
            display_zh="sector_reasons",
            tier=TIER_TRENDING,
            kind=KIND_SECTOR,
            exposure_id="sector_reasons",
            exposure_type="theme",
            description="desc",
            members=existing_members,
            field_owners={"members": "admin:owner@example.com"},
            updated_by="admin:owner@example.com",
        ))
        db.add(TaxonomyVersion(id=1, version=1))
        db.commit()

        incoming_members = [
            {**_member("1001"), "reason": "reason one"},
            {**_member("2002"), "reason": "reason two"},
        ]
        body = BulkTaxonomyRequest(
            actor="bot:reasons-fill",
            sectors=[
                SectorPayload(
                    exposure_id="sector_reasons",
                    display_name="sector_reasons",
                    exposure_type="theme",
                    description="desc",
                    members=incoming_members,
                )
            ],
        )
        draft, _ = create_taxonomy_draft(db, body, actor="bot:reasons-fill")
        response = publish_taxonomy_draft(db, draft.id)

        row = db.query(TagRegistry).filter_by(exposure_id="sector_reasons").one()
        assert [member["ticker"] for member in row.members] == ["1001", "2002"]
        assert [member["reason"] for member in row.members] == ["reason one", "reason two"]
        assert row.field_owners["members"] == "admin:owner@example.com"
        assert response.skipped == []
    finally:
        db.close()
