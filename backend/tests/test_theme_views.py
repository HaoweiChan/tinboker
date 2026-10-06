"""Theme views: write path, run grouping, and the members-only card feed."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import user_db
from src.database.models import Base, ThemeView, User
from src.routers import theme_views as router
from src.utils.auth import create_jwt_token

DAY_MS = 86_400_000
T0 = int(datetime(2026, 2, 28, 8, tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'themes.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    @contextmanager
    def scope():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    monkeypatch.setattr(router, "session_scope", scope)
    monkeypatch.setattr(user_db, "session_scope", scope)
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_emails", ["admin@example.com"])
    monkeypatch.setattr(settings, "jwt_secret_key", "theme-test-jwt")
    monkeypatch.setattr(settings, "tinboker_write_token", "write-token")
    now = datetime.now(timezone.utc)
    with scope() as db:
        db.add(User(id="member", google_id="member", email="member@example.com", name="m",
                    member_until=now + timedelta(days=30), created_at=now, updated_at=now))
        db.add(User(id="free", google_id="free", email="free@example.com", name="f", created_at=now, updated_at=now))
    app = FastAPI()
    app.include_router(router.router)
    return TestClient(app), scope


def bearer(user):
    return {"Authorization": "Bearer " + create_jwt_token(user, f"{user}@example.com")}


WRITER = {"Authorization": "Bearer write-token"}


def view(label="被動元件 MLCC", exposure="sector_mlcc", **over):
    base = {"theme_label": label, "exposure_id": exposure, "stance": "bullish", "conviction": "tentative",
            "thesis": "中低階產能被排擠，可能出現缺貨。", "start_ms": 1461895,
            "tickers": [{"ticker": "2327", "name": "國巨", "role": "beneficiary"},
                        {"ticker": "6762", "name": "TDK", "role": "context"}],
            "quote": "比較偏向猜測的狀態"}
    return {**base, **over}


def put(client, episode, ms, views, ep="640", podcaster="Gooaye 股癌", headers=WRITER):
    return client.put(f"/api/theme-views/episode/{episode}", headers=headers, json={
        "podcaster": podcaster, "episode_number": ep, "released_at_ms": ms, "theme_views": views})


def test_write_requires_the_service_token_and_replaces_the_episode(api):
    client, scope = api
    assert put(client, "e1", T0, [view()], headers=bearer("member")).status_code == 403
    assert put(client, "e1", T0, [view(), view("矽光子", None)]).json() == {"episode_id": "e1", "stored": 2}
    # Re-running an episode replaces its rows; two labels on one theme keep the first.
    assert put(client, "e1", T0, [view(), view("MLCC", "sector_mlcc", stance="bearish")]).json()["stored"] == 1
    with scope() as db:
        row = db.query(ThemeView).one()
        assert (row.theme_key, row.stance, row.episode_number) == ("sector_mlcc", "bullish", "640")
    assert put(client, "e1", T0, []).json()["stored"] == 0
    assert put(client, "e1", T0, [view(stance="neutral")]).status_code == 422
    assert put(client, "e1", T0, [view()] * 4).status_code == 422


def test_cards_are_members_only_and_private(api):
    client, _ = api
    put(client, "e1", T0, [view()])
    assert client.get("/api/theme-views/cards").status_code in (401, 403)
    assert client.get("/api/theme-views/cards", headers=bearer("free")).status_code == 402
    response = client.get("/api/theme-views/cards", headers=bearer("member"))
    assert response.status_code == 200 and "private" in response.headers["cache-control"]


def test_runs_anchor_on_the_first_mention_and_split_after_a_long_gap(api):
    client, _ = api
    put(client, "e1", T0, [view()], ep="640")
    put(client, "e2", T0 + 35 * DAY_MS, [view(conviction="firm", tickers=[
        {"ticker": "2327", "name": "國巨", "role": "beneficiary"},
        {"ticker": "2492", "name": "華新科", "role": "beneficiary"}])], ep="650")
    put(client, "e3", T0 + 35 * DAY_MS + 60 * DAY_MS, [view(stance="bearish")], ep="667")
    put(client, "e4", T0 + 10 * DAY_MS, [view("矽光子", None, tickers=[])], ep="643", podcaster="Other")
    cards = client.get("/api/theme-views/cards", headers=bearer("member")).json()
    assert [c["mentions"][0]["episode_number"] for c in cards] == ["667", "640", "643"]  # newest run first
    run = next(c for c in cards if c["first_ms"] == T0)
    assert [m["episode_number"] for m in run["mentions"]] == ["640", "650"]
    assert run["latest_ms"] == T0 + 35 * DAY_MS
    # Beneficiaries only, most-mentioned first; the context name (TDK) is not measured.
    assert run["tickers"] == [{"ticker": "2327", "name": "國巨", "mentions": 2},
                              {"ticker": "2492", "name": "華新科", "mentions": 1}]
    only = client.get("/api/theme-views/cards?podcaster=Other", headers=bearer("member")).json()
    assert [c["theme_key"] for c in only] == ["label:矽光子"] and only[0]["tickers"] == []
    assert len(client.get("/api/theme-views/cards?limit=1", headers=bearer("member")).json()) == 1


def test_theme_key_normalises_free_labels():
    assert router.theme_key(" 矽光子 ", None) == router.theme_key("矽光子", None) == "label:矽光子"
    assert router.theme_key("ＣＰＵ", None) == "label:cpu"
    assert router.theme_key("anything", "sector_x") == "sector_x"
