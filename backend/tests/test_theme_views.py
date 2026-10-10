"""Theme views: write path, run grouping, and the members-only card feed."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import user_db
from src.database.models import Base, StockTranslation, TagRegistry, ThemeView, User
from src.routers import theme_views as router
from src.utils.auth import create_jwt_token

DAY_MS = 86_400_000
T0 = int(datetime(2026, 2, 28, 8, tzinfo=timezone.utc).timestamp() * 1000)
TW_NAMES = {
    "2327": "國巨*", "2330": "台積電", "3661": "世芯-KY", "0050": "元大台灣50",
    "2492": "華新科", "8150": "南茂科技", "6147": "頎邦", "6669": "緯穎",
    "2465": "麗臺", "2385": "群光電子", "3227": "原相", "6505": "台塑化",
    "6207": "雷科", "2456": "奇力新", "2495": "普安", "6752": "叡揚",
    "6762": "達亞", "6759": "寬量國際", "6981": "創鑫生技", "009150": "凱基優選高股息30",
    "9105": "泰金寶-DR", "1503": "士林電機", "3008": "大立光", "3653": "健策", "6526": "絡達",
    "9917": "中保科", "6976": "聯穎光電",
}
BAD_TICKERS = [
    ("8150", "頎邦"), ("6669", "微影"), ("2465", "微影"), ("2385", "維影"),
    ("3661", "漢策"), ("3661", "金豪科"), ("3227", "金豪科"), ("6505", "育邦"),
    ("6207", "和聲堂"), ("2456", "利融電"), ("2495", "預幫"), ("6752", "Panasonic"),
    ("6762", "TDK"), ("6759", "村田製作所"), ("6981", "村田"), ("009150", "三星電機"),
    ("4062", "揖斐電"), ("6976", "太陽誘電"),
]
GOOD_TICKERS = [
    ("2327", "國巨"), ("2330", "台積電"), ("3661", "世芯"), ("0050", "0050"),
    ("NVDA", "輝達"), ("NVDA", "Nvidia"), ("STM", "意法半導體"), ("VSH", "Vishay"),
    ("6996.T", "Nichicon"), ("2330", " 臺 積電 "), ("2330", "台積電股份有限公司"),
    ("8150", "南茂"), ("9105", "泰金寶"),
    # How shows and ASR actually write them: abbreviations and near-homophones.
    ("1503", "士電"), ("3008", "大力光"), ("3653", "建策"), ("6526", "達發"), ("9917", "中興保全"),
]


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
        db.add_all([StockTranslation(ticker=code, market="TW", name_zh_tw=name)
                    for code, name in TW_NAMES.items()])
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
    assert put(client, "e1", T0, [view(), view("矽光子", None)]).json() == {
        "episode_id": "e1", "stored": 2, "tickers_corrected": 0, "tickers_dropped": 2}
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
    assert run["tickers_source"] == "named"
    only = client.get("/api/theme-views/cards?podcaster=Other", headers=bearer("member")).json()
    assert [c["theme_key"] for c in only] == ["label:矽光子"] and only[0]["tickers"] == []
    assert only[0]["tickers_source"] == "none"
    assert len(client.get("/api/theme-views/cards?limit=1", headers=bearer("member")).json()) == 1


def test_theme_key_normalises_free_labels():
    assert router.theme_key(" 矽光子 ", None) == router.theme_key("矽光子", None) == "label:矽光子"
    assert router.theme_key("ＣＰＵ", None) == "label:cpu"
    assert router.theme_key("anything", "sector_x") == "sector_x"


def test_cards_use_members_only_when_the_entire_run_has_no_beneficiaries(api):
    client, scope = api
    members = [{"name": "Missing ticker", "rank": 0},
               {"ticker": "unranked", "name": "Stored first"},
               {"ticker": "second", "rank": 2},
               {"ticker": "first", "name": "Ranked first", "rank": 1},
               *[{"ticker": str(i)} for i in range(5)]]
    with scope() as db:
        db.add(TagRegistry(slug="mlcc", display_zh="被動元件", exposure_id="sector_mlcc", members=members))
    put(client, "e1", T0, [view(tickers=[{"ticker": "6762", "name": "TDK", "role": "context"}])])
    card = client.get("/api/theme-views/cards", headers=bearer("member")).json()[0]
    assert card["tickers_source"] == "members"
    assert card["tickers"] == [
        {"ticker": "first", "name": "Ranked first", "mentions": 0},
        {"ticker": "second", "name": "second", "mentions": 0},
        {"ticker": "unranked", "name": "Stored first", "mentions": 0},
        {"ticker": "0", "name": "0", "mentions": 0},
        {"ticker": "1", "name": "1", "mentions": 0},
    ]
    put(client, "e2", T0 + DAY_MS, [view()])
    card = client.get("/api/theme-views/cards", headers=bearer("member")).json()[0]
    assert card["tickers_source"] == "named"
    assert card["tickers"] == [{"ticker": "2327", "name": "國巨", "mentions": 1}]


@pytest.mark.parametrize("exposure,members", [(None, []), ("missing", []), ("sector_mlcc", []),
                                               ("sector_mlcc", [{"name": "No ticker"}])])
def test_build_cards_without_available_members(exposure, members):
    row = ThemeView(**view(exposure=exposure, tickers=[]), podcaster="Show", theme_key="theme",
                    episode_id="e1", episode_number="1", released_at=datetime(2026, 2, 28))
    card = router.build_cards([row], 1, {"sector_mlcc": members})[0]
    assert card["tickers_source"] == "none"
    assert card["tickers"] == []


def test_cards_fetch_members_in_one_query_for_multiple_themes(api):
    client, scope = api
    put(client, "e1", T0, [view(tickers=[]), view("矽光子", "sector_cpo", tickers=[])])
    with scope() as db:
        engine = db.get_bind()
    registry_queries = []

    def record_query(conn, cursor, statement, parameters, context, executemany):
        if "tag_registry" in statement:
            registry_queries.append(statement)

    event.listen(engine, "before_cursor_execute", record_query)
    try:
        assert len(router._cards(None, 60)) == 2
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
    assert len(registry_queries) == 1


def test_mentions_flag_episodes_outside_the_public_window():
    """Prod serves only recent episode pages; an older mention must say so, so the card
    shows it as text instead of a link that 404s."""
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    def row(episode_id, released_at):
        return SimpleNamespace(
            podcaster="Show", theme_key="k", theme_label="K", exposure_id=None, episode_id=episode_id,
            episode_number=None, released_at=released_at, stance="bullish", conviction="firm",
            thesis="t", start_ms=None, tickers=[], quote=None,
        )

    now = datetime.utcnow()
    rows = [row("old", now - timedelta(days=20)), row("new", now - timedelta(days=1))]
    flags = lambda cards: {m["episode_id"]: m["episode_public"] for m in cards[0]["mentions"]}  # noqa: E731
    assert flags(router.build_cards(rows, 5, {}, now - timedelta(days=7))) == {"old": False, "new": True}
    assert flags(router.build_cards(rows, 5)) == {"old": True, "new": True}


def test_copy_cards_attach_returns_for_the_social_token_only(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "tinboker_social_token", "social-token")
    put(client, "e1", T0, [view(tickers=[{"ticker": "2327", "name": "國巨", "role": "beneficiary"},
                                         {"ticker": "2492", "name": "華新科", "role": "beneficiary"}])])
    card = client.get("/api/theme-views/cards", headers=bearer("member")).json()[0]
    first, second = "2327", "2492"

    async def windows(request, _user):
        returns = {first: {"since": 10.0, "d7": 2.0, "d30": None, "d90": None},
                   second: {"since": 5.0, "d7": None, "d30": None, "d90": None}}
        return {f"{i.ticker}:{i.reference_ms}": returns[i.ticker] for i in request.items if i.ticker in returns}

    monkeypatch.setattr(router, "get_batch_prices_windows", windows)
    assert client.get("/api/theme-views/copy/cards").status_code in (401, 403)
    assert client.get("/api/theme-views/copy/cards", headers=bearer("member")).status_code == 403
    service = {"Authorization": "Bearer social-token"}
    assert client.get("/api/theme-views/copy/cards", params={"theme": "不存在"}, headers=service).json() == []
    out = client.get("/api/theme-views/copy/cards", params={"theme": card["theme_label"][:2]}, headers=service).json()[0]
    assert out["tickers"][0]["windows"]["since"] == 10.0
    assert out["averages"] == {"since": 7.5, "d7": 2.0, "d30": None, "d90": None}
    pick = {"items": [{"ticker": first, "reference_ms": card["first_ms"]}]}
    assert client.post("/api/theme-views/copy/windows", json=pick, headers=service).json() == {
        f"{first}:{card['first_ms']}": {"since": 10.0, "d7": 2.0, "d30": None, "d90": None}}


@pytest.mark.parametrize("code,name", BAD_TICKERS + GOOD_TICKERS)
def test_named_tickers_are_cleaned_on_write_and_legacy_card_reads(api, code, name):
    client, scope = api
    ticker = {"ticker": code, "name": name, "role": "beneficiary"}
    corrected = (code, name) == ("8150", "頎邦")
    dropped = (code, name) in BAD_TICKERS and not corrected
    expected = [] if dropped else [{**ticker, "ticker": "6147" if corrected else code}]
    response = put(client, "e1", T0, [view(tickers=[ticker])])
    assert response.status_code == 200
    assert response.json() == {"episode_id": "e1", "stored": 1,
                               "tickers_corrected": int(corrected), "tickers_dropped": int(dropped)}
    with scope() as db:
        row = db.query(ThemeView).one()
        assert row.tickers == expected
        row.tickers = [ticker]  # Legacy rows must be checked independently of ingestion.
    card = client.get("/api/theme-views/cards", headers=bearer("member")).json()[0]
    assert card["tickers"] == [{"ticker": t["ticker"], "name": t["name"], "mentions": 1} for t in expected]
    assert card["tickers_source"] == ("none" if dropped else "named")
    with scope() as db:
        assert db.query(ThemeView).one().tickers == [ticker]


@pytest.mark.parametrize("members", [[], [{"ticker": "2327", "name": "國巨"}]])
def test_mismatched_legacy_tickers_fall_back_to_members(api, members):
    client, scope = api
    put(client, "e1", T0, [view(tickers=[])])
    with scope() as db:
        db.query(ThemeView).one().tickers = [{"ticker": "6669", "name": "微影", "role": "beneficiary"}]
        db.add(TagRegistry(slug="mlcc", display_zh="被動元件", exposure_id="sector_mlcc", members=members))
    card = client.get("/api/theme-views/cards", headers=bearer("member")).json()[0]
    assert card["tickers_source"] == ("members" if members else "none")
    assert card["tickers"] == [{**m, "mentions": 0} for m in members]


def test_remapping_requires_a_unique_normalised_exact_name(api):
    client, scope = api
    with scope() as db:
        db.add(StockTranslation(ticker="9998", market="TW", name_zh_tw=" 頎 邦-KY*"))
    tickers = [{"ticker": "8150", "name": name, "role": "context"} for name in ("頎邦", "頎邦股份有限公司", "南")]
    result = put(client, "e1", T0, [view(tickers=tickers)]).json()
    assert result["tickers_corrected"] == 0 and result["tickers_dropped"] == 3
    with scope() as db:
        assert db.query(ThemeView).one().tickers == []


def test_remapping_uses_normalisation_and_only_taiwan_registry(api):
    client, scope = api
    with scope() as db:
        db.add(StockTranslation(ticker="FOREIGN", market="US", name_zh_tw="頎邦"))
    ticker = {"ticker": "8150", "name": " 頎 邦-KY* ", "role": "beneficiary"}
    result = put(client, "e1", T0, [view(tickers=[ticker])]).json()
    assert result["tickers_corrected"] == 1 and result["tickers_dropped"] == 0
    with scope() as db:
        assert db.query(ThemeView).one().tickers == [{**ticker, "ticker": "6147"}]


@pytest.mark.parametrize("route", ["put", "cards", "copy/cards"])
def test_ticker_registry_is_batched_once_per_request(api, monkeypatch, route):
    client, scope = api
    monkeypatch.setattr(settings, "tinboker_social_token", "social-token")
    tickers = [{"ticker": code, "name": name, "role": "beneficiary"} for code, name in BAD_TICKERS]
    views = [view(tickers=tickers), view("矽光子", "sector_cpo", tickers=tickers)]
    put(client, "e1", T0, views)
    with scope() as db:
        engine = db.get_bind()
        for row in db.query(ThemeView).all():
            row.tickers = tickers
    registry_queries = []
    priced = []

    async def windows(request, _user):
        priced.extend(i.ticker for i in request.items)
        return {}

    monkeypatch.setattr(router, "get_batch_prices_windows", windows)

    def record_query(conn, cursor, statement, parameters, context, executemany):
        if "stock_translations" in statement:
            registry_queries.append(statement)

    event.listen(engine, "before_cursor_execute", record_query)
    try:
        if route == "put":
            response = put(client, "e1", T0, views)
            assert response.json() == {"episode_id": "e1", "stored": 2,
                                       "tickers_corrected": 2, "tickers_dropped": 2 * (len(BAD_TICKERS) - 1)}
        else:
            headers = bearer("member") if route == "cards" else {"Authorization": "Bearer social-token"}
            response = client.get(f"/api/theme-views/{route}", headers=headers)
            assert len(response.json()) == 2
            assert all(c["tickers"][0]["ticker"] == "6147" and len(c["tickers"]) == 1 for c in response.json())
        assert response.status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
    assert len(registry_queries) == 1
    if route == "copy/cards":
        assert priced == ["6147", "6147"]


def test_an_empty_registry_leaves_tickers_alone():
    tickers = [{"ticker": "2327", "name": "國巨", "role": "beneficiary"}]
    assert router._clean_tickers(tickers, {}) == (tickers, 0, 0)
