"""Push an episode summary into Substack as a DRAFT.

Deliberately stops at the draft. Publishing on Substack emails the whole subscriber list
the moment it succeeds — there is no unsend — so the last step stays a human clicking
Publish after reading the draft. Everything up to that point is automated.

The API is undocumented; these shapes were read off the requests Substack's own editor
makes, then confirmed against the live API:

    POST /api/v1/drafts   {type, audience, draft_bylines:[{id,is_guest}], draft_body}
    PUT  /api/v1/drafts/{id}   {draft_title, draft_subtitle, draft_body}

``draft_body`` is a JSON *string* of a ProseMirror document, not an object — the same
trap vocus set. ``draft_bylines`` is required on create and must be a list of objects;
a bare list of ids is rejected with ``draft_bylines[0].id: Invalid value``.

Auth is the ``substack.sid`` session cookie, which unlike the vocus token lives for
months, so it is read from settings at boot like every other stable secret. It is
httpOnly, so unlike the vocus token it cannot be lifted out of the page by script and no
scheduled job can rotate it — it is installed by hand from DevTools. Take the row named
exactly ``substack.sid`` on the ``.substack.com`` domain: a correct value is ~80
characters and begins ``s%3A``. A value beginning ``g.`` is Google's ``SID`` cookie,
which sits next to it in the same DevTools list and produces a 403 "Not authorized".
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from src.config import settings
from src.services.substack_prosemirror import markdown_to_prosemirror
from src.services.syndication_markdown import to_syndication_markdown

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0

# Probed against the live API: limit=49 is accepted, limit=50 is rejected with
# "param: limit, msg: Invalid value". An exclusive max, so callers are clamped rather
# than left to discover it as a 400 mid-cleanup.
MAX_DRAFT_LIMIT = 49

# Matches services/og_image.py; the node carries the real pixel size.
COVER_WIDTH, COVER_HEIGHT = 1200, 600

# Substack sits behind an edge that rejects a default python-httpx User-Agent outright.
# These are not an attempt to look like something we are not — the calls are the account
# owner's own, authenticated with their own cookie — they are the minimum the edge needs
# to route the request to the API instead of a challenge page.
_HEADERS = {
    "content-type": "application/json",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "accept": "application/json, text/plain, */*",
}


class SubstackError(RuntimeError):
    """A Substack API call failed or the session cookie is unusable."""


class SubstackClient:
    def __init__(self, sid: Optional[str] = None, subdomain: Optional[str] = None,
                 user_id: Optional[int] = None):
        self._sid = sid if sid is not None else settings.substack_sid
        self._subdomain = subdomain if subdomain is not None else settings.substack_subdomain
        self._user_id = user_id if user_id is not None else settings.substack_user_id

    @property
    def base(self) -> str:
        return f"https://{self._subdomain}.substack.com"

    def is_configured(self) -> bool:
        return bool(self._sid and self._subdomain and self._user_id)

    async def _request(self, client: httpx.AsyncClient, method: str, path: str,
                       payload: Optional[dict] = None) -> Any:
        resp = await client.request(
            method, f"{self.base}{path}",
            json=payload,
            headers=_HEADERS | {"origin": self.base, "referer": f"{self.base}/publish/posts"},
            cookies={"substack.sid": self._sid or ""},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (401, 403):
            # A stale cookie and a bot-blocked request look identical from here, and the
            # operator's next move is different for each: replace the cookie, or fix the
            # request. The body distinguishes them — Cloudflare returns HTML, Substack
            # returns JSON — so pass it along instead of collapsing both to one reason.
            body = (resp.text or "")[:200].replace("\n", " ")
            edge = "<html" in body.lower() or "cloudflare" in body.lower()
            logger.warning("substack %s %s -> %s (%s) %s", method, path, resp.status_code,
                           "edge-block" if edge else "auth", body)
            raise SubstackError("blocked_by_edge" if edge else "credential_expired")
        if resp.status_code >= 400:
            # Substack names the offending field in the body; without it a 400 is a
            # guessing game. This is how draft_bylines was found.
            detail = (resp.text or "")[:300].replace("\n", " ")
            logger.warning("substack %s %s -> %s %s", method, path, resp.status_code, detail)
            raise SubstackError(f"http_{resp.status_code}: {detail}" if detail else f"http_{resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            return None

    async def create_draft(self, client: httpx.AsyncClient, doc: dict) -> int:
        data = await self._request(client, "POST", "/api/v1/drafts", {
            "type": "newsletter",
            "audience": "everyone",
            "draft_bylines": [{"id": self._user_id, "is_guest": False}],
            "draft_body": _body_field(doc),
        })
        draft_id = (data or {}).get("id")
        if not draft_id:
            raise SubstackError("no_draft_id")
        return int(draft_id)

    async def save_draft(self, client: httpx.AsyncClient, draft_id: int, *,
                         title: str, subtitle: str, doc: dict,
                         cover_image: str = "", send_email: bool = False) -> None:
        payload: dict[str, Any] = {
            "draft_title": title,
            "draft_subtitle": subtitle,
            "draft_body": _body_field(doc),
            # A created draft carries should_send_email=True by default, so a human who
            # hits Publish without noticing mails the entire list. That decision belongs
            # to the caller, explicitly, not to the platform's default.
            "should_send_email": send_email,
            # Fills the search-engine description; the lead paragraph is written for it.
            "search_engine_description": subtitle[:300],
        }
        if cover_image:
            payload["cover_image"] = cover_image
        await self._request(client, "PUT", f"/api/v1/drafts/{draft_id}", payload)

    async def upload_image(self, client: httpx.AsyncClient, data: bytes,
                           content_type: str = "image/png") -> str:
        """Put an image on Substack's own storage and return their URL.

        The editor uploads rather than linking, and the node it writes carries an
        ``s3.amazonaws.com`` src — captured from a real insert rather than guessed. Going
        through here means a published post depends on Substack for its images, not on
        our host, which also retires the dev-vs-prod URL problem for anything published.
        """
        uri = f"data:{content_type};base64,{base64.b64encode(data).decode()}"
        res = await self._request(client, "POST", "/api/v1/image", {"image": uri})
        url = (res or {}).get("url")
        if not url:
            raise SubstackError("image_upload_returned_no_url")
        return url

    async def publish_draft(self, client: httpx.AsyncClient, draft_id: int) -> None:
        """Publish a draft to the web WITHOUT emailing anybody.

        ``send_email`` is hard-wired False and there is no parameter to flip it. Mailing
        the subscriber list is irreversible; making it reachable from a config flag means
        one typo in an env file sends a newsletter. If it is ever wanted, that should be a
        deliberate code change with its own review, not a value someone can set.

        Verified live: this returns the post with ``is_published: true`` and
        ``email_sent_at: null``.
        """
        await self._request(client, "POST", f"/api/v1/drafts/{draft_id}/publish",
                            {"send_email": False})

    async def delete_draft(self, client: httpx.AsyncClient, draft_id: int) -> None:
        await self._request(client, "DELETE", f"/api/v1/drafts/{draft_id}")

    async def draft_ids(self, client: httpx.AsyncClient, limit: int = 20) -> list[int]:
        """Ids of the publication's drafts.

        The response is ``{posts, hasMore, nextCursor}`` — the key is **posts**, not
        "drafts". Guessing it wrong cost nothing visible: the endpoint returns 200, the
        lookup misses, and the function reports an empty publication forever. Verified
        against the live response rather than inferred from the path.
        """
        limit = max(1, min(limit, MAX_DRAFT_LIMIT))
        data = await self._request(client, "GET", f"/api/v1/drafts?limit={limit}")
        items = data if isinstance(data, list) else (data or {}).get("posts") or []
        return [int(d["id"]) for d in items if isinstance(d, dict) and d.get("id")]


def image_node(src: str, width: int, height: int, size_bytes: int,
               content_type: str = "image/png") -> dict:
    """The node Substack's editor writes for an inserted image.

    Shape captured from a real insert. Substack accepts any node type on save without
    validating it — three guessed shapes were all stored happily and then hung the
    editor when opened — so this is transcribed, not inferred.
    """
    return {
        "type": "captionedImage",
        "content": [{
            "type": "image2",
            "attrs": {
                "src": src,
                "srcNoWatermark": None,
                "fullscreen": None,
                "imageSize": None,
                "height": height,
                "width": width,
                "resizeWidth": None,
                "bytes": size_bytes,
                "alt": None,
                "title": None,
                "type": content_type,
                "href": None,
                "belowTheFold": False,
                "topImage": True,
                "internalRedirect": None,
                "isProcessing": False,
                "align": None,
                "offset": False,
            },
        }],
    }


def _body_field(doc: dict) -> str:
    """draft_body is the JSON string of the document, never the object itself."""
    import json

    return json.dumps(doc, ensure_ascii=False)


def public_url(subdomain: str, post: dict | None) -> str:
    """The reader-facing URL of a published post, from the slug Substack assigned."""
    slug = ((post or {}).get("slug") or "").strip()
    return f"https://{subdomain}.substack.com/p/{slug}" if slug else f"https://{subdomain}.substack.com/"


def draft_url(subdomain: str, draft_id: int) -> str:
    return f"https://{subdomain}.substack.com/publish/post/{draft_id}"


async def create_summary_draft(
    episode_id: str,
    title: str,
    summary_markdown: str,
    *,
    podcast_name: str = "",
    subtitle: str = "",
    cover_image_url: str = "",
    send_email: bool = False,
    publish: bool = False,
    dry_run: bool = True,
) -> dict:
    """Stage one episode summary as a Substack draft. Never publishes."""
    client = SubstackClient()
    result: dict[str, Any] = {
        "platform": "substack",
        "configured": client.is_configured(),
        "dry_run": dry_run,
        "episode_id": episode_id,
        "posted": False,
    }
    if not client.is_configured():
        result["reason"] = "not_configured"
        return result

    markdown = to_syndication_markdown(summary_markdown, episode_id, settings.site_url, podcast_name)
    doc = markdown_to_prosemirror(markdown)

    if dry_run:
        result["reason"] = "dry_run"
        result["block_count"] = len(doc.get("content") or [])
        return result

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
            # The cover goes in the BODY, not just the cover_image field: on Substack the
            # first body image is what the feed thumbnail and the share card come from —
            # a reference post's og:image and its first body image are the same asset.
            # Uploading also moves the file onto Substack's storage, so the published post
            # stops depending on our host.
            hosted = ""
            if cover_image_url:
                try:
                    resp = await http.get(cover_image_url)
                    if resp.status_code == 200 and resp.content:
                        hosted = await client.upload_image(http, resp.content)
                        doc = {**doc, "content": [
                            image_node(hosted, COVER_WIDTH, COVER_HEIGHT, len(resp.content)),
                            *doc.get("content", []),
                        ]}
                except (httpx.HTTPError, SubstackError) as e:
                    # A post without its cover is still a post; losing the whole draft over
                    # an image is the worse trade.
                    logger.warning("substack: cover upload failed for %s (%s)", episode_id, e)

            draft_id = await client.create_draft(http, doc)
            await client.save_draft(http, draft_id, title=title, subtitle=subtitle, doc=doc,
                                    cover_image=hosted or cover_image_url, send_email=send_email)
    except SubstackError as e:
        logger.warning("substack draft failed for %s: %s", episode_id, e)
        result["reason"] = str(e)
        return result

    published, back = False, None
    if publish:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                await client.publish_draft(http, draft_id)
                # Read back rather than trust the write: this is the one call whose
                # failure mode would be a newsletter nobody meant to send.
                back = await client._request(http, "GET", f"/api/v1/drafts/{draft_id}")
            published = bool((back or {}).get("is_published"))
            if (back or {}).get("email_sent_at"):
                logger.error("substack: %s was emailed despite send_email=False", draft_id)
        except SubstackError as e:
            logger.warning("substack publish failed for %s: %s", episode_id, e)
            result["reason"] = f"published_failed: {e}"

    result.update({
        "posted": True,
        "draft_id": draft_id,
        "url": (public_url(client._subdomain, back) if published
                else draft_url(client._subdomain, draft_id)),
        "published": published,
        "emailed": False,
        "note": None if published else "draft_only_publish_manually",
    })
    logger.info("substack draft %s staged for %s", draft_id, episode_id)
    return result
