"""Weekly Threads copy: one post plus a short comment chain, from the weekly rollup.

Deliberately NOT a LangGraph node. The episode writer runs inside the ingest graph
because its input is episode state; this one's input is the backend's
``GET /api/weekly/{week}`` rollup, which no pipeline stage produces. So it is a plain
function over a dict, with a CLI on top:

    uv run --package tinboker-podcast python -m podcast.weekly_copy 2026-W36

The rollup's ``flips`` (which tickers the same shows changed their mind about) are
computed by the backend, not here — the weekly video reads the same field, and the two
must never name different tickers. See backend/src/routers/weekly.py:flip_rows.

Publishing is a separate, manual step: POST the result to /api/admin/promo/publish
alongside the rendered video. Nothing here posts anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from typing import Any

from .content_builder.llm import invoke_json, load_prompt
from .content_builder.nodes.social_copy_writer import (
    # the episode writer's 我-detector, reused rather than re-implemented so the two
    # cannot drift; it warns and never edits (see the reasoning at its definition)
    _report_first_person,
)

TOP_TICKERS = 8          # what the video shows, so the post and the video agree
TOP_SECTORS = 6
MAX_COMMENTS = 4         # 3 content + the link, matching the episode chain length
LINK_COMMENT = "完整週報：https://tinboker.com"

_TICKER_KEYS = ("ticker", "name", "episodes", "bull", "neu", "bear",
                "prev_bull", "prev_neu", "prev_bear",
                # the stated reason behind each side, so the post can quote a show
                # instead of reciting a scoreboard
                "bull_why", "bear_why")


def _slim(row: dict, keys: tuple[str, ...]) -> dict:
    return {k: row.get(k) for k in keys if row.get(k) is not None}


def build_messages(rollup: dict) -> list[dict[str, str]]:
    """Render the weekly_copy_writer chat messages from a /api/weekly/{week} payload."""
    prompts = load_prompt("weekly_copy_writer")
    tickers = [_slim(t, _TICKER_KEYS) for t in (rollup.get("tickers") or [])[:TOP_TICKERS]]
    flips = [_slim(f, _TICKER_KEYS + ("direction",)) for f in rollup.get("flips") or []]
    # An empty `flips` is a real, common answer (see backend flip_rows) — say so rather
    # than leaving the model to infer that silence means nothing happened.
    flips_note = json.dumps(flips, ensure_ascii=False, indent=2) if flips else \
        "（本週沒有任何一檔跨過「有人改變說法」的門檻。不要硬掰轉向，就寫這件事本身。）"
    sectors = [{"name": s.get("display_name"), "episodes": s.get("episodes")}
               for s in (rollup.get("sectors") or [])[:TOP_SECTORS]]
    start, end = rollup.get("start", ""), rollup.get("end", "")
    user = prompts["user"].format(
        week=rollup.get("week", ""),
        range=f"{start} ~ {end}",
        episode_count=rollup.get("episode_count", 0),
        podcast_count=len(rollup.get("podcasts") or []),
        tickers=json.dumps(tickers, ensure_ascii=False, indent=2),
        flips=flips_note,
        sectors=json.dumps(sectors, ensure_ascii=False, indent=2),
        podcasts=json.dumps([p.get("name") for p in rollup.get("podcasts") or []], ensure_ascii=False),
    )
    return [{"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user}]


def postprocess(result: Any) -> dict[str, Any]:
    """Normalise into ``{post, comments: [str]}`` — the shape /promo/publish takes.

    The link comment is appended here rather than trusted to the model: the promo
    publisher adds nothing of its own (unlike the episode publisher, which inserts the
    permalink as reply 0), so a model that forgets the link publishes a thread with no
    way back to the site.
    """
    post, comments = "", []
    if isinstance(result, dict):
        post = (result.get("post") or "").strip()
        for item in result.get("comments") or []:
            text = (item.get("text") if isinstance(item, dict) else str(item) or "").strip()
            if text:
                comments.append(text)
    comments = [c for c in comments if "tinboker.com" not in c][:MAX_COMMENTS - 1]
    comments.append(LINK_COMMENT)
    _report_first_person(post, [{"text": c} for c in comments])
    return {"post": post, "comments": comments}


def write_weekly_copy(rollup: dict) -> dict[str, Any]:
    return postprocess(invoke_json("weekly_copy_writer", build_messages(rollup)))


def fetch_rollup(week: str, api: str) -> dict:
    url = f"{api.rstrip('/')}/api/weekly/{week}"
    with urllib.request.urlopen(url, timeout=120) as r:   # noqa: S310 (our own API)
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("week", help="ISO week, e.g. 2026-W36")
    ap.add_argument("--api", default="https://dev-api.tinboker.com",
                    help="backend serving /api/weekly (flips ship to dev first)")
    ap.add_argument("--out", help="write the JSON here as well as stdout")
    args = ap.parse_args()

    rollup = fetch_rollup(args.week, args.api)
    if "flips" not in rollup:
        print(f"  ⚠ {args.api} has no `flips` field — that backend predates flip_rows; "
              f"the copy will not lead with a sentiment turn", file=sys.stderr)
    copy = write_weekly_copy(rollup)
    text = json.dumps(copy, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
