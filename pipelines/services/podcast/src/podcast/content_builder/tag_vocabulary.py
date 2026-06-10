"""Canonical tag vocabulary: ASCII slug (the clustering join key) → zh-TW display.

**Extraction-side vocabulary.** Injected into the writer prompt so the LLM maps
concepts to KNOWN slugs instead of inventing per-episode phrasings. Extraction
lowercases slugs (``#tag:Semiconductor`` → ``semiconductor``); ``display_for``
is case-insensitive.

The **display-side gate** lives in ``backend/src/tag_registry.py`` (DB-backed,
managed via the admin UI at ``/admin/tags``). It decides which extracted tags
appear in trending vs. are hidden. When adding a new slug here, also add it to
the backend registry so it can surface on the website.

Grow this list as the catalogue expands. A slug not listed here still works (it
just has no curated zh-TW display yet) — prefer adding it here over inventing
variants. Free-text Chinese tags fragment clustering (美股 vs 美國股市 vs 美股大盤,
半導體 vs 晶片, …); a controlled slug vocabulary avoids that.
"""

from __future__ import annotations

# slug -> zh-TW display name. Slugs are ASCII [A-Za-z0-9_]; the join key is lowercased.
TAG_DISPLAY: dict[str, str] = {
    "AI": "AI",
    "AgenticAI": "代理型 AI",
    "LLM": "大型語言模型",
    "Semiconductor": "半導體",
    "Memory": "記憶體",
    "GPU": "GPU",
    "DataCenter": "資料中心",
    "CloudComputing": "雲端運算",
    "SupplyChain": "供應鏈",
    "EV": "電動車",
    "Software": "軟體",
    "Cybersecurity": "資安",
    "Biotech": "生技醫療",
    "Energy": "能源",
    "Finance": "金融",
    "RealEstate": "房地產",
    "Crypto": "加密貨幣",
    "USStocks": "美股",
    "TWStocks": "台股",
    "HKStocks": "港股",
    "JPStocks": "日股",
    "Macroeconomy": "總體經濟",
    "FedRate": "聯準會利率",
    "Inflation": "通膨",
    "MarketCorrection": "股市修正",
    "Earnings": "財報",
    "IPO": "首次公開發行",
    "MergersAcquisitions": "併購",
    "Geopolitics": "地緣政治",
}

# Lowercased-slug -> display, for case-insensitive lookup against extracted tags.
_DISPLAY_BY_LOWER = {slug.lower(): zh for slug, zh in TAG_DISPLAY.items()}


def display_for(slug: str) -> str:
    """zh-TW display for a (possibly lowercased) tag slug; the slug itself if unknown."""
    return _DISPLAY_BY_LOWER.get((slug or "").lower(), slug)


def vocabulary_prompt_block() -> str:
    """Render the vocabulary as ``Slug = 顯示名`` lines for the writer prompt."""
    return "\n".join(f"  - {slug} = {zh}" for slug, zh in TAG_DISPLAY.items())
