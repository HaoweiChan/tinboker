"""Repairing ticker names already baked into stored social_cards.

A card's company name is resolved when the card is built and written into the row, so
fixing the registry only helps future episodes. 股癌 EP693 (2026-09-02) shipped with
rows reading `2454` / `NVDA` / `AVGO` / `2330`. These lock what the repair may touch —
three derived fields and the cover title — and, just as importantly, what it may not.
"""

import copy
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_ticker_card_names.py"
_spec = importlib.util.spec_from_file_location("backfill_ticker_card_names", _SCRIPT)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def _deck():
    """A deck shaped like EP693's: unresolved TW/US codes plus one already-good row."""
    return [
        {"kind": "cover", "title": "股癌 EP693", "subtitle": "EP693 | 🍖",
         "bullets": ["重點一"], "image_url": "https://cdn/0.png", "start_time_ms": None},
        {"kind": "ticker_table", "title": "本期提及標的與態度", "rows": [
            {"group": "台股", "name": "2330", "code": "", "risk": "中",
             "sentiment": "看多", "sentiment_class": "sent-bull"},
            {"group": "美股", "name": "谷歌", "code": "GOOGL", "risk": "低",
             "sentiment": "看多", "sentiment_class": "sent-bull"},
        ]},
        {"kind": "theme", "title": "主題卡不該被動到", "bullets": ["一句話 [01:00]"],
         "image_url": "https://cdn/2.png", "start_time_ms": 60000},
    ]


def _fake_registry(monkeypatch, mapping):
    """Pin the lookup so the test asserts the repair, not the live registry."""
    monkeypatch.setattr(rc, "prime_tickers", lambda syms: None)
    monkeypatch.setattr(
        rc, "_ticker_name_code",
        lambda t: (mapping[t], t) if t in mapping else (t, ""),
    )
    monkeypatch.setattr(rc, "market_for_ticker", lambda t: "TW" if t.isdigit() else "US")


def test_bare_code_gets_its_name_and_code(monkeypatch):
    _fake_registry(monkeypatch, {"2330": "台積電", "GOOGL": "谷歌"})
    new, diffs = rc.repair_cards(_deck(), "Gooaye 股癌")
    row = new[1]["rows"][0]
    assert (row["name"], row["code"], row["group"]) == ("台積電", "2330", "台股")
    assert any("2330" in d for d in diffs)


def test_an_already_correct_row_is_left_alone(monkeypatch):
    _fake_registry(monkeypatch, {"2330": "台積電", "GOOGL": "谷歌"})
    new, diffs = rc.repair_cards(_deck(), "Gooaye 股癌")
    assert new[1]["rows"][1] == _deck()[1]["rows"][1]
    assert not any("GOOGL" in d for d in diffs)


def test_cover_title_becomes_the_show_name(monkeypatch):
    _fake_registry(monkeypatch, {})
    new, diffs = rc.repair_cards(_deck(), "Gooaye 股癌")
    assert new[0]["title"] == "Gooaye 股癌"
    assert any("cover title" in d for d in diffs)


def test_nothing_outside_the_three_fields_moves(monkeypatch):
    """The blast radius is the whole point: theme cards and every other key stay put."""
    _fake_registry(monkeypatch, {"2330": "台積電", "GOOGL": "谷歌"})
    before = _deck()
    after, _ = rc.repair_cards(before, "Gooaye 股癌")
    assert before == _deck(), "input must not be mutated in place"

    def strip(deck):
        deck = copy.deepcopy(deck)
        for card in deck:
            for entry in (card.get("rows") or []) + (card.get("items") or []):
                for k in ("name", "code", "group"):
                    entry.pop(k, None)
            if card.get("kind") == "cover":
                card.pop("title", None)
        return deck

    assert strip(before) == strip(after)
    assert after[2] == before[2]  # theme card untouched


def test_unknown_symbol_stays_a_bare_code(monkeypatch):
    """No registry entry means no invention — the row keeps the symbol it had."""
    _fake_registry(monkeypatch, {})
    new, diffs = rc.repair_cards(_deck(), "Gooaye 股癌")
    row = new[1]["rows"][0]
    assert (row["name"], row["code"]) == ("2330", "")
    assert not any(d.startswith("2330") for d in diffs)


def test_focus_items_without_a_group_key_do_not_gain_one(monkeypatch):
    _fake_registry(monkeypatch, {"NVDA": "輝達"})
    deck = [{"kind": "focus_list", "title": "產業焦點", "items": [
        {"name": "NVDA", "code": "", "lead": "…", "sentiment": "看多"}]}]
    new, _ = rc.repair_cards(deck, "Gooaye 股癌")
    item = new[0]["items"][0]
    assert (item["name"], item["code"]) == ("輝達", "NVDA")
    assert "group" not in item
