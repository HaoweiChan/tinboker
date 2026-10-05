"""Offline theme-view validation; local artifacts only, at most twelve paid calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

PROMPT = Path(__file__).resolve().parent / "content_builder" / "prompts" / "theme_views.yaml"
MAX_EPISODES = 12
MAX_OUTPUT_TOKENS = 4096
HEADING = re.compile(r"^##[ \t]+(.+)$", re.MULTILINE)
TIME = re.compile(r"\(#time:(\d+)\)")
TICKER = re.compile(r"\[([^\]\n]+)\]\(#ticker:([^\s)]+)\)")


class NamedTicker(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ThemeView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    theme_label: str = Field(min_length=1, max_length=80)
    stance: Literal["bullish", "bearish", "neutral", "mixed"]
    thesis: str = Field(min_length=1, max_length=600)
    start_time_ms: int | None = Field(ge=0)
    named_tickers: list[NamedTicker] = Field(max_length=30)
    evidence: str = Field(min_length=1, max_length=600)


class ThemeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    theme_views: list[ThemeView] = Field(max_length=3)


def parse_chapters(markdown: str) -> list[dict]:
    """Split the summary at its `##` headings, keeping each chapter timestamp."""
    headings = list(HEADING.finditer(markdown))
    if not headings:
        return [{"heading": "Unsectioned summary", "start_time_ms": None, "text": markdown}]
    chapters = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        timestamp = TIME.search(heading.group(1))
        chapters.append({
            "heading": heading.group(1),
            "start_time_ms": int(timestamp.group(1)) if timestamp else None,
            "text": markdown[heading.start():end],
        })
    return chapters


def normalized(label: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", label)).casefold()


def taxonomy_index(rows: list[dict]) -> dict[str, str | None]:
    """Exact normalized names/aliases only; ambiguous aliases remain unmatched."""
    index: dict[str, str | None] = {}
    for row in rows:
        if row.get("exposure_type") != "theme" or not row.get("exposure_id"):
            continue
        for label in [row["display_zh"], *(row.get("aliases") or [])]:
            if not isinstance(label, str) or not label.strip():
                continue
            key = normalized(label)
            exposure_id = row["exposure_id"]
            index[key] = exposure_id if key not in index else (
                exposure_id if index[key] == exposure_id else None
            )
    return index


def validate_response(raw: str, markdown: str, taxonomy: list[dict]) -> list[dict]:
    """Validate strict JSON, chapter timestamps and ticker anchors; flag loose quotes."""
    from shared.tickers_seed_backup import TICKERS_SEED

    response = ThemeResponse.model_validate_json(raw)
    chapter_times = {chapter["start_time_ms"] for chapter in parse_chapters(markdown)}
    anchors = set(TICKER.findall(markdown))
    names = taxonomy_index(taxonomy)
    views = []
    seen = set()
    seen_exposures = set()
    for view in response.theme_views:
        key = normalized(view.theme_label)
        if not key or key in seen:
            raise ValueError("Blank or duplicate theme label")
        seen.add(key)
        # Hard failures are things the model must never invent: a timestamp that is
        # not a chapter anchor, or a ticker that is not linked in the summary. The
        # first live run (12 Gooaye episodes) showed that requiring quote, timestamp
        # and tickers to share ONE chapter rejected 9 correct episodes — summaries
        # split a topic over a timed heading and untimed sub-headings — and that the
        # model paraphrases about half its quotes, so a non-verbatim quote is only
        # flagged for the reviewer.
        if not view.evidence.strip():
            raise ValueError("Blank evidence")
        if view.start_time_ms is not None and view.start_time_ms not in chapter_times:
            raise ValueError("Timestamp is not a chapter anchor")
        pairs = {(ticker.name, ticker.ticker) for ticker in view.named_tickers}
        if len(pairs) != len(view.named_tickers):
            raise ValueError("Duplicate named ticker")
        if not pairs.issubset(anchors):
            raise ValueError("Named ticker is not linked in the summary")
        result = view.model_dump()
        result["evidence_verbatim"] = view.evidence.strip() in markdown
        result["exposure_id"] = names.get(key)
        if result["exposure_id"] is not None:
            if result["exposure_id"] in seen_exposures:
                raise ValueError("Multiple labels map to the same theme exposure")
            seen_exposures.add(result["exposure_id"])
        for ticker in result["named_tickers"]:
            record = TICKERS_SEED.get(ticker["ticker"])
            if record is None:
                record = next((item for item in TICKERS_SEED.values()
                               if ticker["ticker"] in item.get("aliases", [])), None)
            if record and record.get("type") != "company":
                raise ValueError("Named ticker is not a company")
            ticker["market"] = record.get("market") if record else None
        views.append(result)
    return views


def release_date(row: dict) -> str:
    value = row.get("released_at") or row.get("released_at_ms") or row.get("spotify_release_date")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    if not value:
        raise ValueError(f"Missing release date: {row['episode_id']}")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def select_episodes(rows: list[dict], ids: list[str], podcast: str | None, limit: int) -> list[dict]:
    if not 1 <= limit <= MAX_EPISODES:
        raise ValueError("--limit must be between 1 and 12")
    if bool(ids) == bool(podcast):
        raise ValueError("Supply episode ids OR --podcast")
    by_id = {row["episode_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("Episode export contains duplicate ids")
    if ids:
        selected = [by_id[episode_id] for episode_id in dict.fromkeys(ids)]
    else:
        selected = sorted((row for row in rows if row["podcast_name"] == podcast),
                          key=release_date, reverse=True)[:limit]
    if not selected or len(selected) > MAX_EPISODES:
        raise ValueError("Select between 1 and 12 unique episodes")
    for row in selected:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", row["episode_id"]):
            raise ValueError("Unsafe episode id")
        release_date(row)
    return selected


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_summary(row: dict, out: Path) -> str:
    cache = out / f"{row['episode_id']}.summary.md"
    if "summary_markdown" in row:
        markdown = row["summary_markdown"]
    elif row.get("summary_path"):
        markdown = Path(row["summary_path"]).read_text(encoding="utf-8")
    elif cache.exists():
        markdown = cache.read_text(encoding="utf-8")
    else:
        response = httpx.get(row["summary_public_url"], timeout=30, follow_redirects=True)
        response.raise_for_status()
        markdown = response.text
    if not markdown.strip() or len(markdown) > 80000:
        raise ValueError("Summary must contain 1–80000 characters")
    cache.write_text(markdown, encoding="utf-8")
    return markdown


def write_review(out: Path, results: list[tuple[dict, str]], report: dict) -> None:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["# Theme views validation review", "", "Offline prototype; no production writes.", ""]
    for result, markdown in results:
        lines += [f"## EP{result['episode_number']} — {result['released_at']}", "",
                  f"Episode: `{result['episode_id']}`", "",
                  "| Theme | Exposure | Stance | Thesis | Start (ms) | Named tickers | Evidence |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for view in result["theme_views"]:
            tickers = ", ".join(f"{t['name']} ({t['ticker']}, {t['market']})" for t in view["named_tickers"])
            values = [view["theme_label"], view["exposure_id"], view["stance"], view["thesis"],
                      view["start_time_ms"], tickers, view["evidence"]]
            lines.append("| " + " | ".join(map(cell, values)) + " |")
        if not result["theme_views"]:
            lines += ["", "No qualifying theme views."]
        lines += ["", "Chapter headings:", ""]
        lines += [f"- {chapter['heading']}" for chapter in parse_chapters(markdown)]
        lines.append("")
    lines += ["## Run accounting", "", "```json", json.dumps(report, ensure_ascii=False, indent=2), "```", ""]
    (out / "theme_views_review.md").write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> dict:
    from langsmith import tracing_context
    from shared.secrets import bootstrap

    bootstrap(gsm_vars=("OPENROUTER_API_KEY",), optional_vars=())
    from podcast.content_builder.llm import get_model

    rows = json.loads(args.episodes_json.read_text(encoding="utf-8"))
    taxonomy = json.loads(args.taxonomy_json.read_text(encoding="utf-8"))
    selected = select_episodes(rows, args.episode_ids, args.podcast, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    summaries = [(row, load_summary(row, args.out)) for row in selected]
    prompt = yaml.safe_load(PROMPT.read_text(encoding="utf-8"))["system"]
    vocabulary = [{"name": row["display_zh"], "aliases": row.get("aliases") or []}
                  for row in taxonomy if row.get("exposure_type") == "theme"]
    model = get_model("extractor", model_override=args.model)
    client = model.root_client.with_options(timeout=90, max_retries=0)
    model = model.model_copy(update={"max_tokens": MAX_OUTPUT_TOKENS, "client": client.chat.completions})
    report = {"model": model.model_name, "calls": 0, "cached_responses": 0,
              "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
              "cost_usd": 0.0, "cost_complete": True, "unmatched_labels": [], "errors": {}}
    results = []
    started = time.monotonic()
    for row, markdown in summaries:
        episode_id = row["episode_id"]
        messages = [("system", prompt), ("human", json.dumps({"taxonomy": vocabulary, "summary": markdown}, ensure_ascii=False))]
        fingerprint = hashlib.sha256(json.dumps({"messages": messages, "model": model.model_name,
            "params": model._identifying_params, "format": "json_object"}, sort_keys=True, default=str).encode()).hexdigest()
        cache = args.out / f"{episode_id}.raw.json"
        attempt = args.out / f"{episode_id}.attempt.json"
        try:
            if cache.exists():
                saved = json.loads(cache.read_text(encoding="utf-8"))
                if saved["fingerprint"] != fingerprint:
                    raise ValueError("Cached input/config differs; refusing another call for this episode")
                report["cached_responses"] += 1
            else:
                if report["calls"] >= MAX_EPISODES:
                    raise ValueError("Paid call budget exhausted")
                if attempt.exists():
                    report["cost_complete"] = False
                # Exclusive creation also prevents two processes billing the same episode.
                with attempt.open("x", encoding="utf-8") as handle:
                    json.dump({"fingerprint": fingerprint}, handle)
                report["calls"] += 1
                try:
                    with tracing_context(enabled=False):
                        response = model.invoke(messages, response_format={"type": "json_object"})
                except Exception:
                    report["cost_complete"] = False
                    raise
                saved = {"fingerprint": fingerprint, "content": response.content,
                         "usage": response.usage_metadata or {}, "metadata": response.response_metadata}
                write_json(cache, saved)
            usage = saved["usage"]
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                report[key] += usage.get(key, 0)
            cost = saved["metadata"].get("token_usage", {}).get("cost")
            if cost is None:
                report["cost_complete"] = False
            else:
                report["cost_usd"] += float(cost)
            views = validate_response(saved["content"], markdown, taxonomy)
            result = {"episode_id": episode_id, "episode_number": row["episode_number"],
                      "released_at": release_date(row), "theme_views": views}
            write_json(args.out / f"{episode_id}.json", result)
            results.append((result, markdown))
            report["unmatched_labels"].extend(view["theme_label"] for view in views if view["exposure_id"] is None)
        except Exception as exc:
            # Raw responses are retained; failed validations never trigger paid repairs.
            report["errors"][episode_id] = type(exc).__name__
    report["unmatched_labels"] = sorted(set(report["unmatched_labels"]))
    report["wall_seconds"] = round(time.monotonic() - started, 3)
    write_json(args.out / "run_report.json", report)
    write_review(args.out, results, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_ids", nargs="*")
    parser.add_argument("--episodes-json", required=True, type=Path)
    parser.add_argument("--taxonomy-json", required=True, type=Path)
    parser.add_argument("--podcast")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", help="Optional invocation-local override of the configured extractor model")
    report = run(parser.parse_args())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
