"""
Pytest configuration and fixtures
"""
import pytest
import sqlite3
import os
import sys
import tempfile
from pathlib import Path
from src.database.db import init_db, get_connection
from src.config import settings


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Force a clean process exit after the test summary is printed.

    Starlette's TestClient (used across the integration tests without a context
    manager) leaks non-daemon anyio worker threads, which idle forever in queue.get.
    Python's interpreter shutdown joins all non-daemon threads, so the process hangs
    in threading._shutdown after every test has passed — on CI this stalled the job
    for 30+ minutes. The pass/fail summary has already been emitted by this point, so
    exit immediately with the real status instead of waiting on threads that will
    never return. (This is a test-harness artifact only; production runs under uvicorn,
    not TestClient.)
    """
    # Print an explicit result line — os._exit skips pytest's own trailing summary.
    print(
        f"\n[conftest] session complete: {session.testscollected} collected, "
        f"{session.testsfailed} failed (exitstatus={int(exitstatus)}); forcing clean exit.",
        flush=True,
    )
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(exitstatus))


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary in-memory SQLite database for testing"""
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    # Temporarily override database path
    original_path = settings.database_path
    settings.database_path = db_path
    
    try:
        # Initialize database
        init_db()
        yield db_path
    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
        settings.database_path = original_path


@pytest.fixture(scope="function")
def db_connection(test_db):
    """Get database connection for testing"""
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def orm_db(monkeypatch):
    """Point the ORM (src.database.postgres) at a fresh in-memory SQLite database.

    Everything that goes through ``session_scope`` — users, notifications — then runs
    against real SQL instead of a mock. StaticPool keeps the single in-memory database
    alive across sessions/threads.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database import postgres
    import src.database.models  # noqa: F401 — registers the tables on Base.metadata

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    postgres.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(postgres, "engine", engine)
    monkeypatch.setattr(
        postgres, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    yield engine
    engine.dispose()


@pytest.fixture
def sample_stock_data():
    """Sample stock data for testing"""
    return {
        "ticker": "TEST",
        "name": "Test Company",
        "price": 100.0,
        "change": 5.0,
        "change_percent": 5.26,
        "market_cap": 1000000000,
        "revenue": 50000000,
        "pe": 20.0,
        "dividend_yield": 2.5,
        "about": "A test company",
        "volume": 1000000,
        "beta": 1.2,
        "volatility": 0.3,
    }


@pytest.fixture
def sample_graph_data():
    """Sample graph data for testing"""
    from src.models.graph import GraphData, Node, Edge, NodeData, EdgeData, Position
    
    return GraphData(
        nodes=[
            Node(
                id="NVDA",
                type="stock",
                data=NodeData(
                    label="NVIDIA",
                    ticker="NVDA",
                    marketCapTier="large",
                ),
                position=Position(x=100.0, y=200.0),
            ),
            Node(
                id="MSFT",
                type="stock",
                data=NodeData(
                    label="Microsoft",
                    ticker="MSFT",
                    marketCapTier="large",
                ),
                position=Position(x=300.0, y=400.0),
            ),
        ],
        edges=[
            Edge(
                id="e1",
                source="NVDA",
                target="MSFT",
                label="Partnership",
                data=EdgeData(category="automation"),
            ),
        ],
    )


@pytest.fixture
def sample_news_data():
    """Sample news data for testing"""
    return {
        "event_type": "earnings",
        "date": 1704067200000,  # 2024-01-01 timestamp
        "title": "Test Earnings Report",
        "description": "Test company reports earnings",
        "content": "Full earnings report content",
        "related_tickers": ["TEST", "NVDA"],
    }


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the ORM at a throwaway SQLite file so the social tables are isolated.

    The publishers' idempotency ledger (``social_posts``) and the comment triage queue
    (``threads_comments``) live in Postgres in every deployed env, SQLite here.
    """
    from src.database import postgres as pg
    from src.database.models import SocialPostLedger, ThreadsComment

    monkeypatch.setattr(settings, "use_postgres", False)
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(pg, "engine", None)
    monkeypatch.setattr(pg, "SessionLocal", None)
    pg.init_engine()
    for model in (SocialPostLedger, ThreadsComment):
        model.__table__.create(bind=pg.engine, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def _reset_sector_redirects_memo():
    """sector_redirects() memoises the registry map for 60s in-process; never let one
    test's snapshot (or a cached empty map from a DB-less test) leak into the next."""
    from src import tag_registry

    tag_registry._redirects_cache = (0.0, {})
    yield
    tag_registry._redirects_cache = (0.0, {})
