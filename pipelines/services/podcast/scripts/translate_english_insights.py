#!/usr/bin/env python3
"""Translate legacy English ticker_insights theses to Traditional Chinese (zh-TW).

A backlog of insights (overwhelmingly under 財經一路發, extracted before the
ticker-extractor prompt enforced zh-TW) stored their ``bluf_thesis`` — and
sometimes reason/risk titles/descriptions — in English. New episodes are already
zh-TW, so this only repairs the orphaned backlog in place: it TRANSLATES the
English natural-language fields and leaves everything else (ticker, sentiment,
scores, timestamps, indices, categories, severities) untouched.

One LLM call per affected doc translates all of its English snippets at once.
Chinese snippets are left as-is. DRY-RUN BY DEFAULT — pass ``--apply`` to write.

Usage:
    uv run python services/podcast/scripts/translate_english_insights.py --podcast "財經一路發"
    uv run python services/podcast/scripts/translate_english_insights.py --podcast "財經一路發" --limit 5
    uv run python services/podcast/scripts/translate_english_insights.py --podcast "財經一路發" --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001
    print(f"  (secrets_bootstrap skipped: {_e})")

from src.service.upload_to_firebase import FirebaseService  # noqa: E402

INSIGHTS_SUBCOLLECTION = "tickers"
SUPPORTED_SCHEMA = {2, 3}
# Gemini handles zh-TW finance translation cleanly; the default OpenRouter model
# (mimo) left snippets half-translated. Overridable via --model.
DEFAULT_MODEL = "gemini-2.5-flash"
_MAX_RETRIES = 3
# Fields on a reason/risk dict that carry natural language.
TEXT_KEYS = ("title", "description")


def is_english(text: str | None) -> bool:
    """True when a snippet is Latin-dominant (more A–Z letters than CJK chars)."""
    if not text:
        return False
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[一-鿿]", text))
    return latin > cjk


# A run of 4+ consecutive English words = English prose (catches half-translated
# docs too), while tolerating isolated tickers/short names (NVDA, Meta Platforms, ETF).
_EN_PROSE_RUN = re.compile(r"(?:\b[A-Za-z][A-Za-z'’.-]*\b[ \t,]*){4,}")


def needs_translation(text: str | None) -> bool:
    """True if a snippet is English-dominant OR contains an English prose run."""
    if not text:
        return False
    return is_english(text) or bool(_EN_PROSE_RUN.search(text))


def collect_snippets(doc: dict) -> list[tuple]:
    """Return [(path, text)] for every English-dominant natural-language field.

    ``path`` is a locator we patch back into: ("bluf",) | ("reasons", i, key) |
    ("risks", i, key).
    """
    out: list[tuple] = []
    if needs_translation(doc.get("bluf_thesis")):
        out.append((("bluf",), doc["bluf_thesis"]))
    for group in ("reasons", "risks"):
        items = doc.get(group) or []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for key in TEXT_KEYS:
                if needs_translation(item.get(key)):
                    out.append(((group, i, key), item[key]))
    return out


_TRANSLATOR = None
_MODEL_NAME = DEFAULT_MODEL

_SYSTEM = (
    "You are a professional financial translator for a Taiwanese stock-podcast "
    "platform. Translate each English snippet FULLY into Traditional Chinese (zh-TW) "
    "as written in Taiwan market commentary — leave NO English words in the output "
    "except ticker symbols (NVDA, 2330, TSM), company names already in Latin, numbers, "
    "and percentages, which you preserve exactly. Do not add, omit, merge, or reorder. "
    'Return ONLY JSON: {"translations": [...]} — an array with the SAME length and '
    "order as the input snippets."
)


def _get_translator():
    global _TRANSLATOR
    if _TRANSLATOR is None:
        import os as _os

        from langchain_google_genai import ChatGoogleGenerativeAI

        _TRANSLATOR = ChatGoogleGenerativeAI(
            model=_MODEL_NAME, temperature=0.0, google_api_key=_os.getenv("GOOGLE_API_KEY")
        )
    return _TRANSLATOR


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text


def translate(snippets: list[str]) -> list[str]:
    """Translate English finance snippets → zh-TW, preserving order and length."""
    import json as _json

    model = _get_translator()
    user = _json.dumps({"snippets": snippets}, ensure_ascii=False)
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = model.invoke(messages, response_mime_type="application/json")
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            result = _json.loads(_strip_fences(raw), strict=False)
            out = result.get("translations")
            if not isinstance(out, list) or len(out) != len(snippets):
                raise ValueError(f"expected {len(snippets)} translations, got {len(out) if isinstance(out, list) else out!r}")
            out = [str(x) for x in out]
            # Guard against a non-translation: reject only if an output is still
            # English-DOMINANT (a fully translated zh-TW snippet may legitimately
            # retain an English product/term, so we don't fail on a mere word-run).
            still_en = [i for i, t in enumerate(out) if is_english(t)]
            if still_en:
                raise ValueError(f"snippets {still_en} came back still English")
            return out
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise ValueError(f"translation failed after {_MAX_RETRIES} attempts: {last_err}")


def apply_patches(doc: dict, paths: list[tuple], values: list[str]) -> dict:
    """Build a Firestore update dict from translated values, mutating copies."""
    update: dict = {}
    reasons = [dict(r) for r in (doc.get("reasons") or [])]
    risks = [dict(r) for r in (doc.get("risks") or [])]
    touched_reasons = touched_risks = False
    for path, value in zip(paths, values):
        if path == ("bluf",):
            update["bluf_thesis"] = value
        elif path[0] == "reasons":
            reasons[path[1]][path[2]] = value
            touched_reasons = True
        elif path[0] == "risks":
            risks[path[1]][path[2]] = value
            touched_risks = True
    if touched_reasons:
        update["reasons"] = reasons
    if touched_risks:
        update["risks"] = risks
    return update


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--podcast", default="財經一路發", help="podcaster to scope (uses the tickers.podcaster index)")
    ap.add_argument("--apply", action="store_true", help="write translations (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="cap docs processed (0 = all)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"translation model (default {DEFAULT_MODEL})")
    args = ap.parse_args()
    dry = not args.apply
    global _MODEL_NAME
    _MODEL_NAME = args.model

    fb = FirebaseService()
    query = fb.db.collection_group(INSIGHTS_SUBCOLLECTION).where("podcaster", "==", args.podcast)

    # Materialize the full result set BEFORE mutating — updating docs while the
    # collection-group stream cursor is still open truncates the iteration.
    snaps = list(query.stream())
    print(f"fetched {len(snaps)} docs for {args.podcast}")

    scanned = matched = translated = failed = 0
    for snap in snaps:
        scanned += 1
        doc = snap.to_dict() or {}
        if doc.get("schema_version") not in SUPPORTED_SCHEMA:
            continue
        snippets = collect_snippets(doc)
        if not snippets:
            continue
        matched += 1
        paths = [p for p, _ in snippets]
        texts = [t for _, t in snippets]

        if dry:
            if matched <= 6:
                print(f"\n[{doc.get('ticker')}] {snap.reference.path}")
                print(f"   EN: {texts[0][:90]}")
            if args.limit and matched >= args.limit:
                break
            continue

        try:
            zh = translate(texts)
            update = apply_patches(doc, paths, zh)
            snap.reference.update(update)
            translated += 1
            if translated <= 5 or translated % 50 == 0:
                print(f"  ✓ {translated} {doc.get('ticker')}: {zh[0][:60]}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {doc.get('ticker')} {snap.reference.path}: {e}")
            time.sleep(1)
        if args.limit and translated >= args.limit:
            break

    print(f"\nscanned={scanned} matched(english)={matched} translated={translated} failed={failed}")
    if dry:
        print("DRY-RUN — nothing written. Re-run with --apply to translate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
