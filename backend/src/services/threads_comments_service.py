"""Triage the replies people leave on our Threads posts, so a human answers the good ones.

Shape of the problem, from the first 63 posts (2026-06-15 → 08-26, 33 external
replies): ~14 were real arguments or direct questions, ~9 were one-line reactions,
6 were aimed at another commenter rather than at us, 4 were an @meta.ai bot exchange,
1 was self-promo — and exactly **1** was hostile. So the filtering that matters is not
troll defence; it is not talking to bots, not barging into someone else's sub-thread,
and not letting a model improvise financial claims in public.

Hence the split:
  * objective exclusions are rules (ours / bots / empty / not addressed to us) — no model call;
  * the judgement call is one model call per new comment;
  * nothing is ever posted unattended — the model classifies and drafts, a human sends.

The model has no send button on purpose. On the first run against real comments it
called four of them plain "praise", one being 「一堆傻子根本沒弄清楚…」 — that is the
category that used to be allowed out on its own. A wrong tone or a wrong number from a
finance account is worse than a slow reply, and none of this is urgent.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

import httpx

from src.config import settings
from src.database.models import ThreadsComment
from src.database.postgres import session_scope
from src.services.threads_service import ThreadsService

logger = logging.getLogger(__name__)

# Accounts that are not people. Replying to these starts a bot-to-bot thread in
# public — @meta.ai already answered two of our commenters unprompted.
BOT_USERNAMES = {"meta.ai", "aistudio", "threads"}

# A reply that touches someone's position is advice, not chit-chat: never unattended,
# whatever the classifier thinks. Belt to the model's braces.
POSITION_RE = re.compile(
    r"(\d{4}\s*(?:TW)?|\$[A-Za-z]{1,5}\b)"           # 2330 / $NVDA
    r"|(買|賣|進場|出場|加碼|減碼|停損|停利|目標價|該不該|可以入|能買|存股|套牢)"
)

CATEGORIES = ("praise", "question", "substantive", "hostile", "noise", "promo", "bot")

TRIAGE_SYSTEM = """你是台灣財經 podcast 摘要帳號 @tinboker 的社群編輯。判斷一則留言該不該回、怎麼回。

分類（category 只能是其中一個）：
- praise：**完全沒有內容**的稱讚、打招呼、按讚式回應（例：「推」「感謝整理」「皓哥出品必屬精品」）。
  留言只要對主題表達了看法、補充、比喻或評論，就算語氣是稱讚也不是 praise，是 substantive
- question：直接問我們問題，想要一個答案
- substantive：提出論點、反駁、補充資料，值得對話
- hostile：人身攻擊、單純謾罵
- noise：一句話情緒或梗，沒有可回應的內容（例：「我就空」「就賭爛」）。
  指出我們講錯的地方（人名、數字、錯字）不是 noise，是 substantive —— 那是要修正的
- promo：主要目的是推自己的連結或帳號
- bot：留言者是機器人

同時判斷：
- has_factual_claim：留言裡有可被查證的具體事實或數字（研究報告、毛利率、產能時程…）
- asks_question：留言在等一個回答

draft：只有 category 是 question / substantive 才寫，其他一律留空字串。
這個帳號是公開的自動整理帳號，不假裝是人。回覆有立場但沒有第一人稱：
- **不准出現「我」**（我覺得、我聽完、我也沒想通… 全部不行）。立場照樣要有，
  只是不掛在一個人身上：「這個講法站不住」而不是「我覺得這個講法站不住」
- 一到三句，講一件事就好
- 口語、可以用半句接續，不要完整的書面句
- 不要開場招呼、不要感謝收看、不要收尾金句、不要 CTA、不要 emoji
- 對方提出論點就接著論點講，不要複述他說過的話
- 不要只是附和。開頭不要用「確實」「的確」「沒錯」「這確實是」
- 如果沒有東西可以補充（節目裡的一個細節、一個數字、一個還沒有答案的點），
  draft 就留空字串 —— 空草稿比一句廢話好，人會自己接手
- 不確定的地方就說不確定（「這題還沒有答案」），不要硬給結論
- 絕對不要給買賣建議、目標價或個股操作意見
- 繁體中文，中英文之間留半形空格

只輸出 JSON：{"category":"...","has_factual_claim":bool,"asks_question":bool,"reason":"一句話說明","draft":"..."}"""


def _is_bot(username: Optional[str]) -> bool:
    return (username or "").lower().lstrip("@") in BOT_USERNAMES


def _addressed_to_us(entry: dict, our_ids: set[str]) -> bool:
    """True when the reply hangs off our post or one of our own chain comments.

    Threads' /conversation returns the whole tree, so most entries in a busy thread
    are people talking to each other. Answering those reads as barging in.
    """
    return (entry.get("replied_to") or {}).get("id") in our_ids


def decide(category: str, has_factual_claim: bool, asks_question: bool, text: str) -> str:
    """Route a triaged comment. Deterministic on purpose — the model classifies, this decides."""
    if category in ("hostile", "noise", "promo", "bot"):
        return "ignore"
    if (
        category == "praise"
        and not has_factual_claim
        and not asks_question
        and not POSITION_RE.search(text or "")
    ):
        # 「推」「感謝整理」— there is nothing to answer, so it does not belong in a queue
        # a human works through. Praise carrying a claim, a question or a position is a
        # conversation, and falls through to review.
        return "ignore"
    return "needs_review"


async def _triage(client: httpx.AsyncClient, post_text: str, comment_text: str) -> dict:
    """One model call: classify the comment and draft a reply. Never raises."""
    if not settings.openrouter_api_key:
        return {"category": None, "reason": "no_openrouter_key", "draft": ""}
    last_error = "no attempt"
    for attempt in range(2):
        try:
            out = await _triage_once(client, post_text, comment_text)
        except Exception as e:  # malformed JSON, timeout, 5xx — one retry, then give up
            last_error = str(e)
            continue
        category = out.get("category")
        if category not in CATEGORIES:
            last_error = f"unknown_category: {category}"
            continue
        return {
            "category": category,
            "has_factual_claim": bool(out.get("has_factual_claim")),
            "asks_question": bool(out.get("asks_question")),
            "reason": (out.get("reason") or "")[:500],
            "draft": (out.get("draft") or "").strip(),
        }
    logger.warning("comment triage failed: %s", last_error)
    return {"category": None, "reason": f"triage_failed: {last_error}", "draft": ""}


async def _triage_once(client: httpx.AsyncClient, post_text: str, comment_text: str) -> dict:
    resp = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://tinboker.com",
            "X-Title": "TinBoker comment triage",
        },
        json={
            "model": settings.social_comment_model,
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM},
                {"role": "user", "content":
                    f"我們的貼文：\n{post_text[:1200]}\n\n這則留言：\n{comment_text[:1200]}"},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    # json_object mode still leaks fences and the odd prose preamble — take the object.
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(match.group(0) if match else raw, strict=False)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
    except ValueError:
        return None


async def sync_and_triage(scan_posts: Optional[int] = None) -> dict:
    """Pull new comments on recent posts and triage them. Posts nothing.

    Returns ``{scanned, new, needs_review, ignored}``.
    """
    if not ThreadsService().is_configured:
        return {"configured": False, "scanned": 0, "new": 0,
                "needs_review": 0, "ignored": 0}

    limit = scan_posts or settings.social_comment_scan_posts
    base = settings.threads_api_base.rstrip("/")
    token = settings.threads_access_token
    counts = {"configured": True, "scanned": 0, "new": 0,
              "needs_review": 0, "ignored": 0}

    async with httpx.AsyncClient(timeout=30.0) as client:
        posts = (await client.get(
            f"{base}/me/threads",
            params={"fields": "id,text", "limit": limit, "access_token": token},
        )).json().get("data", [])
        counts["scanned"] = len(posts)

        with session_scope() as db:
            known = {c.id for c in db.query(ThreadsComment.id).all()}

        async def conversation(post: dict) -> list[dict]:
            r = await client.get(
                f"{base}/{post['id']}/conversation",
                params={"fields": "id,text,username,timestamp,replied_to,permalink,"
                                  "is_reply_owned_by_me",
                        "access_token": token},
            )
            return r.json().get("data", [])

        # Fetch and triage concurrently. Serially this is ~15s of HTTP plus one model
        # call per new comment, which on a first run (40 comments) blows past both the
        # admin page's 30s client timeout and Cloudflare's 100s edge cap — the button
        # could never finish, so the tab stayed empty.
        convs = await asyncio.gather(*(conversation(p) for p in posts))

        # Comments synced before we stored the API's permalink have none, so the tab shows
        # them with no way through to the thread. The walk already has the URLs in hand —
        # fill them in rather than making someone re-sync from scratch.
        if known:
            urls = {e["id"]: e["permalink"] for cv in convs for e in cv if e.get("permalink")}
            with session_scope() as db:
                for row in db.query(ThreadsComment).filter(
                    ThreadsComment.permalink.is_(None), ThreadsComment.id.in_(urls)
                ):
                    row.permalink = urls[row.id]

        seen = set(known)
        candidates: list[tuple[dict, dict]] = []
        for post, conv in zip(posts, convs):
            our_ids = {post["id"]} | {c["id"] for c in conv if c.get("is_reply_owned_by_me")}
            for entry in conv:
                # /me/threads returns our own chain replies too, so the same comment can
                # surface under two posts — dedupe here or the insert hits the PK.
                if entry.get("is_reply_owned_by_me") or entry["id"] in seen:
                    continue
                if _is_bot(entry.get("username")) or not _addressed_to_us(entry, our_ids):
                    continue
                if not (entry.get("text") or "").strip():
                    continue  # a sticker or image reply — nothing to read, nothing to answer
                seen.add(entry["id"])
                candidates.append((post, entry))

        gate = asyncio.Semaphore(5)

        async def triage(post: dict, entry: dict) -> dict:
            async with gate:
                return await _triage(client, post.get("text") or "", entry.get("text") or "")

        triaged = await asyncio.gather(*(triage(p, e) for p, e in candidates))

        for (post, entry), t in zip(candidates, triaged):
            verdict = (
                decide(t["category"], t.get("has_factual_claim", False),
                       t.get("asks_question", False), entry.get("text") or "")
                if t["category"] else "needs_review"
            )
            draft = t.get("draft") or ""
            row = ThreadsComment(
                id=entry["id"], root_post_id=post["id"],
                replied_to_id=(entry.get("replied_to") or {}).get("id"),
                username=entry.get("username"), text=entry.get("text") or "",
                posted_at=_parse_ts(entry.get("timestamp")),
                permalink=entry.get("permalink"),
                category=t["category"], verdict=verdict,
                reason=t.get("reason"), draft=draft,
                status="ignored" if verdict == "ignore" else "pending",
            )
            with session_scope() as db:
                db.add(row)
            counts["new"] += 1

            counts["ignored" if verdict == "ignore" else "needs_review"] += 1

    return counts


async def send_reply(comment_id: str, text: str,
                     service: Optional[ThreadsService] = None) -> dict:
    """Post ``text`` as a reply to ``comment_id`` and mark the row replied.

    Only the admin button reaches this — the status check guards against a double tap.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("reply text is empty")

    with session_scope() as db:
        row = db.get(ThreadsComment, comment_id)
        if row is None:
            raise ValueError(f"unknown comment {comment_id}")
        if row.status == "replied":
            return {"replied": False, "reason": "already_replied",
                    "reply_media_id": row.reply_media_id}

    svc = service or ThreadsService()
    media_id = await svc.publish_reply(text, comment_id)

    with session_scope() as db:
        row = db.get(ThreadsComment, comment_id)
        row.status = "replied"
        row.draft = text
        row.reply_media_id = media_id
        row.replied_at = datetime.utcnow()
    logger.info("replied to comment %s", comment_id)
    return {"replied": True, "reply_media_id": media_id}


def set_status(comment_id: str, status: str) -> dict:
    """Mark a comment skipped/pending without posting anything."""
    if status not in ("pending", "skipped", "ignored"):
        raise ValueError(f"bad status {status}")
    with session_scope() as db:
        row = db.get(ThreadsComment, comment_id)
        if row is None:
            raise ValueError(f"unknown comment {comment_id}")
        if row.status == "replied":
            return {"ok": False, "reason": "already_replied"}
        row.status = status
    return {"ok": True, "status": status}


def list_comments(status: str = "pending", limit: int = 50) -> list[dict]:
    with session_scope() as db:
        q = db.query(ThreadsComment)
        if status != "all":
            q = q.filter(ThreadsComment.status == status)
        rows = q.order_by(ThreadsComment.posted_at.desc().nulls_last()).limit(limit).all()
        return [
            {
                "id": r.id, "root_post_id": r.root_post_id, "username": r.username,
                "text": r.text, "posted_at": r.posted_at.isoformat() if r.posted_at else None,
                "category": r.category, "verdict": r.verdict, "reason": r.reason,
                "draft": r.draft, "status": r.status, "auto": r.auto,
                "reply_media_id": r.reply_media_id,
                "permalink": r.permalink,
            }
            for r in rows
        ]
