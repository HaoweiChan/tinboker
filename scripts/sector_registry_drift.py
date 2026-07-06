#!/usr/bin/env python3
"""Report tag_registry sector-member drift against the committed seed.

Read-only inventory tool for TKB-009 M0. It connects to Postgres using the same
environment variable shape as the backend settings: DATABASE_URL/POSTGRES_URL or
POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "backend" / "src" / "data" / "sectors_seed.py"


def postgres_url_from_env() -> str:
    """Mirror backend config precedence without importing backend app settings."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    postgres_url = os.environ.get("POSTGRES_URL")
    if postgres_url:
        return postgres_url

    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise SystemExit(
            "Postgres credentials not configured. Set DATABASE_URL or POSTGRES_URL, "
            "or set POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, "
            "and POSTGRES_PASSWORD."
        )

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "podcast_db")
    user = os.environ.get("POSTGRES_USER", "podcast_user")
    encoded_password = quote(password, safe="")
    return f"postgresql://{user}:{encoded_password}@{host}:{port}/{database}"


def load_seed_members() -> dict[str, list[str]]:
    """Parse SECTORS_SEED without importing backend code."""
    tree = ast.parse(SEED_PATH.read_text(encoding="utf-8"), filename=str(SEED_PATH))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SECTORS_SEED":
                    seed = ast.literal_eval(node.value)
                    return {
                        str(sector["exposure_id"]): member_tickers(sector.get("members"))
                        for sector in seed
                    }
    raise RuntimeError(f"SECTORS_SEED assignment not found in {SEED_PATH}")


def member_tickers(members: Any) -> list[str]:
    """Return normalized unique ticker strings, preserving source order."""
    if members is None:
        return []
    if isinstance(members, str):
        members = json.loads(members)
    if not isinstance(members, list):
        raise TypeError(f"Expected members list, got {type(members).__name__}")

    tickers: list[str] = []
    seen: set[str] = set()
    for member in members:
        ticker = ""
        if isinstance(member, dict):
            ticker = str(member.get("ticker") or "").strip()
        elif member is not None:
            ticker = str(member).strip()
        if ticker and ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)
    return tickers


def ordered_difference(left: list[str], right: list[str]) -> list[str]:
    right_set = set(right)
    return [ticker for ticker in left if ticker not in right_set]


def markdown_cell(values: list[str]) -> str:
    if not values:
        return "-"
    return ", ".join(values).replace("|", "\\|")


def fetch_db_sector_members(database_url: str) -> list[tuple[str, list[str]]]:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        rows = conn.execute(
            text(
                """
                SELECT exposure_id, members
                FROM tag_registry
                WHERE kind = 'sector'
                ORDER BY exposure_id
                """
            )
        )
        return [
            (str(row.exposure_id or ""), member_tickers(row.members))
            for row in rows
            if row.exposure_id
        ]


def main() -> int:
    seed_members = load_seed_members()
    db_rows = fetch_db_sector_members(postgres_url_from_env())

    drift_rows: list[tuple[str, list[str], list[str]]] = []
    for exposure_id, db_members in db_rows:
        seed_for_sector = seed_members.get(exposure_id, [])
        only_db = ordered_difference(db_members, seed_for_sector)
        only_seed = ordered_difference(seed_for_sector, db_members)
        if only_db or only_seed:
            drift_rows.append((exposure_id, only_db, only_seed))

    if not drift_rows:
        print("No sector registry drift found.")
        return 0

    print("| exposure_id | members only in DB | members only in seed |")
    print("|---|---|---|")
    for exposure_id, only_db, only_seed in drift_rows:
        print(
            f"| {exposure_id} | {markdown_cell(only_db)} | "
            f"{markdown_cell(only_seed)} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
