"""Comment public/private visibility filtering (feedback board)."""
import tempfile, os
from src.config import settings


def test_private_comments_filtered_by_viewer():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings.database_path = path
    from src.database.db import init_db
    from src.database import comment_db
    init_db()

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

    os.remove(path)


if __name__ == "__main__":
    test_private_comments_filtered_by_viewer()
    print("ok")
