"""Publish an episode summary to 方格子 (vocus.cc).

vocus has no developer API. This drives the same undocumented REST endpoints its own
Next.js editor uses, mapped from a live editor session:

    POST  /api/articles                  {title, lexicalObj, userId, status}
    PATCH /api/articles/{id}/draft       {title, lexicalObj, articleId, draftType, ...}
    PATCH /api/articles/{id}             the publish-settings payload (below)
    PATCH /api/articles/{id}/status/{n}  status is a PATH segment, not a body field

Two things about this deserve to stay uncomfortable:

1. **It is undocumented.** vocus can change any of it without notice, and the failure is
   silent — a changed field name yields a 200 with a half-empty article. Hence
   :func:`_verify_published`: every publish reads the article back and confirms the
   platform actually agrees it is public. Never report success on the write alone.

2. **The credential is a 7-day token** (``VOCUS_ID_TOKEN``, a vocus-signed HS256 JWT,
   obtained by signing in and reading ``localStorage.id_token``). There is no refresh
   endpoint in their bundle, so it must be replaced by hand roughly weekly. That makes
   expiry the single most likely failure, so it is checked *before* posting and reported
   as ``credential_expired`` — this publisher must never degrade quietly to dry-run the
   way an unconfigured Threads client does, because a silent skip here means weeks of
   articles that were never published.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from src.config import settings
from src.services.syndication_markdown import to_syndication_markdown
from src.services.vocus_lexical import markdown_to_lexical

logger = logging.getLogger(__name__)

VOCUS_API_BASE = "https://api.vocus.cc"

# Observed live: PATCH .../status/1 is what the editor sends with publishMethod=draft.
# 投資理財 — vocus's own category id, from the publish wizard's dropdown. One publication,
# one category; make it a setting if that ever stops being true.
VOCUS_CATEGORY_ID = "5a978e00fd897800016874cc"
VOCUS_CATEGORY_TITLE = "投資理財"

STATUS_DRAFT = 1
# Confirmed live 2026-08-11: after a full publish the article appears in the status=2
# bucket. _verify_published() still checks every time — an undocumented API can accept
# every write and change nothing, and that must never read as success.
STATUS_PUBLIC = 2

# Warn while there is still time to act, rather than at the moment posting breaks.
TOKEN_WARN_SECONDS = 2 * 24 * 3600

_TOKEN_CACHE_SECONDS = 60
_token_cache: Optional[tuple[Optional[str], float]] = None


class VocusError(RuntimeError):
    """A vocus API call failed or the credential is unusable."""


def _fetch_token_from_gsm() -> Optional[str]:
    """Read VOCUS_ID_TOKEN straight from Secret Manager, bypassing the startup cache.

    Every other secret here is stable for months, so reading it once at boot is fine.
    This one is replaced roughly weekly, and requiring a backend restart after each
    rotation would make the whole thing not worth operating. Failures are swallowed:
    the caller falls back to the boot-time value.
    """
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        return None
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/VOCUS_ID_TOKEN/versions/latest"
        return client.access_secret_version(request={"name": name}).payload.data.decode("utf-8").strip()
    except Exception as e:  # noqa: BLE001 — never let a GSM blip break publishing outright
        logger.debug("vocus: live GSM token read failed (%s); using boot-time value", e)
        return None


def current_token() -> Optional[str]:
    """The token to publish with — freshest first, cached for a minute.

    A minute is long enough that a publish run does not hammer GSM, and short enough
    that a token pasted in the admin UI takes effect while the operator is still there.
    """
    global _token_cache
    now = time.time()
    if _token_cache and now - _token_cache[1] < _TOKEN_CACHE_SECONDS:
        return _token_cache[0]
    token = _fetch_token_from_gsm() or settings.vocus_id_token
    _token_cache = (token, now)
    return token


def _jwt_exp(token: str) -> Optional[int]:
    """Read ``exp`` out of the token without verifying it.

    We are not authenticating anyone — we only need to know whether the platform will
    still accept this credential, so the signature is irrelevant here.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp"))
    except (IndexError, ValueError, TypeError, binascii.Error, json.JSONDecodeError):
        return None


def token_status(token: Optional[str] = None) -> dict:
    """``{configured, expired, expires_at, seconds_left, expiring_soon}`` — safe to
    surface in the admin UI: it reports *about* the token, never its value."""
    tok = token if token is not None else current_token()
    if not tok:
        return {"configured": False, "expired": True, "expires_at": None,
                "seconds_left": None, "expiring_soon": False}
    exp = _jwt_exp(tok)
    if exp is None:
        # Unparseable: treat as unusable rather than assume it works.
        return {"configured": True, "expired": True, "expires_at": None,
                "seconds_left": None, "expiring_soon": True}
    left = exp - int(time.time())
    return {
        "configured": True,
        "expired": left <= 0,
        "expires_at": exp,
        "seconds_left": left,
        "expiring_soon": 0 < left <= TOKEN_WARN_SECONDS,
    }


def _lexical_field(lexical: dict) -> str:
    """vocus wants the editor state as a JSON *string*, on both create and draft-save.

    Worth stating because the capture said otherwise: the interceptor used to map the
    payload re-parsed nested strings, so a stringified value looked like a nested object.
    The API is unambiguous — ``model.Draft.LexicalObj: ReadString: expects " or n, but
    found {`` is what an object gets you.
    """
    return json.dumps(lexical, ensure_ascii=False)


class VocusClient:
    """Thin async client over the endpoints the vocus editor itself calls."""

    def __init__(self, token: Optional[str] = None, user_id: Optional[str] = None,
                 salon_id: Optional[str] = None, base: str = VOCUS_API_BASE):
        self._token = token if token is not None else current_token()
        self._user_id = user_id if user_id is not None else settings.vocus_user_id
        self._salon_id = salon_id if salon_id is not None else settings.vocus_salon_id
        self._base = base.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._user_id)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _request(self, client: httpx.AsyncClient, method: str, path: str,
                       payload: Optional[dict] = None) -> Any:
        resp = await client.request(method, f"{self._base}{path}", headers=self._headers, json=payload)
        if resp.status_code in (401, 403):
            # Overwhelmingly the 7-day token, so say so instead of a bare HTTP code.
            raise VocusError("credential_expired")
        if resp.status_code >= 400:
            # Carry a slice of the body: against an undocumented API "http_400" alone
            # tells you nothing, and the response is usually the only hint about which
            # field it disliked. Never contains the credential — only our own payload.
            detail = (resp.text or "")[:300].replace("\n", " ")
            logger.warning("vocus %s %s -> %s %s", method, path, resp.status_code, detail)
            raise VocusError(f"http_{resp.status_code}: {detail}" if detail else f"http_{resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            return None

    async def create_article(self, client: httpx.AsyncClient, title: str, lexical: dict) -> str:
        data = await self._request(client, "POST", "/api/articles", {
            "title": title, "lexicalObj": _lexical_field(lexical),
            "userId": self._user_id, "status": STATUS_DRAFT,
        })
        article_id = (data or {}).get("_id") or (data or {}).get("id") or (data or {}).get("articleId")
        if not article_id:
            raise VocusError("create_returned_no_article_id")
        return str(article_id)

    async def save_body(self, client: httpx.AsyncClient, article_id: str, title: str, lexical: dict) -> None:
        await self._request(client, "PATCH", f"/api/articles/{article_id}/draft", {
            "title": title, "lexicalObj": _lexical_field(lexical), "articleId": article_id,
            "draftType": "draft", "commandLogs": "[]",  # also a JSON string, not an array
        })

    async def save_settings(self, client: httpx.AsyncClient, article_id: str, *, title: str,
                            abstract: str, canonical_url: str, tags: list[str],
                            thumbnail_url: str = "") -> None:
        await self._request(client, "PATCH", f"/api/articles/{article_id}", {
            "title": title,
            "abstract": abstract[:200],
            # model.TagInfo, whose display field is `title`. Two traps in one field: a
            # list of strings is rejected outright ("cannot unmarshal string into ...
            # Article.ArticleInfo.tags"), but an object with the WRONG keys is accepted
            # with a 200 and stored as {"title": "", "totalScore": 0} — five blank chips
            # in the publish wizard and no error anywhere. Read tags back, do not trust
            # the status code.
            "tags": [{"title": t} for t in tags],
            # 分類 is required by the publish wizard and blocks it when unset. It is a
            # model.BertClassify object — a bare id string is rejected — so send the
            # whole {_id, title, score} shape the API stores.
            "newCategory": {"_id": VOCUS_CATEGORY_ID, "title": VOCUS_CATEGORY_TITLE, "score": 0},
            "canonicalURL": canonical_url,
            # The whole article also lives on tinboker.com. Pointing canonical home is
            # what keeps three full-text copies from competing with each other.
            "openCanonical": True,
            "setInvestment": True,   # investment-content disclosure; this is a finance publication
            "showCatalog": True,
            "setIsPay": False,
            "salonId": self._salon_id,
            "thumbnailUrl": thumbnail_url,
            # "custom" when we supply one; "article" makes vocus hunt for an image in the
            # body, and the body has none — that is what leaves the placeholder cover.
            "coverSource": "custom" if thumbnail_url else "article",
            "ogImageType": "thumbnail",
        })

    async def set_status(self, client: httpx.AsyncClient, article_id: str, status: int) -> None:
        await self._request(client, "PATCH", f"/api/articles/{article_id}/status/{status}", None)

    async def list_article_ids(self, client: httpx.AsyncClient, status: int, limit: int = 20) -> list[str]:
        """Ids of this user's articles in one status bucket.

        There is no single-article read: GET /api/articles/{id} 404s in every shape we
        tried, so "is it public yet?" has to be answered by asking which bucket it is in.
        """
        data = await self._request(
            client, "GET",
            f"/api/articles?num={limit}&order=desc&page=1&sort=updatedAt"
            f"&status={status}&userId={self._user_id}",
        )
        items = data if isinstance(data, list) else (data or {}).get("articles") or (data or {}).get("data") or []
        return [str(a.get("_id") or a.get("id")) for a in items if isinstance(a, dict)]

    async def delete_article(self, client: httpx.AsyncClient, article_id: str) -> None:
        await self._request(client, "DELETE", f"/api/articles/{article_id}", None)


def article_url(article_id: str) -> str:
    return f"https://vocus.cc/article/{article_id}"


async def _verify_published(client: VocusClient, http: httpx.AsyncClient, article_id: str) -> bool:
    """Read the article back and confirm vocus agrees it is public.

    The status integer is inferred, and an undocumented API can accept a write and do
    nothing. Without this check a broken publisher reports success indefinitely.
    """
    try:
        return article_id in await client.list_article_ids(http, STATUS_PUBLIC)
    except VocusError:
        return False


async def publish_summary(
    episode_id: str,
    title: str,
    summary_markdown: str,
    podcast_name: str = "",
    *,
    abstract: str = "",
    tags: Optional[list[str]] = None,
    thumbnail_url: str = "",
    dry_run: bool = True,
) -> dict:
    """Publish one episode summary to vocus.

    Returns a flat result in the same shape the Threads/Facebook publishers use:
    ``{platform, configured, dry_run, episode_id, posted, ...}``. On any failure
    ``reason`` says what went wrong — notably ``credential_expired``, which means the
    7-day token needs replacing and NOTHING was published.
    """
    tok = token_status()
    base = {"platform": "vocus", "configured": tok["configured"], "dry_run": dry_run,
            "episode_id": episode_id, "token": tok}

    body_markdown = to_syndication_markdown(summary_markdown, episode_id)
    if not body_markdown:
        return {**base, "posted": False, "reason": "no_summary_content"}

    if not tok["configured"]:
        return {**base, "posted": False, "reason": "not_configured"}
    # Deliberately NOT degraded to a dry-run: an expired token must be loud.
    if tok["expired"]:
        return {**base, "posted": False, "reason": "credential_expired"}

    lexical = markdown_to_lexical(body_markdown)
    canonical = f"{settings.site_url.rstrip('/')}/episode/{episode_id}"

    if dry_run:
        return {**base, "posted": False, "reason": "dry_run",
                "preview": {"title": title, "canonical_url": canonical,
                            "block_count": len(lexical["root"]["children"])}}

    client = VocusClient()
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            article_id = await client.create_article(http, title, lexical)
            await client.save_body(http, article_id, title, lexical)
            await client.save_settings(http, article_id, title=title,
                                       # No title fallback: repeating the headline wastes
                                       # the one line a reader skims before clicking.
                                       abstract=abstract,
                                       canonical_url=canonical, tags=tags or [],
                                       thumbnail_url=thumbnail_url)
            await client.set_status(http, article_id, STATUS_PUBLIC)
            verified = await _verify_published(client, http, article_id)
    except VocusError as e:
        reason = str(e)
        logger.warning("vocus publish failed for %s: %s", episode_id, reason)
        return {**base, "posted": False, "reason": reason}
    except httpx.HTTPError as e:
        logger.warning("vocus publish transport error for %s: %s", episode_id, e)
        return {**base, "posted": False, "reason": "transport_error"}

    if not verified:
        # The writes succeeded but the article is not public. Surfaced as a distinct
        # reason so it is never mistaken for a network blip — the likeliest cause is
        # STATUS_PUBLIC being the wrong integer.
        logger.error("vocus published %s but read-back says it is not public", article_id)
        return {**base, "posted": False, "reason": "publish_unverified",
                "article_id": article_id, "url": article_url(article_id)}

    return {**base, "posted": True, "article_id": article_id, "url": article_url(article_id)}
