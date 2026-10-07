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
    # Added 2026-10 from the labels eight more shows actually produced.
    **{k: ("記憶體", None) for k in ("記憶體存儲", "記憶體存儲產業", "記憶體族群", "記憶體股", "記憶體類股", "記憶體與存儲", "記憶體跟存儲", "AI記憶體")},
    **{k: ("NAND Flash", None) for k in ("NAND Flash 儲存需求",)},
    "利基型記憶體": ("NOR Flash 利基記憶體", "sector_nor_flash"),
    "高速網通與光通訊": ("光通訊", None),
    **{k: ("AI 基礎建設", None) for k in ("AI Infra", "AI 基礎建設概念股", "AI 基礎設施")},
    "AI 相關硬體": ("AI 硬體", None),
    **{k: ("AI 資本支出", None) for k in ("大型科技股資本支出", "雲端巨頭資本支出", "科技巨頭資本支出與供應鏈")},
    **{k: ("科技巨頭", None) for k in ("AI 巨頭", "AI 和科技巨頭", "AI 大型科技股", "AI雲端巨頭", "雲端巨頭", "四大雲端業者")},
    **{k: ("AI", None) for k in ("AI 概念股", "AI 類股", "AI 產業", "科技跟AI股")},
    "AI相關供應鏈": ("AI 供應鏈", None),
    **{k: ("台積電供應鏈", None) for k in ("臺積電供應鏈", "泛台積電概念股", "台積電關係企業")},
    **{k: ("晶圓廠廠務", None) for k in ("廠務工程", "廠務工程與設備")},
    **{k: ("探針卡", None) for k in ("探針", "探針族群", "探針卡與測試介面")},
    "摺疊機": ("摺疊手機", None), "特化族群": ("特化", None), "稀土概念股": ("稀土供應鏈", None),
    "IPC/IPD 矽電容": ("矽電容", None), "虛擬貨幣": ("加密貨幣", None), "開放權重模型": ("開源模型", None),
    **{k: ("漲價概念股", None) for k in ("報價概念股", "報價漲價股")},
    **{k: ("自動駕駛", None) for k in ("RoboTaxi", "無人自動駕駛計程車")},
    "老AI族群": ("老AI", None), "設備族群": ("設備股", None),
    **{k: ("電力設備", None) for k in ("電力基建", "AI 資料中心電力", "資料中心的電網升級鏈", "電力與資料中心設備", "電力設備與資料中心電力")},
    **{k: ("NeoCloud", None) for k in ("新型雲端服務商", "算力租賃", "賣算力")},
    **{k: ("穿戴裝置", None) for k in ("AI穿戴裝置", "穿戴型裝置")},
    **{k: ("半導體", None) for k in ("晶片股", "半導體供應鏈")},
    **{k: ("PCB 載板", "sector_pcb_substrate") for k in ("ABF 載板", "ABF 載板與上游銅箔材料")},
    "PCB 產業": ("PCB 硬板製造", "sector_pcb_rigid"),
    "AI 伺服器代工廠": ("AI 伺服器組裝", "sector_ai_server"),
    "應用軟體": ("企業 SaaS", "sector_saas"),
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


_CANON_NORM = {_normalize(key): value for key, value in CANON.items()}


def canonical_theme(label: str, taxonomy: list[dict[str, Any]]) -> tuple[str, str | None]:
    """One identity per theme: a synonym's canonical name, else the taxonomy's own display
    name when the label (or an alias) matches exactly one theme, else the label as given.

    Spacing and width are ignored, so 「AI算力」 and 「AI 算力」 are the same label.
    """
    canon = _CANON_NORM.get(_normalize(label))
    if canon:
        return canon
    matches: dict[str, str] = {}
    for theme in taxonomy:
        if not theme.get("exposure_id"):
            continue
        names = [theme.get("display_zh"), theme.get("display_name"), *(theme.get("aliases") or [])]
        if any(name and _normalize(name) == _normalize(label) for name in names):
            matches[theme["exposure_id"]] = theme.get("display_zh") or label
    if len(matches) == 1:
        exposure, display = next(iter(matches.items()))
        return display, exposure
    return label, None


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
        view["theme_label"], view["exposure_id"] = canonical_theme(view["theme_label"], taxonomy)
        view["thesis"] = view["thesis"][:400]
        view["quote"] = view["quote"][:200] if view["quote"] else None
        result.append(view)
    return result
