import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database import postgres


POSTGRES_URL = os.getenv("TINBOKER_TEST_POSTGRES_URL")


@pytest.mark.integration
@pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TINBOKER_TEST_POSTGRES_URL is not configured",
)
def test_tag_registry_audit_trigger_captures_direct_update():
    engine = create_engine(POSTGRES_URL)
    old_engine = postgres.engine
    old_session = postgres.SessionLocal
    postgres.engine = engine
    postgres.SessionLocal = sessionmaker(bind=engine)
    exposure_id = f"sector_audit_{uuid.uuid4().hex}"
    try:
        postgres.create_all_tables()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tag_registry_audit WHERE exposure_id = :eid"), {"eid": exposure_id})
            conn.execute(text("DELETE FROM tag_registry WHERE exposure_id = :eid"), {"eid": exposure_id})
            conn.execute(text("SELECT set_config('app.taxonomy_actor', 'admin:audit-test', true)"))
            conn.execute(text("SELECT set_config('app.taxonomy_note', 'direct sql test', true)"))
            conn.execute(
                text(
                    """
                    INSERT INTO tag_registry (
                        slug, display_zh, tier, kind, exposure_id, exposure_type, members
                    )
                    VALUES (
                        :eid, 'Audit A', 'trending', 'sector', :eid, 'theme', '[]'::jsonb
                    )
                    """
                ),
                {"eid": exposure_id},
            )
            conn.execute(
                text("UPDATE tag_registry SET display_zh = 'Audit B' WHERE exposure_id = :eid"),
                {"eid": exposure_id},
            )
            row = conn.execute(
                text(
                    """
                    SELECT action, actor, note, "before", "after"
                    FROM tag_registry_audit
                    WHERE exposure_id = :eid AND action = 'UPDATE'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"eid": exposure_id},
            ).mappings().one()
            assert row["actor"] == "admin:audit-test"
            assert row["note"] == "direct sql test"
            assert row["before"]["display_zh"] == "Audit A"
            assert row["after"]["display_zh"] == "Audit B"
            conn.execute(text("DELETE FROM tag_registry WHERE exposure_id = :eid"), {"eid": exposure_id})
            conn.execute(text("DELETE FROM tag_registry_audit WHERE exposure_id = :eid"), {"eid": exposure_id})
    finally:
        postgres.engine = old_engine
        postgres.SessionLocal = old_session
        engine.dispose()
