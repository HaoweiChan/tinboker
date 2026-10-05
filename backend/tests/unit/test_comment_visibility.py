"""Comment storage + public/private visibility filtering (feedback board)."""
import pytest


@pytest.fixture
def comment_db(tmp_path):
    import src.database.postgres as pg
    from src.config import settings

    prev = (pg.engine, pg.SessionLocal, settings.use_postgres, settings.database_path)
    settings.use_postgres = False
    settings.database_path = str(tmp_path / "comments.db")
    pg.engine = None
    pg.SessionLocal = None
    pg.init_engine()
    from src.database import comment_db as module
    pg.create_all_tables()
    try:
        yield module
    finally:
        pg.engine, pg.SessionLocal, settings.use_postgres, settings.database_path = prev


def test_private_comments_filtered_by_viewer(comment_db):
    pub = comment_db.create_comment("p", "e", "u1", "Alice", None, "public msg", is_public=True)
    priv = comment_db.create_comment("p", "e", "u1", "Alice", None, "secret", is_public=False)
    assert priv["is_public"] is False

    # Anonymous: only the public one
    anon = comment_db.get_comments("p", "e")
    assert {c["id"] for c in anon} == {pub["id"]}

    # Author sees own private
    mine = comment_db.get_comments("p", "e", viewer_id="u1")
    assert {c["id"] for c in mine} == {pub["id"], priv["id"]}

    # Other user does not
    other = comment_db.get_comments("p", "e", viewer_id="u2")
    assert {c["id"] for c in other} == {pub["id"]}

    # Admin sees everything
    admin = comment_db.get_comments("p", "e", viewer_id="u2", is_admin=True)
    assert {c["id"] for c in admin} == {pub["id"], priv["id"]}


def test_reply_lookup_and_delete(comment_db):
    parent = comment_db.create_comment("p", "e", "u1", "Alice", None, "first")
    reply = comment_db.create_comment("p", "e", "u2", "Bob", None, "re", parent["id"], depth=1)

    assert comment_db.get_comment_by_id(parent["id"])["depth"] == 0
    assert [c["id"] for c in comment_db.get_comments("p", "e")] == [parent["id"], reply["id"]]
    assert comment_db.get_comments("p", "other") == []

    assert comment_db.delete_comment(reply["id"]) is True
    assert comment_db.delete_comment(reply["id"]) is False
    assert comment_db.get_comment_by_id(reply["id"]) is None


def test_threads_comments_for_episode_show_only_triaged_public_ones(comment_db):
    from datetime import datetime
    from src.database.models import SocialPostLedger, ThreadsComment
    from src.database.postgres import session_scope
    from src.services.threads_comments_service import public_for_episode

    def comment(cid, post, category, **kw):
        return ThreadsComment(id=cid, root_post_id=post, username="u", text=cid,
                              category=category, posted_at=datetime(2026, 10, 1), **kw)

    with session_scope() as db:
        db.add_all([
            SocialPostLedger(platform="threads", episode_id="ep1", media_id="m1", child_ids=[]),
            SocialPostLedger(platform="threads", episode_id="post_hoc:2330:ep1", media_id="m2", child_ids=[]),
            SocialPostLedger(platform="threads", episode_id="xep1", media_id="m3", child_ids=[]),
            SocialPostLedger(platform="facebook", episode_id="ep1", media_id="m4", child_ids=[]),
            comment("good", "m1", "substantive", status="replied", draft="sent"),
            comment("drafted", "m2", "question", draft="unsent draft"),
            comment("hostile", "m1", "hostile"),
            comment("untriaged", "m1", None),
            comment("other-episode", "m3", "praise"),
            comment("facebook", "m4", "praise"),
        ])

    out = {c["id"]: c for c in public_for_episode("ep1")}
    assert set(out) == {"good", "drafted"}
    assert out["good"]["reply"] == "sent"
    assert out["drafted"]["reply"] is None          # an unsent draft never leaks
    assert out["good"]["posted_at"] == "2026-10-01T00:00:00Z"
    assert public_for_episode("nope") == []
