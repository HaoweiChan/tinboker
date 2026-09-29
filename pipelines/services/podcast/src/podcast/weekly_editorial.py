"""Source-grounded weekly editorial cards; CLI never uploads or publishes."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import html
import json
import os
import re
from datetime import date
from pathlib import Path

from .content_builder.card_deck import ACCENT_YELLOW, _focus_list_slide, card_theme_css
from .content_builder.llm import _LLM_OVERRIDES, _model_name, invoke_json, load_prompt

VERSION = "weekly-editorial-v3"
MAX_SOURCE_CHARS = 240_000


def _validate_material(material: dict) -> dict:
    week = material["week"]
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError("Invalid ISO week")
    year, number = map(int, week.replace("W", "").split("-"))
    start, end = date.fromisocalendar(year, number, 1), date.fromisocalendar(year, number, 7)
    if material["start"] != start.isoformat() or material["end"] != end.isoformat():
        raise ValueError("Week boundaries disagree")
    episodes = material["episodes"]
    if not 3 <= len(episodes) <= 80:
        raise ValueError("Need 3–80 source episodes")
    ids = set()
    for ep in episodes:
        if not isinstance(ep.get("episode_id"), str) or not re.fullmatch(r"[\w-]{3,160}", ep["episode_id"]):
            raise ValueError("Invalid episode ID")
        if ep["episode_id"] in ids:
            raise ValueError("Duplicate episode ID")
        ids.add(ep["episode_id"])
        if not start <= date.fromisoformat(ep["date"]) <= end:
            raise ValueError("Source outside requested week")
        if not all(isinstance(ep.get(k), str) and ep[k].strip() for k in ("podcast_name", "title", "summary")):
            raise ValueError("Incomplete source")
        if not 100 <= len(ep["summary"]) <= 24000:
            raise ValueError("Source summary outside size bounds")
    if sum(len(e["summary"]) for e in episodes) > MAX_SOURCE_CHARS:
        raise ValueError("Source budget exceeded")
    return material


def validate_material(material: dict) -> dict:
    try:
        return _validate_material(material)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed weekly sources") from exc


def _text(value, minimum: int, maximum: int, *, multiline: bool = False, field: str = "card text") -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f"{field}: expected {minimum}–{maximum} characters, got {len(value) if isinstance(value, str) else type(value).__name__}")
    value = value.strip()
    if (not multiline and "\n" in value) or re.search(r"[<>]|https?://|[我你]", value):
        raise ValueError("Unsafe markup, link or personal voice")
    return value


def validate_editorial(result: dict, material: dict) -> dict:
    if not isinstance(result, dict) or result.get("skip"):
        raise ValueError("Insufficient editorial material")
    sources = {ep["episode_id"]: ep for ep in material["episodes"]}
    post = _text(result.get("post"), 180, 350, multiline=True, field="post")
    cards = result.get("cards")
    if not isinstance(cards, list) or len(cards) != 3:
        raise ValueError("Exactly three cards required")
    titles = set()
    for card in cards:
        title = _text(card.get("title"), 5, 16)
        if title in titles:
            raise ValueError("Duplicate theme")
        titles.add(title)
        claims = card.get("claims")
        if not isinstance(claims, list) or len(claims) != 2:
            raise ValueError("Each card needs two sourced claims")
        evidence_ids = set()
        for claim in claims:
            _text(claim.get("heading"), 2, 11)
            _text(claim.get("body"), 15, 48)
            ep = sources.get(claim.get("episode_id"))
            quote = claim.get("quote")
            if ep is None or not isinstance(quote, str) or len(quote.strip()) < 12 or quote.strip() not in _visible_summary(ep["summary"]):
                raise ValueError("Claim evidence not found in source")
            evidence_ids.add(ep["episode_id"])
        viewpoint = card.get("viewpoint") or {}
        _text(viewpoint.get("heading"), 5, 18)
        body = _text(viewpoint.get("body"), 25, 65)
        if any(term in body for term in ("持續關注", "值得關注", "後續觀察", "密切留意", "有待觀察")):
            raise ValueError("Generic viewpoint")
        refs = viewpoint.get("episode_ids")
        if not isinstance(refs, list) or not refs or set(refs) != evidence_ids:
            raise ValueError("Viewpoint must trace to both claims")
    return {"week": material["week"], "post": post, "cards": cards}


def editorial_role() -> str:
    # Explicit weekly configuration wins; otherwise use the short-form writer.
    if _LLM_OVERRIDES.get("weekly_copy_writer_model") or os.getenv("WEEKLY_COPY_WRITER_MODEL"):
        return "weekly_copy_writer"
    return "social_copy_writer"


def _cached_call(stage: str, messages: list, cache_dir: Path) -> dict:
    # At most writer + reviewer + one repair + reviewer; transport retries are bounded.
    role = editorial_role()
    key = hashlib.sha256(json.dumps([VERSION, stage, _model_name(role), messages], ensure_ascii=False).encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = cache_dir / f"{key}.json"
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return json.loads(path.read_text())
        result = invoke_json(role, messages)
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False))
        temp.replace(path)
        return result


def _visible_summary(summary: str) -> str:
    # Preserve all prose; remove only link destinations and emphasis delimiters.
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", summary).replace("**", "")


REVIEW_PATHS = {"post", *(f"cards[{i}].{field}" for i in range(3)
                         for field in ("claims[0]", "claims[1]", "viewpoint"))}


def review_passed(verdict: dict, material: dict) -> bool:
    """A blanket approval cannot bypass missing or contradictory field evidence."""
    if not isinstance(verdict, dict) or verdict.get("approved") is not True or verdict.get("issues") != []:
        return False
    checks = verdict.get("checks")
    if not isinstance(checks, list) or len(checks) != len(REVIEW_PATHS):
        return False
    sources = {ep["episode_id"]: _visible_summary(ep["summary"]) for ep in material["episodes"]}
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            return False
        path = check.get("path")
        if not isinstance(path, str) or path not in REVIEW_PATHS or path in seen or check.get("supported") is not True:
            return False
        seen.add(path)
        reason = check.get("reason")
        evidence = check.get("evidence")
        if not isinstance(reason, str) or len(reason.strip()) < 12 or not isinstance(evidence, list) or not evidence:
            return False
        for item in evidence:
            if not isinstance(item, dict):
                return False
            quote, episode_id = item.get("quote"), item.get("episode_id")
            if not isinstance(episode_id, str) or episode_id not in sources or not isinstance(quote, str) or len(quote.strip()) < 12 or quote.strip() not in sources[episode_id]:
                return False
    return seen == REVIEW_PATHS


def generate_editorial(material: dict, cache_dir: Path, candidate: dict | None = None) -> dict:
    validate_material(material)
    normalized = {**material, "episodes": [{**ep, "summary": _visible_summary(ep["summary"])} for ep in material["episodes"]]}
    prompt = load_prompt("weekly_editorial")
    messages = [{"role": "system", "content": prompt["system"]},
                {"role": "user", "content": json.dumps(normalized, ensure_ascii=False)}]
    if candidate is None:
        candidate = _cached_call("write", messages, cache_dir)
    repaired = False

    def repair(draft: dict, issues: str) -> dict:
        repair_messages = [*messages, {"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)},
                           {"role": "user", "content": f"草稿未通過驗證：{issues}。只准修一次。逐欄計字，所有欄位遵守字數限制；主文180至350字且只含三張卡可支持的內容。quote 必須連續逐字複製來源，不能改空格或省字。重新輸出完整JSON，不可縮短事實的條件、否定或假設性質。"}]
        return _cached_call("repair", repair_messages, cache_dir)

    def review(draft: dict) -> dict:
        cited_ids = {claim["episode_id"] for card in draft["cards"] for claim in card["claims"]}
        cited = {**normalized, "episodes": [ep for ep in normalized["episodes"] if ep["episode_id"] in cited_ids]}
        return _cached_call("review", [{"role": "system", "content": prompt["review"]},
                                       {"role": "user", "content": json.dumps({"sources": cited, "draft": draft}, ensure_ascii=False)}], cache_dir)

    try:
        result = validate_editorial(candidate, material)
    except (ValueError, TypeError, AttributeError) as exc:
        if isinstance(candidate, dict) and candidate.get("skip"):
            raise ValueError("Insufficient editorial material") from exc
        result = validate_editorial(repair(candidate, str(exc)), material)
        repaired = True
    verdict = review(result)
    if not review_passed(verdict, material):
        if not repaired:
            result = validate_editorial(repair(result, json.dumps(verdict, ensure_ascii=False)), material)
            verdict = review(result)
        if not review_passed(verdict, material):
            raise ValueError(f"Editorial evidence review failed: {json.dumps(verdict, ensure_ascii=False)}")
    result["review"] = verdict
    return result


WEEKLY_CSS = """
section header {position:absolute;top:28px;left:88px;font-size:24px;font-weight:600;color:#ffd23f;letter-spacing:1px;}
section.focus-list .flead {display:block;overflow:visible;}
section.focus-list .fname {font-size:34px;}
section.focus-list .takeaway {margin-top:28px;padding:24px 28px;background:#292617;border-left:6px solid #ffd23f;}
section.focus-list .takeaway-label {display:flex;align-items:center;justify-content:space-between;color:#ffd23f;font-size:30px;font-weight:800;margin-bottom:14px;}
section.focus-list .takeaway-label span {font-size:22px;font-weight:500;color:#c5bc99;}
section.focus-list .takeaway h3 {margin:0 0 10px;font-size:36px;line-height:1.4;color:#f5e7b6;font-weight:800;}
section.focus-list .takeaway p {margin:0;font-size:31px;line-height:1.55;color:#e7e2d1;}
"""


def build_deck(result: dict, material: dict) -> tuple[str, str]:
    validate_editorial(result, validate_material(material))
    sources = {ep["episode_id"]: ep for ep in material["episodes"]}
    label = f'週報 {material["week"].split("-")[1]}｜{material["start"][5:].replace("-", "/")}–{material["end"][5:].replace("-", "/")}'
    slides = []
    for card in result["cards"]:
        items = []
        for claim in card["claims"]:
            ep = sources[claim["episode_id"]]
            name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9 ]", "", ep["podcast_name"]).strip()[:12]
            items.append({"name": claim["heading"], "lead": claim["body"], "source": f'{name} {ep["date"][5:].replace("-", "/")}'})
        slide = _focus_list_slide({"title": card["title"], "items": items})
        vp = card["viewpoint"]
        slide += '\n\n<div class="takeaway"><div class="takeaway-label">聽播客觀點<span>綜合節目內容</span></div>'
        slide += f'<h3>{html.escape(vp["heading"])}</h3><p>{html.escape(vp["body"])}</p></div>'
        slides.append(slide)
    front = f'---\nmarp: true\ntheme: tinboker-cards\nsize: 1:1\npaginate: false\nheader: "{label}"\nfooter: ""\n---\n\n'
    return front + '\n\n---\n\n'.join(slides), card_theme_css(*ACCENT_YELLOW) + WEEKLY_CSS


def render_editorial(result: dict, material: dict) -> tuple[str, str, list[str]]:
    from src.pipeline.steps.social_cards_render import _render_png
    markdown, css = build_deck(result, material)
    images = _render_png(markdown, css, os.environ.get("MARP_SERVICE_URL", "http://localhost:5004"))
    if len(images) != 3:
        raise ValueError("Weekly renderer must return three cards")
    for image in images:
        raw = base64.b64decode(image, validate=True)
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or int.from_bytes(raw[16:20], "big") != 1080 or int.from_bytes(raw[20:24], "big") != 1080:
            raise ValueError("Invalid weekly PNG dimensions")
    return markdown, css, images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--candidate-file", type=Path, help="Reuse a saved model candidate for bounded repair evaluation")
    args = parser.parse_args()
    from shared.secrets import bootstrap
    bootstrap(gsm_vars=("OPENROUTER_API_KEY",), optional_vars=())
    material = json.loads(args.input.read_text())
    result = generate_editorial(material, args.cache_dir or args.out_dir / "cache",
                                json.loads(args.candidate_file.read_text()) if args.candidate_file else None)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "editorial.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    markdown, css = build_deck(result, material)
    (args.out_dir / "weekly.md").write_text(markdown)
    (args.out_dir / "theme.css").write_text(css)
    if not args.no_render:
        _, _, images = render_editorial(result, material)
        for i, image in enumerate(images, 1):
            (args.out_dir / f"weekly.{i:03}.png").write_bytes(base64.b64decode(image))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
