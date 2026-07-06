from __future__ import annotations

from src.database import user_db


def test_remap_merged_sector_tag_subscriptions_dedupes_targets():
    assert user_db.remap_merged_sector_tag_subscriptions(
        ["AI", "日本矽晶圓", "矽晶圓", "日本後段設備", "封裝製程機台"]
    ) == ["AI", "矽晶圓", "封裝製程機台"]


def test_migrate_merged_sector_tag_subscriptions_is_idempotent(monkeypatch):
    class FakeFirestore:
        def __init__(self):
            self.docs = [
                {
                    "id": "u1",
                    "tag_subscriptions": ["日本前段設備", "前段製程設備", "其他"],
                },
                {
                    "id": "u2",
                    "tag_subscriptions": ["被動元件 MLCC"],
                },
            ]
            self.writes: list[tuple[str, str, dict, bool]] = []

        def get_all_documents(self, collection: str):
            assert collection == "users"
            return self.docs

        def set_document(self, collection: str, doc_id: str, data: dict, merge: bool = False):
            self.writes.append((collection, doc_id, data, merge))
            for doc in self.docs:
                if doc["id"] == doc_id:
                    doc.update(data)
            return True

    fake = FakeFirestore()
    monkeypatch.setattr(user_db, "_get_firestore_service", lambda: fake)

    assert user_db.migrate_merged_sector_tag_subscriptions() == 1
    assert fake.docs[0]["tag_subscriptions"] == ["前段製程設備", "其他"]
    assert fake.writes[0][0:2] == ("users", "u1")
    assert fake.writes[0][3] is True

    assert user_db.migrate_merged_sector_tag_subscriptions() == 0
    assert len(fake.writes) == 1
