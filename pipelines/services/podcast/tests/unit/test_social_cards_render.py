"""Unit tests for the social_cards render+upload step (Step 4b).

Mocks the marp render call and the storage backend, so no Marp/Chrome/GCS is needed.
Covers the URL join, the count-mismatch guard (must NOT desync card↔image indices),
the skip conditions, and the cover-date formatting.
"""

from __future__ import annotations

import types
from datetime import datetime

import pytest
from src.pipeline.steps import social_cards_render as scr


class FakeUploader:
    bucket_name = "podcast-data-web"

    def __init__(self):
        self.calls = []
        self.public_flags = []

    def upload_file_from_base64(self, b64, file_type, podcast, episode_id, ext, skip_existing=True, public=False):
        self.calls.append((file_type, episode_id, ext))
        self.public_flags.append(public)
        return True, f"gs://{self.bucket_name}/{file_type}/{episode_id}.{ext}"

    def generate_public_url(self, blob):
        return f"https://cdn.tinboker.com/{blob}"


def _cfg(rerun=None):
    return types.SimpleNamespace(rerun_from=rerun)


def _services(up):
    return types.SimpleNamespace(gcs_service=up)


def _cards(n_themes=2):
    cards = [{"kind": "cover", "title": "股癌", "bullets": ["x"], "start_time_ms": None, "image_url": None}]
    for i in range(n_themes):
        cards.append({"kind": "theme", "title": f"主題{i}", "bullets": [f"重點 [0{i}:0{i}]"],
                      "start_time_ms": i * 1000, "image_url": None})
    return cards


def _ep(cards, **kw):
    sr = {"social_cards": cards} if cards is not None else None
    return types.SimpleNamespace(
        summary_result=sr, episode_id=kw.get("episode_id", "EP1"), podcast_name="股癌",
        api_data=kw.get("api_data", {"datePublished": "2026-06-06T07:00:00.000Z"}),
        created_time=kw.get("created_time"),
    )


@pytest.fixture(autouse=True)
def _no_vps(monkeypatch):
    monkeypatch.delenv("VPS_MEDIA_ROOT", raising=False)


def test_happy_path_joins_public_urls_in_order(monkeypatch):
    monkeypatch.setattr(scr, "_render_png", lambda *a, **k: ["A", "B", "C"])
    up = FakeUploader()
    cards = _cards(2)
    scr.render_social_cards(_cfg(), _services(up), _ep(cards))

    # Each URL carries a content-hash ?v= cache-buster (GCS reuses the path on
    # reprocess; the query changes iff the PNG bytes change).
    import hashlib
    def ver(b64):
        return hashlib.md5(b64.encode("utf-8")).hexdigest()[:10]
    assert [c["image_url"] for c in cards] == [
        f"https://cdn.tinboker.com/social_cards/EP1/0.png?v={ver('A')}",
        f"https://cdn.tinboker.com/social_cards/EP1/1.png?v={ver('B')}",
        f"https://cdn.tinboker.com/social_cards/EP1/2.png?v={ver('C')}",
    ]
    # Index-aware sub-path so the N PNGs don't collide.
    assert up.calls == [("social_cards", "EP1/0", "png"),
                        ("social_cards", "EP1/1", "png"),
                        ("social_cards", "EP1/2", "png")]
    # Card images must be uploaded world-readable (Threads fetches them by URL).
    assert up.public_flags == [True, True, True]


def test_count_mismatch_skips_upload(monkeypatch):
    # Render returns fewer PNGs than cards → must skip entirely (no desync).
    monkeypatch.setattr(scr, "_render_png", lambda *a, **k: ["only-one"])
    up = FakeUploader()
    cards = _cards(2)
    scr.render_social_cards(_cfg(), _services(up), _ep(cards))
    assert all(c["image_url"] is None for c in cards)
    assert up.calls == []


def test_render_failure_is_non_fatal(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("marp down")
    monkeypatch.setattr(scr, "_render_png", _boom)
    cards = _cards(1)
    scr.render_social_cards(_cfg(), _services(FakeUploader()), _ep(cards))  # must not raise
    assert all(c["image_url"] is None for c in cards)


def test_noops(monkeypatch):
    def _never(*a, **k):
        raise AssertionError("should not render")
    monkeypatch.setattr(scr, "_render_png", _never)
    # No social_cards
    scr.render_social_cards(_cfg(), _services(FakeUploader()), _ep(None))
    # validate-only rerun
    scr.render_social_cards(_cfg("validate"), _services(FakeUploader()), _ep(_cards(1)))


def test_cover_date_from_published_else_created():
    assert scr._cover_date(_ep([], api_data={"datePublished": "2026-06-06T07:00:00.000Z"})) == "2026.06.06"
    ep = _ep([], api_data={}, created_time=datetime(2025, 1, 2))
    assert scr._cover_date(ep) == "2025.01.02"
