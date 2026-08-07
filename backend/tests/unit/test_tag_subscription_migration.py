from __future__ import annotations

from src.database import user_db


def test_remap_merged_sector_tag_subscriptions_dedupes_targets():
    assert user_db.remap_merged_sector_tag_subscriptions(
        ["AI", "日本矽晶圓", "矽晶圓", "日本後段設備", "封裝製程機台"]
    ) == ["AI", "矽晶圓", "封裝製程機台"]


def test_remap_preserves_the_legacy_hash_prefix():
    assert user_db.remap_merged_sector_tag_subscriptions(["#日本矽晶圓"]) == ["#矽晶圓"]


# The table-level idempotency of migrate_merged_sector_tag_subscriptions is covered in
# test_user_notification_postgres.py, which runs it against a real users table.
