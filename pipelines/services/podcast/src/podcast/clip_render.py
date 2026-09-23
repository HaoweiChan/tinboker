"""Turn a picked clip into the 1080x1080 player-style video the account posts.

The format is the one Willy settled on for EP118 (2026-09-19): cover art big and
centred over a blurred, saturated copy of itself, the date / episode title / show name
under it, and a scrubber that runs while the audio plays — elapsed on the left, counting
the position INSIDE THE EPISODE, and the clip's own remaining time on the right. No quote
text on the card; the audio carries it.

Everything here reuses infrastructure that already exists on the VPS:

  * the card is one Marp slide rendered by ``marp_service`` (/render-png), the same
    Chromium that draws the episode carousel cards — so no browser is installed for this;
  * ffmpeg is on the host (7.1.3), which is where podcast-api runs;
  * the mp4 lands in the media tree and is served by Caddy, so Threads has a public
    ``video_url`` and nothing new is exposed.

Three things that cost an afternoon to find, all in the renderer's constraints:

  * that Chromium has NO outbound network, so remote artwork renders as a broken-image
    icon. The cover must be inlined as a data URI.
  * markdown-it mangles a long data URI inside an inline ``style`` attribute, so the
    artwork goes into the THEME CSS (passed to marp-cli as a file) and never through the
    markdown.
  * ``section::after`` is Marp's own page-number pseudo-element. A veil declared there is
    silently dropped and the card renders unreadable over the blur, so the veil is a
    real div with its own z-index.

And one from ffmpeg: ``drawbox``'s ``t`` is thickness, not time, and ``crop`` has no
``eval=frame``, so neither can animate the progress fill. What works is an alpha ramp —
a solid bar whose alpha is 0 past the playhead.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BG, TEXT, MUTED, BRAND = "#0f1117", "#e7eaee", "#929baa", "#ffd23f"
ART, ART_Y, META_Y = 540, 56, 636
TRACK_X, TRACK_W, TRACK_Y, TRACK_H = 88, 904, 922, 6
CLOCK_Y, CLOCK_SIZE = 952, 26
# ASCII digits only, so the host's DejaVu is enough — no CJK font needed in ffmpeg.
CLOCK_FONT = "DejaVu Sans"
MARP_URL = os.environ.get("MARP_SERVICE_URL", "http://127.0.0.1:5004")
THEME = "tinboker-clip"


def _fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "tinboker-pipelines"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def artwork_data_uri(doc: dict, show_image_url: Optional[str] = None) -> Optional[str]:
    """The episode's cover, else the show's own.

    Whole shows carry no per-episode Spotify images (兆華 has none across 46 episodes),
    so the show cover from the platform API is not a rare fallback — it is the normal
    path for some shows."""
    images = doc.get("spotify_images") or []
    url = (sorted(images, key=len)[0] if images else None) or show_image_url
    if not url:
        return None
    try:
        return "data:image/jpeg;base64," + base64.b64encode(_fetch(url)).decode()
    except Exception as e:  # noqa: BLE001 — no cover, no card, no clip
        logger.warning("clip artwork fetch failed (%s): %r", url, e)
        return None


def card_theme_css(art_data_uri: str) -> str:
    """The Marp theme for one square card. The artwork is baked in here on purpose —
    see the module docstring for what happens when it goes in the markdown instead."""
    return f"""
/* @theme {THEME} */
/* @size 1:1 1080px 1080px */
section {{
  width:1080px; height:1080px; box-sizing:border-box; margin:0; padding:0;
  background:{BG}; color:{TEXT}; position:relative; overflow:hidden;
  font-family:'Noto Sans TC','Noto Sans CJK TC','PingFang TC','Microsoft JhengHei',sans-serif;
}}
section::before {{ content:""; position:absolute; inset:-140px;
  background-image:url('{art_data_uri}'); background-size:cover; background-position:center;
  filter:blur(70px) saturate(1.9); }}
section .veil {{ position:absolute; z-index:1; inset:0; background:linear-gradient(180deg,
  rgba(15,17,23,.42) 0%, rgba(15,17,23,.72) 52%, rgba(15,17,23,.96) 100%); }}
section .art {{ position:absolute; z-index:2; left:{(1080 - ART) // 2}px; top:{ART_Y}px;
  width:{ART}px; height:{ART}px; border-radius:28px;
  background-image:url('{art_data_uri}'); background-size:cover; background-position:center;
  box-shadow:0 30px 70px rgba(0,0,0,.55); }}
section .meta {{ position:absolute; z-index:2; left:88px; right:88px; top:{META_Y}px; }}
section .date {{ font-size:30px; color:{MUTED}; letter-spacing:.5px; }}
section h1 {{ font-size:52px; font-weight:900; line-height:1.24; margin:10px 0 14px;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
section .show {{ font-size:32px; color:{MUTED}; }}
section .track {{ position:absolute; z-index:2; left:{TRACK_X}px; top:{TRACK_Y}px;
  width:{TRACK_W}px; height:{TRACK_H}px; border-radius:3px; background:rgba(255,255,255,.16); }}
section .mark {{ position:absolute; z-index:2; right:88px; bottom:26px; font-size:24px;
  font-weight:700; color:{BRAND}; letter-spacing:1px; opacity:.9; }}
"""


def card_markdown(date: str, title: str, show: str) -> str:
    """One slide. Structure only — every URL lives in the theme."""
    return (f"---\nmarp: true\ntheme: {THEME}\nsize: 1:1\npaginate: false\n---\n\n"
            f'<div class="veil"></div>\n<div class="art"></div>\n'
            f'<div class="meta"><div class="date">{date}</div>\n\n'
            f"# {title}\n\n"
            f'<div class="show">{show}</div></div>\n'
            f'<div class="track"></div><div class="mark">TinBoker</div>\n')


def render_card(markdown: str, theme_css: str, timeout: int = 120) -> bytes:
    """PNG bytes from the Marp service, which owns the only Chromium we have."""
    payload = json.dumps({"markdown": markdown, "theme_css": theme_css}).encode()
    req = urllib.request.Request(f"{MARP_URL.rstrip('/')}/render-png", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.load(r)
    images = body.get("images") or []
    if not images:
        raise RuntimeError(f"marp service returned no image: {str(body)[:200]}")
    return base64.b64decode(images[0])


def _clock(expr: str, x: str) -> str:
    return (f"drawtext=text='{expr}':x={x}:y={CLOCK_Y}:fontsize={CLOCK_SIZE}:"
            f"fontcolor={MUTED}:font='{CLOCK_FONT}'")


def ffmpeg_args(card: Path, audio: str, start_ms: int, duration_s: float, out: Path) -> list[str]:
    """The whole compose in one pass. Split out so a test can read the filter graph."""
    bar = (f"color=c={BRAND}:s={TRACK_W}x{TRACK_H}:d={duration_s},format=rgba,"
           f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
           f"a='if(lt(X,{TRACK_W}*T/{duration_s}),255,0)'[bar]")
    start_s = start_ms / 1000
    elapsed = (f"%{{eif\\:({start_s}+t)/60\\:d}}\\:%{{eif\\:mod({start_s}+t\\,60)\\:d\\:2}}")
    left = f"-%{{eif\\:({duration_s}-t)/60\\:d}}\\:%{{eif\\:mod({duration_s}-t\\,60)\\:d\\:2}}"
    graph = (f"[0:v]null[card];{bar};[card][bar]overlay={TRACK_X}:{TRACK_Y}[p];"
             f"[p]{_clock(elapsed, str(TRACK_X))},{_clock(left, f'{TRACK_X + TRACK_W}-tw')}[v]")
    return ["ffmpeg", "-y", "-loop", "1", "-i", str(card),
            "-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}", "-i", audio,
            "-filter_complex", graph, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", "25", "-c:a", "aac", "-b:a", "160k", "-t", f"{duration_s:.3f}", str(out)]


def render_clip(doc: dict, clip: dict, *, show_image_url: Optional[str] = None,
                episode_id: Optional[str] = None) -> Optional[str]:
    """Render the clip and return its public URL, or None when it cannot be made.

    None is never an error the caller should raise on: a missing cover or a missing
    audio file simply means this episode gets no clip today."""
    from src.service.gcs_storage_service import GCSStorageService

    art = artwork_data_uri(doc, show_image_url)
    audio = doc.get("mp3_public_url") or doc.get("mp3_url")
    if not art or not audio:
        logger.info("clip render skipped for %s (art=%s audio=%s)",
                    episode_id, bool(art), bool(audio))
        return None

    title = (doc.get("episode_title") or doc.get("title") or "").strip()
    date = (doc.get("spotify_release_date") or "").replace("-", ".")
    duration_s = (clip["end_ms"] - clip["start_ms"]) / 1000

    with tempfile.TemporaryDirectory() as tmp:
        card = Path(tmp) / "card.png"
        card.write_bytes(render_card(card_markdown(date, title, doc.get("podcast_name") or ""),
                                     card_theme_css(art)))
        out = Path(tmp) / "clip.mp4"
        # The audio is read over its public URL rather than off the disk beside us: the
        # media tree's layout is the storage service's business, and ffmpeg ranges the
        # 30 seconds it needs instead of reading the whole file either way.
        proc = subprocess.run(ffmpeg_args(card, audio, clip["start_ms"], duration_s, out),
                              capture_output=True, timeout=600)
        if proc.returncode != 0 or not out.is_file():
            logger.warning("ffmpeg failed for %s: %s", episode_id,
                           proc.stderr.decode("utf-8", "replace")[-400:])
            return None
        ok, url = GCSStorageService().upload_file(
            out, "clip", doc.get("podcast_name") or "", episode_id or doc.get("id") or "",
            extension="mp4", skip_existing=False)
    return url if ok else None
