"""
Migration for TKB-001 — podcast ticker / sector performance tracking.

Creates content_mentions, ticker_performance_snapshots and
sector_performance_snapshots. Idempotent (CREATE TABLE IF NOT EXISTS via
checkfirst); safe to re-run. Tables are also picked up by the startup
create_all, so this script is for explicit/manual rollout.
"""

import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from src.database.postgres import Base, init_engine, engine  # noqa: E402
from src.database.models import (  # noqa: E402
    ContentMention,
    SectorPerformanceSnapshot,
    TickerPerformanceSnapshot,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MENTION_TABLES = [
    ContentMention.__table__,
    TickerPerformanceSnapshot.__table__,
    SectorPerformanceSnapshot.__table__,
]


def main():
    """Create the TKB-001 mention + performance snapshot tables."""
    logger.info("Creating mention/performance tables...")
    init_engine()
    logger.info(f"Database engine initialized. Using: {engine.url}")
    Base.metadata.create_all(bind=engine, tables=MENTION_TABLES, checkfirst=True)
    logger.info("Created: %s", ", ".join(t.name for t in MENTION_TABLES))


if __name__ == "__main__":
    main()
