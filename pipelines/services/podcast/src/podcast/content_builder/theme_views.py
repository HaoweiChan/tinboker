"""Transcript-grounded theme extraction and deterministic output validation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

CANON = {  # synonym -> (label, exposure_id)
    **{k: ("記憶體", None) for k in ("記憶體", "記憶體與儲存族群", "記憶體與儲存", "記憶體漲價", "記憶體漲價循環", "記憶體缺貨漲價", "記憶體超級循環", "存儲")},
    **{k: ("被動元件", "sector_mlcc") for k in ("被動元件 MLCC", "被動元件", "鋁價與鋁電解電容", "被動元件與功率元件漲價", "被動跟功率", "日本被動元件")},
    **{k: ("光通訊", None) for k in ("光通訊", "高速光模組")},
    **{k: ("Google TPU 供應鏈", None) for k in ("Google 供應鏈", "Google TPU 供應鏈", "TPU 供應鏈", "Google AI 與 TPU")},
    **{k: ("AWS 供應鏈", None) for k in ("AWS 供應鏈", "AWS Chain")},
    **{k: ("企業 SaaS", "sector_saas") for k in ("軟體", "軟體股")},
    **{k: ("晶圓廠廠務", None) for k in ("廠務", "廠務與設廠材料", "晶圓廠廠務工程")},
    **{k: ("LPU 與 SRAM", None) for k in ("LPU 概念", "LPU 與 SRAM 概念", "類SRAM記憶體")},
    **{k: ("AI 算力需求", None) for k in ("AI 算力", "AI 算力需求")},
    "CPU": ("CPU 與 Agentic AI", "sector_cpu_agentic_ai"), "AI agent": ("CPU 與 Agentic AI", "sector_cpu_agentic_ai"),
    "散熱": ("液冷散熱", "sector_liquid_cooling"),
}

# Canonical names retain the same identity even without a taxonomy cache.
for _label, _exposure in tuple(CANON.values()):
    CANON.setdefault(_label, (_label, _exposure))


def build_episode_input(
    episode_id: str, transcript: dict[str, Any], summary: str, *, podcaster: str = "",
) -> tuple[str, set[int], set[tuple[str, str]], str]:
    """Group eight sentences per timestamp, retaining only summary ticker anchors."""
    anchors = list(dict.fromkeys(re.findall(r"\[([^\]]+)\]\(#ticker:([^\s)]+)\)", summary)))
    sentences = transcript.get("sentences") or []
    if not sentences:
        raise ValueError("timestamped transcript sentences are required")
    lines: list[str] = []
    starts: set[int] = set()
    for offset in range(0, len(sentences), 8):
        group = sentences[offset:offset + 8]
        start = group[0]["start"]
        if type(start) is not int or start < 0:
            raise ValueError("transcript start must be integer milliseconds")
        starts.add(start)
        lines.append(f"[{start}] " + " ".join(sentence["content"] for sentence in group))
    text = " ".join(sentence["content"] for sentence in sentences)
    companies = "\n".join(f"- {name} -> {ticker}" for name, ticker in anchors)
    prompt = f"EPISODE {episode_id} | {podcaster}\nLINKABLE COMPANIES\n{companies}\n\nTRANSCRIPT\n"
    return prompt + "\n".join(lines), starts, set(anchors), text


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def validate_theme_views(
    data: dict[str, Any], episode_id: str, starts: set[int],
    anchors: set[tuple[str, str]], transcript_text: str, taxonomy: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reject bad schemas; remove unsupported timestamps, quotes, and company links."""
    if set(data) != {"episode_id", "theme_views"} or data["episode_id"] != episode_id:
        raise ValueError("invalid episode schema or episode id")
    views = data["theme_views"]
    if not isinstance(views, list) or len(views) > 3:
        raise ValueError("theme_views must be a list with at most 3 views")
    names: dict[str, set[str]] = {}
    for theme in taxonomy:
        if not theme.get("exposure_id"):
            continue
        for name in [theme.get("display_zh"), theme.get("display_name"), *(theme.get("aliases") or [])]:
            if name:
                names.setdefault(_normalize(name), set()).add(theme["exposure_id"])
    keys = {"theme_label", "stance", "conviction", "thesis", "start_ms", "tickers", "quote"}
    result = []
    for raw in views:
        if not isinstance(raw, dict) or set(raw) != keys:
            raise ValueError("invalid theme view keys")
        if raw["stance"] not in ("bullish", "bearish", "mixed") or raw["conviction"] not in ("firm", "tentative"):
            raise ValueError("invalid stance or conviction")
        if not all(isinstance(raw[key], str) and raw[key].strip() for key in ("theme_label", "thesis")):
            raise ValueError("theme_label and thesis must be nonempty strings")
        if not isinstance(raw["tickers"], list):
            raise ValueError("tickers must be a list")
        view = dict(raw)
        start = view["start_ms"]
        if type(start) is not int or start not in starts:
            view["start_ms"] = None
        quote = view["quote"]
        if not isinstance(quote, str) or not quote.strip() or re.sub(r"\s+", "", quote) not in re.sub(r"\s+", "", transcript_text):
            view["quote"] = None
        view["tickers"] = [
            {key: ticker[key] for key in ("ticker", "name", "role")}
            for ticker in view["tickers"]
            if isinstance(ticker, dict)
            and isinstance(ticker.get("name"), str) and isinstance(ticker.get("ticker"), str)
            and (ticker["name"], ticker["ticker"]) in anchors
            and ticker.get("role") in ("beneficiary", "context")
        ][:20]
        matches = names.get(_normalize(view["theme_label"]), set())
        exposure = next(iter(matches)) if len(matches) == 1 else None
        view["theme_label"], view["exposure_id"] = CANON.get(view["theme_label"], (view["theme_label"], exposure))
        view["thesis"] = view["thesis"][:400]
        view["quote"] = view["quote"][:200] if view["quote"] else None
        result.append(view)
    return result
