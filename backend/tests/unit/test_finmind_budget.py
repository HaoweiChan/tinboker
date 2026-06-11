"""Unit tests for the FinMind free-tier hourly request budget."""

import importlib


def _fresh_budget(monkeypatch, cap):
    """Reload the module with a forced cap and no Redis (use the local counter)."""
    monkeypatch.setenv("FINMIND_HOURLY_CAP", str(cap))
    import src.services.finmind_budget as budget
    budget = importlib.reload(budget)
    # Force the in-process fallback path so the test is hermetic (no real Redis).
    budget._redis_unavailable = True
    budget._redis_client = None
    budget._local_window = ""
    budget._local_count = 0
    return budget


def test_consume_allows_up_to_cap_then_blocks(monkeypatch):
    budget = _fresh_budget(monkeypatch, cap=3)
    assert budget.consume() is True   # 1
    assert budget.consume() is True   # 2
    assert budget.consume() is True   # 3
    assert budget.consume() is False  # 4 — over cap
    assert budget.consume() is False  # stays blocked within the window


def test_weight_is_respected(monkeypatch):
    budget = _fresh_budget(monkeypatch, cap=5)
    assert budget.consume(weight=5) is True   # exactly at cap
    assert budget.consume(weight=1) is False  # over


def test_remaining_decrements(monkeypatch):
    budget = _fresh_budget(monkeypatch, cap=10)
    assert budget.remaining() == 10
    budget.consume(weight=4)
    assert budget.remaining() == 6


def test_window_rollover_resets(monkeypatch):
    budget = _fresh_budget(monkeypatch, cap=2)
    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False
    # Simulate the clock-hour rolling over by clearing the recorded window.
    budget._local_window = "stale-window"
    assert budget.consume() is True  # new window → budget refreshed
