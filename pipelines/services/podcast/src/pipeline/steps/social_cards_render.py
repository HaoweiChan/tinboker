"""Step 4b: Render social cards to PNGs and upload them.

Builds a TinBoker-branded Marp card deck from the episode's ``social_cards`` (cover +
one per theme), renders each slide to a 1080×1080 PNG via the marp_service
``/render-png`` endpoint, uploads them (GCS or the VPS media dir), and writes the public
URLs back into ``social_cards[i]['image_url']`` so the next step (Firestore) persists
them.

Best-effort: any failure is logged and leaves the image_urls as None — the platform
then falls back to a text/single-image post instead of a card carousel. Runs after
``upload_to_gcs`` (which assigns the episode_id + resolves the storage backend) and
before ``upload_to_firestore``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

MARP_SERVICE_URL = os.environ.get("MARP_SERVICE_URL", "http://localhost:5004")


def _render_png(markdown: str, theme_css: str, base_url: str, timeout: int = 120) -> list[str]:
    """Call the marp_service /render-png endpoint; return base64 PNGs in slide order."""
    body = json.dumps({"markdown": markdown, "theme_css": theme_css}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/render-png", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted internal URL)
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError(payload.get("error", "render failed"))
    return payload.get("images", [])


def _resolve_uploader(services: ServiceContainer):
    """Same backend resolution as upload_to_gcs: VPS media dir or GCS."""
    media_root = os.environ.get("VPS_MEDIA_ROOT")
    if media_root:
        from .gcs_upload import _LocalMediaUploader
        base_url = os.environ.get("VPS_BASE_URL", "https://podcast-api.tinboker.com/media/web")
        return _LocalMediaUploader(media_root, base_url)
    return services.gcs_service


def _cover_date(episode_data: EpisodeData) -> str:
    """Cover-card date as YYYY.MM.DD, from the feed datePublished (else today)."""
    published = (episode_data.api_data or {}).get("datePublished") or ""
    if isinstance(published, str) and len(published) >= 10 and published[4] == "-":
        return published[:10].replace("-", ".")
    created = episode_data.created_time
    dt = created if isinstance(created, datetime) else datetime.now()
    return dt.strftime("%Y.%m.%d")


def render_social_cards(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Render + upload the episode's social cards, enriching social_cards in place."""
    if config.rerun_from not in (None, "download", "transcribe", "summarize", "upload"):
        return
    summary_result = episode_data.summary_result
    if not summary_result:
        return
    cards = summary_result.get("social_cards")
    if not cards:
        return
    if not episode_data.episode_id:
        print("  ⚠ Social cards skipped: missing episode_id")
        return

    svc = _resolve_uploader(services)
    if not svc:
        print("  ⚠ Social cards skipped: no storage backend")
        return

    try:
        from src.podcast.content_builder.card_deck import (
            CARD_THEME_CSS,
            build_card_deck_markdown,
        )
        markdown = build_card_deck_markdown(
            cards, show_name=episode_data.podcast_name, date_str=_cover_date(episode_data),
        )
        images = _render_png(markdown, CARD_THEME_CSS, MARP_SERVICE_URL)
    except Exception as e:
        print(f"  ⚠ Social card render skipped: {e}")
        return

    # Index alignment is load-bearing (card i ↔ carousel image i ↔ reply i). If the
    # render produced a different count, skip rather than post a desynced thread.
    if len(images) != len(cards):
        print(f"  ⚠ Social card count mismatch ({len(images)} PNG vs {len(cards)} cards); skipping")
        return

    bucket = getattr(svc, "bucket_name", "")
    uploaded = 0
    for i, b64 in enumerate(images):
        try:
            ok, url = svc.upload_file_from_base64(
                b64, "social_cards", episode_data.podcast_name,
                f"{episode_data.episode_id}/{i}", "png", skip_existing=False,
                public=True,  # Threads fetches these by URL — must be world-readable.
            )
        except Exception as e:
            print(f"  ⚠ Social card {i} upload failed: {e}")
            continue
        if ok and url:
            blob = url.replace(f"gs://{bucket}/", "") if bucket else url
            cards[i]["image_url"] = svc.generate_public_url(blob)
            uploaded += 1

    if uploaded:
        print(f"  ✓ Rendered + uploaded {uploaded} social card image(s)")
