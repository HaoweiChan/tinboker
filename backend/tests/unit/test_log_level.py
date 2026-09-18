"""Root log level comes from LOG_LEVEL (default WARNING).

Nothing configured logging before, so every logger.info() in the codebase was dropped by
the root logger's WARNING default: on 2026-09-18 the newly re-enabled US OHLC warmer ran
for 20 minutes with no output at all and only a Postgres query could tell it was working.
"""
import logging

from src.config import Settings


def _level_for(value: str | None) -> int:
    """Mirror of main.py's mapping (kept trivial there on purpose)."""
    settings = Settings() if value is None else Settings(log_level=value)
    return getattr(logging, settings.log_level.strip().upper(), logging.WARNING)


def test_default_keeps_todays_behaviour():
    assert Settings().log_level == "WARNING"
    assert _level_for(None) == logging.WARNING


def test_info_turns_the_warmers_reporting_on():
    assert _level_for("INFO") == logging.INFO
    assert _level_for(" info ") == logging.INFO


def test_a_nonsense_level_falls_back_to_warning():
    assert _level_for("chatty") == logging.WARNING
