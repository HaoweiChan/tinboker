"""Compose and publish episode summaries to Threads.

This is the bridge between the agents' podcast ingestion pipeline and the brand's
Threads account. It reads recent episodes (Firestore, via ``podcast_service``),
composes a zh-TW post from the contract fields the agents pipeline writes
(``key_insights``, ``related_tickers``, ``episode_title``) plus a permalink back to
``{site_url}/episode/{id}``, and publishes it.

Two guards keep it safe to run on a schedule:
  * a shared Postgres idempotency ledger, claimed *before* posting, so neither a
    re-run nor two overlapping triggers can double-post (``social_ledger``);
  * a recency window so even a wiped ledger can only ever touch episodes from the
    last few days.

With no Threads credentials configured the run is forced to ``dry_run`` — it composes
and returns the drafts without publishing — so the endpoint is always safe to call.
"""

import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.config import settings
from src.services import social_ledger
from src.services.content_source_service import social_enabled_for, speaker_for
from src.services.podcast import PodcastService
from src.services.threads_service import THREADS_MAX_CHARS, ThreadsError, ThreadsService

logger = logging.getLogger(__name__)

podcast_service = PodcastService()

MAX_INSIGHTS = 3
MAX_CARDS = 20  # Threads carousel hard limit (cover + up to 19 themes)


def _field(episode: Any, name: str, default=None):
    """Read a field from an Episode model or a plain dict interchangeably."""
    if isinstance(episode, dict):
        return episode.get(name, default)
    return getattr(episode, name, default)


def episode_url(episode_id: str) -> str:
    return f"{settings.site_url.rstrip('/')}/episode/{episode_id}"


def social_link(url: str, fmt: str) -> str:
    """``url`` tagged so GA4 can tell a Threads arrival — and which post shape sent it —
    from everything else. Measured 2026-09-19: 520K views → 598 clicks in 28 days, and
    nothing on the site side could say what those 598 did next. The ledger keeps the
    bare URL; only the posted link carries the tags."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=threads&utm_medium=social&utm_campaign={fmt}"


def link_comment(episode_id: str, fmt: str = "episode_thread", hook: Optional[str] = None,
                 focus_ms: Optional[int] = None) -> str:
    """The episode permalink, posted as the FIRST comment (not in the post body) so
    the link doesn't suppress organic reach and lives where it helps SEO.

    ``hook`` says what is on the other side that the post did not give away, and
    ``focus_ms`` (``?t=``) lands the reader on the section the post was about instead
    of the top of a 13-screen page. Measured 2026-09-19: 1.5% of the people who saw
    「▶ 完整重點」 clicked it, and those who did had to scroll five screens to find the
    sentence they had just liked. Without a hook the old generic line stands."""
    url = episode_url(episode_id)
    if isinstance(focus_ms, int) and focus_ms >= 1000:
        url = f"{url}?t={focus_ms}"
    link = social_link(url, fmt)
    hook = " ".join((hook or "").split())
    return f"▶ {hook}\n{link}" if hook else f"▶ 完整重點：{link}"


def episode_link_comment(episode: Any, fmt: str) -> str:
    """``link_comment`` fed from the episode's written copy (``social_thread``)."""
    thread = _field(episode, "social_thread")
    thread = thread if isinstance(thread, dict) else {}
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    return link_comment(episode_id, fmt, hook=thread.get("link_hook"), focus_ms=thread.get("focus_ms"))


RASTER_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _is_raster(url: Optional[str]) -> bool:
    """True for image URLs Meta can actually ingest. Threads/IG and the FB photo
    endpoints reject SVG (and other vector formats) with a media-download error, so a
    non-raster image must be dropped or the whole post hard-fails. Currently the only
    episode image is an SVG summary card, so this degrades posts to text-only until a
    raster (PNG/JPEG) card render exists."""
    if not url:
        return False
    return url.lower().split("?")[0].endswith(RASTER_IMAGE_EXTS)


def _has_human_thread(episode: Any) -> bool:
    """True when an operator authored social copy (post or comments). Such episodes
    publish via the thread composer even without rendered cards, so the hand-written
    copy + link comment go out and the publish matches the admin preview."""
    t = _field(episode, "social_thread")
    if not isinstance(t, dict):
        return False
    if (t.get("post") or "").strip():
        return True
    return any(
        ((c.get("text") if isinstance(c, dict) else c) or "").strip()
        for c in (t.get("comments") or [])
    )


def compose_post(episode: Any, *, count_line: str = "", with_link: bool = True) -> dict:
    """Build a Threads post draft from an episode. Always <= THREADS_MAX_CHARS chars.

    ``count_line`` (e.g. "⬇️ 7 個重點整理") is reserved in the budget and placed at the
    end — used as the carousel caption to signal the thread below. No hashtags are
    added. ``with_link`` keeps the permalink in the body for the standalone single-post
    path (no comment channel); the thread path passes ``with_link=False`` and posts the
    link as the first comment instead. Returns ``{episode_id, text, image_url, url}``.
    """
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    title = (_field(episode, "episode_title") or "").strip()
    podcast_name = (_field(episode, "podcast_name") or "").strip()
    insights = [s.strip() for s in (_field(episode, "key_insights") or []) if s and s.strip()]
    image_url = _field(episode, "summary_image_public_url") or None
    if not _is_raster(image_url):
        image_url = None  # Meta can't ingest SVG — post text-only rather than hard-fail

    url = episode_url(episode_id)
    link_line = f"\n\n{link_comment(episode_id, 'episode_single')}" if with_link else ""
    count_seg = f"\n\n{count_line}" if count_line else ""

    header = "｜".join(p for p in (podcast_name, title) if p) or title or podcast_name

    # Fixed tail (count + optional link) is reserved first; insights fill what remains.
    budget = THREADS_MAX_CHARS - len(link_line) - len(count_seg)
    body = header[:budget] if header else ""

    for insight in insights[:MAX_INSIGHTS]:
        candidate = f"{body}\n\n• {insight}" if body else f"• {insight}"
        if len(candidate) <= budget:
            body = candidate
        else:
            break

    if not body:
        # No header and no insight fit — fall back to a trimmed header/title.
        body = (header or title or podcast_name)[: max(0, budget - 1)].rstrip()

    text = f"{body}{count_seg}{link_line}"
    if len(text) > THREADS_MAX_CHARS:  # defensive; should not trigger given the budget
        text = text[: THREADS_MAX_CHARS - len(link_line)].rstrip() + link_line

    return {"episode_id": episode_id, "text": text, "image_url": image_url, "url": url}


def _compose_reply(title: str, bullets: list[str]) -> str:
    """One threaded reply: 【title】 + bullets, clamped to THREADS_MAX_CHARS."""
    lines = [f"【{title}】"] if title else []
    for bullet in bullets:
        candidate = "\n".join(lines + [f"• {bullet}"])
        if len(candidate) <= THREADS_MAX_CHARS:
            lines.append(f"• {bullet}")
        else:
            break  # never split a bullet (it carries the timestamp) — drop trailing ones
    return "\n".join(lines).strip()


def _finalize_post_text(episode: Any, body: str, count_line: str = "") -> str:
    """Clamp the human-authored grand-summary post to THREADS_MAX_CHARS, appending only
    the count line. No hashtags and no permalink — the permalink goes in the first
    comment (see ``compose_thread``)."""
    count_seg = f"\n\n{count_line}" if count_line else ""
    budget = THREADS_MAX_CHARS - len(count_seg)
    body = (body or "").strip()[:max(0, budget)].rstrip()
    return f"{body}{count_seg}"


def pick_insight(insights: list[str]) -> str:
    """The one key_insight worth a post on its own: a number beats none, a line that
    fits a Threads screen (15–45 chars) beats a paragraph, earlier beats later."""
    def score(i: int, s: str) -> tuple:
        return (any(ch.isdigit() for ch in s), 15 <= len(s) <= 45, -i)
    clean = [(i, " ".join(str(s).split())) for i, s in enumerate(insights or []) if s and str(s).strip()]
    return max(clean, key=lambda t: score(*t))[1] if clean else ""


def is_zero_ticker(episode: Any) -> bool:
    """No stock in the episode — macro, gold, a 心法 episode. Decided from the
    ingest-time ``related_tickers`` field, NOT content_mentions: the mention sync runs
    on its own timer and a fresh episode can have zero rows for an hour."""
    return not (_field(episode, "related_tickers") or [])


def pick_macro_claim(claims: list[dict]) -> Optional[dict]:
    """The claim worth a card: one with a data series behind it, the host's own number
    quoted if any claim has one, then the most confident. Nothing → None (text only)."""
    from src.services.macro_data import SERIES
    usable = [c for c in claims or [] if isinstance(c, dict)
              and str(c.get("indicator_id") or "").upper() in SERIES and (c.get("claim") or "").strip()]
    if not usable:
        return None
    return max(usable, key=lambda c: (bool(c.get("level_quoted")), float(c.get("confidence") or 0)))


def _air_date_tw(episode: Any) -> Optional[str]:
    ms = _release_ms(episode)
    if not ms:
        return None
    return (datetime.fromtimestamp(ms / 1000, tz=timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def macro_card_url(episode: Any, claim: dict) -> Optional[str]:
    """The macro card with the episode day marked and the host's claim printed."""
    date = _air_date_tw(episode)
    if not date:
        return None
    label = f"{speaker_for(_field(episode, 'podcast_name'))} {int(date[5:7])}/{int(date[8:])}"
    q = urllib.parse.urlencode({"event": date, "label": label, "claim": (claim.get("claim") or "")[:160]})
    return f"{settings.public_api_url.rstrip('/')}/api/og/macro/{str(claim['indicator_id']).upper()}.png?{q}"


def is_low_ticker(episode: Any) -> bool:
    """One or two stocks — the host talked about a name, not a market. A five-card deck
    over that is padding; the shape that fits is the story of the call plus its chart."""
    return 1 <= len(_field(episode, "related_tickers") or []) <= 2


def _ticker_name(ticker: str) -> str:
    """zh-TW name from stock_translations; the bare ticker when the lookup fails — a
    story that says 3324 is worse than one that says 雙鴻, but far better than no post."""
    try:
        from src.database.postgres import get_session
        from src.services.paid_weekly import query_names
        for db in get_session():
            return query_names(db, {ticker}).get(ticker) or ticker
    except Exception as e:  # noqa: BLE001
        logger.info("ticker name lookup failed for %s: %s", ticker, e)
    return ticker


def compose_ticker_story(episode: Any) -> dict:
    """The frame of a same-day ticker story: which stock, the marked chart, the link.
    The text itself is written by the pipeline at publish time (``_story`` in
    ``today`` mode) — an LLM call the dry-run preview does not spend."""
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    ticker = str((_field(episode, "related_tickers") or [""])[0]).upper()
    date = _air_date_tw(episode) or datetime.utcnow().strftime("%Y-%m-%d")
    label = f"{speaker_for(_field(episode, 'podcast_name'))} {int(date[5:7])}/{int(date[8:])}"
    q = urllib.parse.urlencode({"days": 60, "event": date, "label": label})
    return {"episode_id": episode_id, "ticker": ticker, "mention_date": date, "podcaster": _field(episode, "podcast_name"),
            "image_url": f"{settings.public_api_url.rstrip('/')}/api/og/stock/{ticker}.png?{q}",
            "url": episode_url(episode_id)}


def compose_text_post(episode: Any) -> dict:
    """A zero-ticker episode as text only — no cards, no reply chain, link in the
    first reply. The text is the pipeline's own ``social_thread.post``: the 12–18 line
    argued post the writer already produced in the approved voice, which the carousel
    only ever used as a caption. The carousel exists to show what the stocks were; with
    none there is nothing for five cards to say, and the macro breakouts on this
    account were all short argued posts, not decks. An episode with no written post
    (pre-writer backlog) falls back to the speaker + one key_insight."""
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    thread = _field(episode, "social_thread") or {}
    text = (thread.get("post") or "").strip() if isinstance(thread, dict) else ""
    if not text:
        insight = pick_insight(_field(episode, "key_insights") or [])
        text = f"{speaker_for(_field(episode, 'podcast_name'))}這集\n{insight}"
    # With a macro claim behind the episode, the post carries the macro card — the
    # indicator's line with this episode marked on it — the way a stock episode carries
    # its chart. Without one it stays text only.
    claim = pick_macro_claim(_field(episode, "macro_claims") or [])
    image_url = macro_card_url(episode, claim) if claim else None
    return {"episode_id": episode_id, "text": text[:THREADS_MAX_CHARS], "url": episode_url(episode_id),
            "image_url": image_url}


def compose_thread(episode: Any) -> dict:
    """Build an AlphaMemo-style thread from an episode's social_cards.

    Returns ``{episode_id, main_text, image_urls, replies, url}`` — the carousel
    caption + ordered card images, and one reply per theme card. image_urls[i] and
    replies line up with the cards (cover is image 0, themes follow).

    Prefers the human-authored ``social_thread`` (post + per-theme comments) when
    present; otherwise falls back to the mechanical ``【title】 + bullets`` compose.
    """
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    cards = [c for c in (_field(episode, "social_cards") or []) if isinstance(c, dict)]
    # Drop non-raster (SVG) card images — Meta rejects them; better a text post than a hard fail.
    image_urls = [c["image_url"] for c in cards if _is_raster(c.get("image_url"))][:MAX_CARDS]
    theme_cards = [c for c in cards if c.get("kind") == "theme"]
    count_line = f"⬇️ {len(theme_cards)} 個重點整理" if theme_cards else ""

    thread = _field(episode, "social_thread")
    thread = thread if isinstance(thread, dict) else {}
    human_post = (thread.get("post") or "").strip()
    human_comments = [
        (c.get("text") if isinstance(c, dict) else str(c) or "").strip()
        for c in (thread.get("comments") or [])
    ]
    human_comments = [c for c in human_comments if c]

    if human_post:
        main_text = _finalize_post_text(episode, human_post, count_line)
    else:
        main_text = compose_post(episode, count_line=count_line, with_link=False)["text"]

    replies: list[dict] = []
    if human_comments:
        replies = [{"text": c[:THREADS_MAX_CHARS].rstrip()} for c in human_comments]
    else:
        for card in theme_cards:
            bullets = [b for b in (card.get("bullets") or []) if b and b.strip()]
            text = _compose_reply((card.get("title") or "").strip(), bullets)
            if text:
                replies.append({"text": text})

    # Permalink as the FIRST comment (link-in-first-comment) — keeps it out of the
    # post body so reach isn't suppressed and the link still gets indexed.
    replies.insert(0, {"text": episode_link_comment(episode, "episode_thread")})

    return {
        "episode_id": episode_id,
        "main_text": main_text,
        "image_urls": image_urls,
        "replies": replies,
        "url": episode_url(episode_id),
    }


async def publish_thread(service: ThreadsService, draft: dict) -> dict:
    """Publish a composed thread: carousel (or single image) + reply chain.

    Returns ``{root_media_id, reply_ids, image_count, reply_count}``. Per-reply errors
    stop the chain but still return the root (the carousel is already live), so the
    caller records it and never re-posts.
    """
    image_urls = draft["image_urls"]
    if len(image_urls) >= 2:
        root = await service.publish_carousel(image_urls, draft["main_text"])
    elif len(image_urls) == 1:
        root = await service.publish(draft["main_text"], image_url=image_urls[0])
    else:
        root = await service.publish(draft["main_text"])

    reply_ids: list[str] = []
    prev = root
    for reply in draft["replies"]:
        try:
            rid = await service.publish_reply(reply["text"], reply_to_id=prev)
        except ThreadsError as e:
            logger.warning("Reply failed for %s (%d posted): %s", draft["episode_id"], len(reply_ids), e)
            break
        reply_ids.append(rid)
        prev = rid

    return {
        "root_media_id": root,
        "reply_ids": reply_ids,
        "image_count": len(image_urls),
        "reply_count": len(reply_ids),
    }


def _release_ms(episode: Any) -> Optional[int]:
    return _field(episode, "released_at_ms") or _field(episode, "created_time")


PLATFORM = "threads"


def already_posted(episode_id: str) -> bool:
    return social_ledger.already_posted(PLATFORM, episode_id)


def _record(episode_id: str, media_id: str, url: str, reply_ids: Optional[list[str]] = None,
            fmt: str = "episode_single") -> None:
    social_ledger.record(PLATFORM, episode_id, media_id, url, reply_ids, fmt=fmt)


def list_posted(limit: int = 50, days: Optional[int] = None) -> list[dict]:
    """Recent ledger rows, newest first (``reply_ids`` keeps the published API shape)."""
    rows = social_ledger.list_posted(PLATFORM, limit, days=days)
    return [{**r, "reply_ids": r["child_ids"]} for r in rows]


async def publish_recent(
    limit: int = 10,
    dry_run: bool = True,
    max_age_days: Optional[int] = None,
    max_posts: Optional[int] = None,
) -> dict:
    """Post any recent, not-yet-posted episodes to Threads.

    Returns a summary with the drafts that were (or would be) posted and the
    reasons others were skipped. Safe to call repeatedly; idempotent per episode.
    """
    service = ThreadsService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured

    if max_age_days is None:
        max_age_days = settings.threads_max_age_days
    cutoff_ms: Optional[int] = None
    if max_age_days and max_age_days > 0:
        cutoff_ms = int((datetime.utcnow().timestamp() - max_age_days * 86400) * 1000)

    episodes = await podcast_service.get_recent_episodes(limit=limit, enrich_content=False)

    posted: list[dict] = []
    skipped: list[dict] = []

    for episode in episodes:
        episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
        if not episode_id:
            continue
        if already_posted(episode_id):
            skipped.append({"episode_id": episode_id, "reason": "already_posted"})
            continue
        if not social_enabled_for(_field(episode, "podcast_name")):
            skipped.append({"episode_id": episode_id, "reason": "social_disabled_for_show"})
            continue
        rel_ms = _release_ms(episode)
        if cutoff_ms is not None and (rel_ms is None or rel_ms < cutoff_ms):
            skipped.append({"episode_id": episode_id, "reason": "outside_recency_window"})
            continue
        has_cards = bool(_field(episode, "social_cards"))
        if not (has_cards or _field(episode, "key_insights") or _field(episode, "episode_title")):
            skipped.append({"episode_id": episode_id, "reason": "no_postable_content"})
            continue
        if max_posts is not None and len(posted) >= max_posts:
            # Still a candidate — it is not recorded, so the next slot picks it up.
            skipped.append({"episode_id": episode_id, "reason": "slot_full"})
            continue

        # No stocks in the episode → the written post as text, no cards.
        if is_zero_ticker(episode) and (_has_human_thread(episode) or _field(episode, "key_insights")):
            draft = compose_text_post(episode)
            if effective_dry_run:
                posted.append({**draft, "kind": "text", "dry_run": True})
                continue
            if not social_ledger.claim(PLATFORM, episode_id):
                skipped.append({"episode_id": episode_id, "reason": "already_posted"})
                continue
            try:
                fmt = "episode_macro_card" if draft.get("image_url") else "episode_text"
                media_id = await service.publish(draft["text"], image_url=draft.get("image_url"))
                reply_id = await service.publish_reply(episode_link_comment(episode, fmt), reply_to_id=media_id)
                _record(episode_id, media_id, draft["url"], [reply_id], fmt=fmt)
                posted.append({**draft, "kind": "text", "media_id": media_id, "dry_run": False})
                logger.info("Posted text post for %s (%s)", episode_id, media_id)
            except ThreadsError as e:
                social_ledger.release(PLATFORM, episode_id)
                skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})
            continue

        # One or two stocks → the story of the call on its marked chart. The story comes
        # from the pipeline at publish time; if it does not, the episode takes the
        # carousel path below rather than being skipped.
        if is_low_ticker(episode):
            frame = compose_ticker_story(episode)
            if effective_dry_run:
                posted.append({**frame, "kind": "ticker_story", "text": "（發佈時由 pipeline 產生）", "dry_run": True})
                continue
            from src.services import social_formats
            frame["name"] = await asyncio.to_thread(_ticker_name, frame["ticker"])
            story = await social_formats._story(frame, mode="today")
            if story:
                if not social_ledger.claim(PLATFORM, episode_id):
                    skipped.append({"episode_id": episode_id, "reason": "already_posted"})
                    continue
                try:
                    media_id = await service.publish(story, image_url=frame["image_url"])
                    hook = f'{speaker_for(frame["podcaster"])}這集講{frame["name"]}的整段'
                    reply_id = await service.publish_reply(
                        link_comment(episode_id, "episode_ticker_story", hook=hook), reply_to_id=media_id)
                    _record(episode_id, media_id, frame["url"], [reply_id], fmt="episode_ticker_story")
                    posted.append({**frame, "kind": "ticker_story", "text": story, "media_id": media_id, "dry_run": False})
                    logger.info("Posted ticker story for %s (%s, %s)", episode_id, frame["ticker"], media_id)
                except ThreadsError as e:
                    social_ledger.release(PLATFORM, episode_id)
                    skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})
                continue
            logger.info("no ticker story for %s (%s) — carousel instead", episode_id, frame["ticker"])

        # Use the full thread (carousel + reply chain) when the episode has rendered
        # cards OR hand-authored social copy; otherwise fall back to a single text/image
        # post (legacy episodes with neither).
        if has_cards or _has_human_thread(episode):
            thread = compose_thread(episode)
            if effective_dry_run:
                posted.append({
                    "episode_id": episode_id, "url": thread["url"],
                    "main_text": thread["main_text"], "image_count": len(thread["image_urls"]),
                    "reply_count": len(thread["replies"]), "dry_run": True,
                })
                continue
            if not social_ledger.claim(PLATFORM, episode_id):
                skipped.append({"episode_id": episode_id, "reason": "already_posted"})
                continue
            try:
                res = await publish_thread(service, thread)
                _record(episode_id, res["root_media_id"], thread["url"], res["reply_ids"], fmt="episode_thread")
                posted.append({"episode_id": episode_id, "url": thread["url"], "dry_run": False, **res})
                logger.info("Posted thread for %s (root=%s, %d replies)",
                            episode_id, res["root_media_id"], res["reply_count"])
            except ThreadsError as e:
                social_ledger.release(PLATFORM, episode_id)
                skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})
            continue

        draft = compose_post(episode)
        if effective_dry_run:
            posted.append({**draft, "dry_run": True})
            continue
        if not social_ledger.claim(PLATFORM, episode_id):
            skipped.append({"episode_id": episode_id, "reason": "already_posted"})
            continue
        try:
            media_id = await service.publish(draft["text"], image_url=draft["image_url"])
            _record(episode_id, media_id, draft["url"])
            posted.append({**draft, "media_id": media_id, "dry_run": False})
            logger.info("Posted episode %s to Threads (%s)", episode_id, media_id)
        except ThreadsError as e:
            social_ledger.release(PLATFORM, episode_id)
            skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})

    return {
        "platform": "threads",
        "configured": configured,
        "dry_run": effective_dry_run,
        "candidates": len(episodes),
        "posted_count": len([p for p in posted if not p.get("dry_run")]),
        "posted": posted,
        "skipped": skipped,
    }


async def publish_episode(episode: Any, dry_run: bool = True) -> dict:
    """Publish one already-fetched episode to Threads (the admin "發佈" button).

    Unlike :func:`publish_recent` this targets a single, explicitly chosen episode
    and ignores the recency window (the operator picked it). Still idempotent
    (skips if already posted) and forced to dry-run when unconfigured. Returns a
    flat result: ``{platform, configured, dry_run, episode_id, posted, ...}`` with
    ``posted`` True only on a real publish, else a ``reason`` for the skip/preview.
    """
    service = ThreadsService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    base = {"platform": "threads", "configured": configured, "dry_run": effective_dry_run, "episode_id": episode_id}

    if not episode_id:
        return {**base, "posted": False, "reason": "no_episode_id"}
    if already_posted(episode_id):
        return {**base, "posted": False, "reason": "already_posted", "url": episode_url(episode_id)}
    if not social_enabled_for(_field(episode, "podcast_name")):
        return {**base, "posted": False, "reason": "social_disabled_for_show"}
    has_cards = bool(_field(episode, "social_cards"))
    if not (has_cards or _field(episode, "key_insights") or _field(episode, "episode_title")):
        return {**base, "posted": False, "reason": "no_postable_content"}

    if has_cards or _has_human_thread(episode):
        thread = compose_thread(episode)
        if effective_dry_run:
            return {**base, "posted": False, "reason": "dry_run", "url": thread["url"],
                    "main_text": thread["main_text"], "image_count": len(thread["image_urls"]),
                    "reply_count": len(thread["replies"])}
        if not social_ledger.claim(PLATFORM, episode_id):
            return {**base, "posted": False, "reason": "already_posted", "url": thread["url"]}
        try:
            res = await publish_thread(service, thread)
        except ThreadsError as e:
            social_ledger.release(PLATFORM, episode_id)
            return {**base, "posted": False, "reason": f"publish_failed: {e}", "url": thread["url"]}
        _record(episode_id, res["root_media_id"], thread["url"], res["reply_ids"], fmt="episode_thread")
        logger.info("Posted thread for %s (root=%s, %d replies)", episode_id, res["root_media_id"], res["reply_count"])
        return {**base, "posted": True, "url": thread["url"], **res}

    draft = compose_post(episode)
    if effective_dry_run:
        return {**base, "posted": False, "reason": "dry_run", **draft}
    if not social_ledger.claim(PLATFORM, episode_id):
        return {**base, "posted": False, "reason": "already_posted", "url": draft["url"]}
    try:
        media_id = await service.publish(draft["text"], image_url=draft["image_url"])
    except ThreadsError as e:
        social_ledger.release(PLATFORM, episode_id)
        return {**base, "posted": False, "reason": f"publish_failed: {e}", "url": draft["url"]}
    _record(episode_id, media_id, draft["url"])
    logger.info("Posted episode %s to Threads (%s)", episode_id, media_id)
    return {**base, "posted": True, "media_id": media_id, **draft}
