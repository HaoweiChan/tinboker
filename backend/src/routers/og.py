"""Public cover images for syndicated copies.

Deliberately unauthenticated: the whole point is that vocus, Substack, and any social
card crawler can fetch the URL we hand them. It exposes nothing an episode page does not
already show — the podcast name and the episode title.
"""
import asyncio
import base64
import logging
import mimetypes
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from datetime import date, timedelta

from sqlalchemy import distinct, func

from src.cache.redis_client import cache_get, cache_set
from src.database.models import ContentMention, StockTranslation, TagRegistry
from src.database.postgres import get_session
from src.services.attention import scope_mentions
from src.services.gcs_content import GCSContentService, media_path
from src.services.og_image import episode_cover_png, episode_cover_svg, svg_to_png
from src.services.podcast import PodcastService
from src.services.stock import StockService
from src.services.stock_card import SIZE as CARD_SIZE, stock_card_svg
from src.services.weekly_card import (
    MAX_ROWS, MIN_MENTIONS, THEME_MIN_MENTIONS, movers_card_svg, short_name,
    theme_rows, ticker_rows,
)
from src.services.syndication_markdown import podcast_short_name, syndication_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/og", tags=["og"])
podcast_service = PodcastService()
stock_service = StockService()

# A day: the title never changes after ingest, and the syndication platforms refetch on
# their own schedule regardless.
_CACHE_CONTROL = "public, max-age=86400"

# Show artwork changes about never, and it is inlined into every cover we draw, so the
# result is cached rather than rebuilt per request.
_ART_CACHE_TTL = 7 * 24 * 3600
_ART_MAX_BYTES = 512 * 1024


async def _cover_bytes(url: str) -> tuple[bytes, str]:
    """Artwork as ``(bytes, content_type)`` — off our own disk when it is mirrored.

    ``content_sources.cover_image_url`` points at the media host once
    ``mirror_podcast_covers`` has run, and that maps to a file on the disk this process
    already has mounted, so the common path is a local read with no network at all. The
    HTTP branch stays for rows the mirror has not reached yet (it runs in the
    background after boot) and for anything pointing somewhere else entirely.
    """
    parsed = GCSContentService.parse_gs_url(url)
    if parsed:
        path = media_path(*parsed)
        data = await asyncio.to_thread(path.read_bytes)
        return data, mimetypes.guess_type(path.name)[0] or ""
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(url)
    if resp.status_code != 200:
        return b"", ""
    return resp.content, resp.headers.get("content-type", "").split(";", 1)[0].strip()


async def _cover_data_uri(podcast_name: str) -> str:
    """Show artwork as a data: URI, or "" if it cannot be had.

    Never raises: a cover without artwork is a perfectly good cover, and neither a
    missing file nor a failed fetch is a reason to fail the request — this endpoint is
    what the syndication crawlers hit, so it degrades rather than 500s.
    """
    if not podcast_name:
        return ""
    key = f"og:art:{podcast_name}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    try:
        covers = await podcast_service._podcast_cover_map()
        url = (covers or {}).get(podcast_name, "")
        if not url:
            return ""
        data, content_type = await _cover_bytes(url)
        if not data or not content_type.startswith("image/"):
            return ""
        if len(data) > _ART_MAX_BYTES:
            logger.info("og: artwork for %s too large (%d bytes)", podcast_name, len(data))
            return ""
        uri = f"data:{content_type};base64,{base64.b64encode(data).decode()}"
    except Exception as e:  # noqa: BLE001 — the cover degrades, it does not fail
        logger.info("og: artwork fetch failed for %s (%s)", podcast_name, e)
        return ""
    await cache_set(key, uri, ttl=_ART_CACHE_TTL)
    return uri


async def _episode_svg(episode_id: str) -> str:
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    raw_title = (getattr(episode, "episode_title", None) or "").strip() or episode_id

    # The cover has to say what the post is called, so it is built from the same
    # syndication_title() the publishers use — reading episode_title directly meant the
    # cover said "EP684 | 🔦" while the post was "股癌 EP684 | 🔦 摘要". The show's name
    # is then dropped from the line because the kicker above it already carries it.
    short = podcast_short_name(podcast_name)
    full = syndication_title(podcast_name, raw_title)
    title = full[len(short):].strip() if short and full.startswith(short) else full

    return episode_cover_svg(title, kicker=short,
                             cover_data_uri=await _cover_data_uri(podcast_name))


@router.get("/episode/{episode_id}.svg")
async def episode_cover(episode_id: str) -> Response:
    """The cover as SVG. Kept because already-published articles reference this URL."""
    return Response(content=await _episode_svg(episode_id), media_type="image/svg+xml",
                    headers={"Cache-Control": _CACHE_CONTROL})


@router.get("/episode/{episode_id}.png")
async def episode_cover_raster(episode_id: str) -> Response:
    """The cover as PNG — what social crawlers need, since og:image ignores SVG.

    A failure here is loud on purpose. Serving the SVG instead would produce a 200 with
    a card that silently never renders, and silent success is the failure mode that has
    cost the most time on this integration.
    """
    svg = await _episode_svg(episode_id)
    try:
        png = await asyncio.to_thread(episode_cover_png, svg)
    except Exception as e:  # noqa: BLE001 — surfaced, never swapped for the SVG
        logger.exception("og: PNG rasterisation failed for %s", episode_id)
        raise HTTPException(status_code=500, detail=f"cover rasterisation failed: {e}") from e
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": _CACHE_CONTROL})


# A stock card goes stale the moment the price moves, so it cannot share the episode
# cover's day-long TTL. Fifteen minutes is long enough that a post going around does not
# re-rasterise per viewer, short enough that the card is never wrong by a session.
# ponytail: no Redis layer on the PNG bytes — the two reads underneath are already
# cached and the CDN holds the raster; add one if rasterisation shows up in profiles.
_STOCK_CACHE_CONTROL = "public, max-age=900"


def _daily_mentions(ticker: str, since: str, allowed: Optional[frozenset]) -> list[dict]:
    """One row per calendar day this ticker was talked about, since ``since``.

    Counted in SQL rather than pulled row-by-row: the busiest tickers carry 200+ mentions
    a quarter and the card only ever draws the daily totals. Sync on purpose — the caller
    runs it through ``asyncio.to_thread`` because ``get_session`` is a sync SQLAlchemy
    session and holding one on the event loop stalls every other request.
    """
    day = func.date(ContentMention.mentioned_at)
    bull = func.count(1).filter(ContentMention.sentiment_label.like("%BULLISH%"))
    bear = func.count(1).filter(ContentMention.sentiment_label.like("%BEARISH%"))
    for db in get_session():
        rows = (
            scope_mentions(db.query(day, func.count(1), bull, bear), allowed)
            .filter(ContentMention.mention_type == "ticker",
                    ContentMention.ticker == ticker,
                    ContentMention.mentioned_at >= since)
            .group_by(day)
            .all()
        )
        return [{"d": str(d), "n": n, "bull": b, "bear": r} for d, n, b, r in rows]
    return []


@router.get("/stock/{ticker}.png")
async def stock_card_raster(
    # Constrained here rather than downstream: this value is interpolated into a
    # Content-Disposition filename, and a header is the wrong place to find out that a
    # path parameter could contain quotes or newlines.
    ticker: str = Path(..., pattern=r"^[A-Za-z0-9.\-]{1,20}$"),
    days: int = Query(90, ge=20, le=250, description="Trading sessions to draw"),
    download: bool = Query(False, description="Send as an attachment rather than inline"),
) -> Response:
    """One ticker as a square PNG — candles, volume, and the podcast bull/bear split.

    Public and unauthenticated like the rest of this router: it shows nothing a stock
    page does not already show. ``?download=1`` is what the frontend button uses — the
    HTML ``download`` attribute is ignored cross-origin, so the header has to say it.
    """
    ticker = ticker.upper()
    stock = await stock_service.get_stock_info_async(ticker, timeframe="1Y")
    if not stock or not stock.chartData:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")

    since = stock.chartData[max(0, len(stock.chartData) - days)].date
    # Roster resolved here (async, cached) and handed into the thread: the card must
    # count the same shows the stock page does, not every row in the store.
    allowed = await podcast_service._allowed_podcast_names()
    mentions = await asyncio.to_thread(_daily_mentions, ticker, since, allowed)

    svg = stock_card_svg(stock.model_dump(), mentions, days)
    try:
        png = await asyncio.to_thread(svg_to_png, svg, CARD_SIZE, CARD_SIZE)
    except Exception as e:  # noqa: BLE001 — surfaced, never swapped for the SVG
        logger.exception("og: stock card rasterisation failed for %s", ticker)
        raise HTTPException(status_code=500, detail=f"card rasterisation failed: {e}") from e

    headers = {"Cache-Control": _STOCK_CACHE_CONTROL}
    if download:
        stamp = stock.chartData[-1].date
        headers["Content-Disposition"] = f'attachment; filename="{ticker}-{stamp}.png"'
    return Response(content=png, media_type="image/png", headers=headers)


def _week_counts(db, start: date, end: date, allowed: Optional[frozenset]) -> dict[str, dict]:
    """Per-ticker mention totals for one week, with the sentiment split."""
    rows = (
        scope_mentions(db.query(
            ContentMention.ticker,
            func.count(1),
            func.count(1).filter(ContentMention.sentiment_label.like("%BULLISH%")),
            func.count(1).filter(ContentMention.sentiment_label.like("%BEARISH%")),
            func.count(distinct(ContentMention.podcaster)),
        ), allowed)
        .filter(ContentMention.mention_type == "ticker",
                ContentMention.ticker.isnot(None),
                ContentMention.mentioned_at >= start,
                ContentMention.mentioned_at < end)
        .group_by(ContentMention.ticker)
        .all()
    )
    return {t: {"n": n, "bull": b, "bear": r, "casts": c} for t, n, b, r, c in rows}


def _weekly_movers(week_start: date, allowed: Optional[frozenset]) -> dict:
    """The week's biggest risers in podcast mention count.

    Ranked by the CHANGE, not the count: ranking by count returns the same handful of
    mega-caps every week, which is true and useless for a recap. Checked against ten
    weeks of production data, the change ranking led with a different story each week.
    """
    end = week_start + timedelta(days=7)
    prev_start = week_start - timedelta(days=7)
    for db in get_session():
        now = _week_counts(db, week_start, end, allowed)
        before = _week_counts(db, prev_start, week_start, allowed)
        rows = []
        for ticker, cur in now.items():
            if cur["n"] < MIN_MENTIONS:
                continue
            prev = before.get(ticker, {}).get("n", 0)
            if cur["n"] - prev <= 0:
                continue
            rows.append({"ticker": ticker, "prev": prev, **cur})
        rows.sort(key=lambda r: (r["n"] - r["prev"], r["n"]), reverse=True)
        rows = rows[:MAX_ROWS]

        names = {}
        if rows:
            for tk, zh, en, aliases in db.query(
                StockTranslation.ticker, StockTranslation.name_zh_tw,
                StockTranslation.name_en, StockTranslation.aliases,
            ).filter(StockTranslation.ticker.in_([r["ticker"] for r in rows])).all():
                names[tk] = short_name(zh, en, aliases)
        for r in rows:
            r["name"] = names.get(r["ticker"]) or ""

        return {"week_start": week_start.isoformat(),
                "week_end": (end - timedelta(days=1)).isoformat(),
                "total": sum(v["n"] for v in now.values()),
                "rows": rows}
    return {"week_start": week_start.isoformat(), "week_end": "", "total": 0, "rows": []}


@router.get("/weekly.png")
async def weekly_card_raster(
    download: bool = Query(False, description="Send as an attachment rather than inline"),
) -> Response:
    """Last complete week's biggest risers in podcast mention count, as a square PNG.

    Always the last COMPLETE week — the current one is partial, and a recap card built
    from three days of a five-day week understates every ticker on it.
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday() + 7)
    allowed = await podcast_service._allowed_podcast_names()
    data = await asyncio.to_thread(_weekly_movers, week_start, allowed)
    try:
        svg = movers_card_svg({
            "title": "本週聲量竄升",
            "subtitle": "Podcast 提及次數較上週增幅最大的標的",
            "caption": f'本週全市場提及 {data["total"]:,} 次，'
                       f'以下為本週至少 {MIN_MENTIONS} 次者',
            "week_start": data["week_start"], "week_end": data["week_end"],
            "rows": ticker_rows(data["rows"]),
        })
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"no movers for that week: {e}") from e

    try:
        png = await asyncio.to_thread(svg_to_png, svg, CARD_SIZE, CARD_SIZE)
    except Exception as e:  # noqa: BLE001 — surfaced, never swapped for the SVG
        logger.exception("og: weekly card rasterisation failed (%s)", week_start)
        raise HTTPException(status_code=500, detail=f"card rasterisation failed: {e}") from e

    headers = {"Cache-Control": "public, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="tinboker-weekly-{week_start}.png"'
    return Response(content=png, media_type="image/png", headers=headers)


def _theme_week_counts(db, start: date, end: date, allowed: Optional[frozenset]) -> dict[str, dict]:
    """Per-theme mention totals for one week. Sector rows carry no sentiment."""
    rows = (
        scope_mentions(db.query(ContentMention.exposure_id, func.count(1),
                                func.count(distinct(ContentMention.podcaster))), allowed)
        .filter(ContentMention.mention_type == "sector",
                ContentMention.exposure_id.isnot(None),
                ContentMention.mentioned_at >= start,
                ContentMention.mentioned_at < end)
        .group_by(ContentMention.exposure_id)
        .all()
    )
    return {e: {"n": n, "casts": c} for e, n, c in rows}


def _theme_movers(week_start: date, allowed: Optional[frozenset]) -> dict:
    """The week's biggest risers in theme discussion, with a few member tickers each.

    A theme's name is not self-explanatory — "矽光子與 CPO" means little until 穩懋 and
    聯亞 are sitting next to it — so the registry's member list is carried through to
    the card.
    """
    end = week_start + timedelta(days=7)
    for db in get_session():
        now = _theme_week_counts(db, week_start, end, allowed)
        before = _theme_week_counts(db, week_start - timedelta(days=7), week_start, allowed)
        rows = []
        for exposure_id, cur in now.items():
            if cur["n"] < THEME_MIN_MENTIONS:
                continue
            prev = before.get(exposure_id, {}).get("n", 0)
            if cur["n"] - prev <= 0:
                continue
            rows.append({"exposure_id": exposure_id, "prev": prev, **cur})
        rows.sort(key=lambda r: (r["n"] - r["prev"], r["n"]), reverse=True)
        rows = rows[:MAX_ROWS]

        if rows:
            meta = {
                e: (zh, members or [])
                for e, zh, members in db.query(
                    TagRegistry.exposure_id, TagRegistry.display_zh, TagRegistry.members,
                ).filter(TagRegistry.exposure_id.in_([r["exposure_id"] for r in rows])).all()
            }
            for r in rows:
                zh, members = meta.get(r["exposure_id"], ("", []))
                r["name"] = zh or r["exposure_id"]
                r["member_count"] = len(members)
                r["members"] = [
                    {"ticker": m.get("ticker", ""), "name": m.get("name", "")}
                    for m in members[:3] if m.get("ticker")
                ]

        return {"week_start": week_start.isoformat(),
                "week_end": (end - timedelta(days=1)).isoformat(),
                "total": sum(v["n"] for v in now.values()), "rows": rows}
    return {"week_start": week_start.isoformat(), "week_end": "", "total": 0, "rows": []}


@router.get("/weekly-themes.png")
async def weekly_themes_raster(
    download: bool = Query(False, description="Send as an attachment rather than inline"),
) -> Response:
    """Last complete week's biggest risers in theme discussion, as a square PNG."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday() + 7)
    allowed = await podcast_service._allowed_podcast_names()
    data = await asyncio.to_thread(_theme_movers, week_start, allowed)
    try:
        svg = movers_card_svg({
            "title": "本週題材竄升",
            "subtitle": "Podcast 討論次數較上週增幅最大的題材",
            "caption": f'本週題材共被提及 {data["total"]:,} 次',
            "week_start": data["week_start"], "week_end": data["week_end"],
            "rows": theme_rows(data["rows"]),
        })
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"no theme movers for that week: {e}") from e

    try:
        png = await asyncio.to_thread(svg_to_png, svg, CARD_SIZE, CARD_SIZE)
    except Exception as e:  # noqa: BLE001 — surfaced, never swapped for the SVG
        logger.exception("og: theme card rasterisation failed (%s)", week_start)
        raise HTTPException(status_code=500, detail=f"card rasterisation failed: {e}") from e

    headers = {"Cache-Control": "public, max-age=3600"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="tinboker-themes-{week_start}.png"'
    return Response(content=png, media_type="image/png", headers=headers)
