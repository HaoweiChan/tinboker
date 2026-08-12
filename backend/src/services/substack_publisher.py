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
months, so it is read from settings at boot like every other stable secret.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.config import settings
from src.services.substack_prosemirror import markdown_to_prosemirror
from src.services.syndication_markdown import to_syndication_markdown

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0


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
            headers={"content-type": "application/json"},
            cookies={"substack.sid": self._sid or ""},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 401 or resp.status_code == 403:
            raise SubstackError("credential_expired")
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
                         title: str, subtitle: str, doc: dict) -> None:
        await self._request(client, "PUT", f"/api/v1/drafts/{draft_id}", {
            "draft_title": title,
            "draft_subtitle": subtitle,
            "draft_body": _body_field(doc),
        })

    async def delete_draft(self, client: httpx.AsyncClient, draft_id: int) -> None:
        await self._request(client, "DELETE", f"/api/v1/drafts/{draft_id}")

    async def draft_ids(self, client: httpx.AsyncClient, limit: int = 20) -> list[int]:
        data = await self._request(client, "GET", f"/api/v1/drafts?limit={limit}")
        items = data if isinstance(data, list) else (data or {}).get("drafts") or []
        return [int(d["id"]) for d in items if isinstance(d, dict) and d.get("id")]


def _body_field(doc: dict) -> str:
    """draft_body is the JSON string of the document, never the object itself."""
    import json

    return json.dumps(doc, ensure_ascii=False)


def draft_url(subdomain: str, draft_id: int) -> str:
    return f"https://{subdomain}.substack.com/publish/post/{draft_id}"


async def create_summary_draft(
    episode_id: str,
    title: str,
    summary_markdown: str,
    *,
    subtitle: str = "",
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

    markdown = to_syndication_markdown(summary_markdown, episode_id, settings.site_url)
    doc = markdown_to_prosemirror(markdown)

    if dry_run:
        result["reason"] = "dry_run"
        result["block_count"] = len(doc.get("content") or [])
        return result

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
            draft_id = await client.create_draft(http, doc)
            await client.save_draft(http, draft_id, title=title, subtitle=subtitle, doc=doc)
    except SubstackError as e:
        logger.warning("substack draft failed for %s: %s", episode_id, e)
        result["reason"] = str(e)
        return result

    result.update({
        "posted": True,
        "draft_id": draft_id,
        "url": draft_url(client._subdomain, draft_id),
        "note": "draft_only_publish_manually",
    })
    logger.info("substack draft %s staged for %s", draft_id, episode_id)
    return result
