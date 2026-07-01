#!/usr/bin/env python3
"""Regenerate SECTORS_SEED from the tide-tw-data curation (TW-only).

tide-tw-data is a 2-level, Taiwan-only taxonomy:
  sector_groups.json : 10 top-level groups -> ~112 sub-industry names
  latest.json        : each sub-industry -> its TW constituent tickers (+ money-flow)
  stock_names.json   : ticker -> zh name

We map it onto our existing sector system (`backend/src/data/sectors_seed.py`):
  * 10 groups        -> exposure_type='industry'  (the /topics 產業 tab)
  * real sub-industries -> exposure_type='theme'  (the /topics 題材 tab)
    (dropping every '・其他' residual bucket + generic catch-alls)

US tickers are intentionally dropped — a separate US topics tab handles them.

Display metadata (slug / icon / colour / aliases / per-ticker reasons) is NOT in
tide, so we reuse it from the current seed by concept-matching, and fall back to
per-group defaults for genuinely new themes. Members are capped to a handful of
"leaders" (current-curated tickers first, then tide's own order) so the board /
cards stay the same size as today.

Run:  python build_sectors_seed_from_tide.py [--tide DIR] [--write]
Without --write it prints a summary and diff stats only.

# ponytail: one-shot generator; tide-tw-data is gitignored so we commit the
# generated .py, not this input. Re-run when tide updates the curation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pprint
import sys
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BACKEND_SEED = REPO / "backend/src/data/sectors_seed.py"
PIPELINE_SEED = REPO / "pipelines/libs/shared/src/shared/sectors_seed_backup.py"
REASONS_JSON = REPO / "backend/src/data/sector_reasons.json"

LEADERS_CAP = 15  # members kept per sector for display / board perf

# Sub-industries we never surface as a theme (residual dumps, not investable themes).
DROP_THEME = {"其他產業"}
DROP_THEME_SUFFIX = "・其他"

# Groups whose sole sub-industry == the group itself -> industry only, no dup theme.
SINGLE_SUB_GROUPS = {"生技醫療", "營建地產"}

# --- 10 top-level groups -> industry metadata (icons reused from current seed,
#     so they are guaranteed present in the frontend ICON_REGISTRY). -------------
GROUP_META = {
    "半導體":       ("sector_semiconductor",        "cpu",           "#3B82F6",
                     ["半導體", "晶片", "晶圓", "護國神山", "semiconductor", "chip", "chips"]),
    "AI與電子硬體":  ("sector_ai_hardware",           "circuit-board", "#10B981",
                     ["電子硬體", "AI 硬體", "電子零組件", "electronics hardware", "ai hardware"]),
    "軟體雲端資安":  ("sector_software_cloud",        "code-2",        "#6366F1",
                     ["軟體", "雲端", "資安", "software", "cloud", "cybersecurity", "saas"]),
    "綠能與電力":    ("sector_green_energy",          "plug-zap",      "#22C55E",
                     ["綠能", "電力", "能源", "再生能源", "green energy", "power", "renewables"]),
    "金融":         ("sector_financials",            "landmark",      "#F59E0B",
                     ["金融", "金融股", "金控", "銀行", "壽險", "financials", "banks"]),
    "航運物流":      ("sector_shipping_logistics",    "ship",          "#14B8A6",
                     ["航運", "物流", "貨櫃", "散裝", "shipping", "logistics"]),
    "傳產製造":      ("sector_manufacturing",         "factory",       "#94A3B8",
                     ["傳產", "製造", "工業", "傳統產業", "manufacturing", "industrials"]),
    "民生消費":      ("sector_consumer",              "shopping-cart", "#C026D3",
                     ["民生", "消費", "內需", "零售", "consumer", "retail"]),
    "營建地產":      ("sector_construction_realestate", "building",     "#B45309",
                     ["營建", "地產", "建設", "房地產", "construction", "real estate"]),
    "生技醫療":      ("sector_biotech_medical",       "heart-pulse",   "#16A34A",
                     ["生技", "醫療", "生醫", "製藥", "新藥", "biotech", "healthcare", "pharma"]),
}

# Readable slug + extra english aliases for the standout *new* themes tide adds
# that don't map onto a current sector. Everything else falls back to the group
# icon/colour and a transliterated slug. Optional keys: icon, color.
THEME_OVERRIDE = {
    "PCB 載板":         {"slug": "sector_pcb_substrate", "aliases": ["PCB 載板", "ABF", "IC 載板", "載板", "substrate"]},
    "汽車工業・其他":   {"slug": "sector_auto", "display": "汽車", "aliases": ["汽車", "車用", "automotive", "auto"]},
    "AI 先進封裝":      {"slug": "sector_ai_adv_packaging", "aliases": ["先進封裝", "advanced packaging", "chiplet"]},
    "HBM 高頻寬記憶體": {"slug": "sector_hbm", "aliases": ["HBM", "高頻寬記憶體", "high bandwidth memory"]},
    "CXL 技術":         {"slug": "sector_cxl", "aliases": ["CXL", "compute express link"]},
    "客製 ASIC 矽智財": {"slug": "sector_asic_ip", "aliases": ["ASIC", "矽智財", "silicon ip", "custom asic"]},
    "CPU 與 Agentic AI": {"slug": "sector_cpu_agentic_ai", "aliases": ["Agentic AI", "AI agent", "代理式 AI"]},
    "HPC 與網通 IC":    {"slug": "sector_hpc_networking_ic", "aliases": ["HPC", "高效能運算", "網通 IC"]},
    "第三代半導體":     {"slug": "sector_wide_bandgap", "aliases": ["第三代半導體", "碳化矽", "氮化鎵", "SiC", "GaN"]},
    "記憶體模組":       {"slug": "sector_memory_module", "aliases": ["記憶體模組", "memory module"]},
    "顯示驅動 IC":      {"slug": "sector_display_driver_ic", "aliases": ["驅動 IC", "display driver", "DDIC"]},
    "IC 通路":          {"slug": "sector_ic_distribution", "aliases": ["IC 通路", "ic distribution"]},
    "AI 伺服器組裝":    {"slug": "sector_ai_server", "aliases": ["AI 伺服器", "ai server"]},
    "液冷散熱":         {"slug": "sector_liquid_cooling", "aliases": ["液冷", "散熱", "liquid cooling", "thermal"]},
    "氣冷與核心組件":   {"slug": "sector_air_cooling", "aliases": ["氣冷", "散熱風扇", "air cooling"]},
    "高速光模組":       {"slug": "sector_optical_module", "aliases": ["光模組", "optical module", "光收發"]},
    "矽光子與 CPO":     {"slug": "sector_silicon_photonics", "aliases": ["矽光子", "CPO", "silicon photonics"]},
    "AI 互連元件":      {"slug": "sector_ai_interconnect", "aliases": ["AI 互連", "interconnect"]},
    "車用連接器":       {"slug": "sector_auto_connector", "aliases": ["車用連接器", "automotive connector"]},
    "軟板":             {"slug": "sector_fpc", "aliases": ["軟板", "FPC", "flexible pcb"]},
    "PCB 硬板製造":     {"slug": "sector_pcb_rigid", "aliases": ["PCB", "印刷電路板", "硬板", "rigid pcb"]},
    "玻璃基板":         {"slug": "sector_glass_substrate", "aliases": ["玻璃基板", "glass substrate"]},
    "AI PC 筆電與平板": {"slug": "sector_ai_pc", "aliases": ["AI PC", "筆電", "平板", "notebook"]},
    "EMS 電子代工":     {"slug": "sector_ems", "aliases": ["EMS", "電子代工", "代工"]},
    "MicroLED 顯示供應鏈": {"slug": "sector_microled", "aliases": ["MicroLED", "Micro LED", "Mini LED"]},
    "光學鏡頭":         {"slug": "sector_optical_lens", "aliases": ["光學鏡頭", "鏡頭", "optical lens"]},
    "AR VR XR 光學":    {"slug": "sector_ar_vr_optics", "aliases": ["AR", "VR", "XR", "元宇宙", "ar/vr"]},
    "Edge AI AIoT":     {"slug": "sector_edge_ai", "aliases": ["Edge AI", "AIoT", "邊緣運算"]},
    "高速交換器與無線網路": {"slug": "sector_networking", "aliases": ["交換器", "網通", "switch", "networking"]},
    "低軌衛星":         {"slug": "sector_leo_satellite", "aliases": ["低軌衛星", "衛星", "LEO", "satellite"]},
    "石英頻率控制":     {"slug": "sector_crystal_osc", "aliases": ["石英元件", "頻率元件", "crystal oscillator"]},
    "雲端與 MSP":       {"slug": "sector_cloud_msp", "aliases": ["雲端", "MSP", "cloud", "資料中心"]},
    "企業 SaaS":        {"slug": "sector_saas", "aliases": ["SaaS", "企業軟體", "軟體服務", "enterprise software"]},
    "資安防護":         {"slug": "sector_cybersecurity", "aliases": ["資安", "資訊安全", "cybersecurity", "security"]},
    "離岸風電":         {"slug": "sector_offshore_wind", "aliases": ["離岸風電", "風電", "offshore wind"]},
    "太陽能產業":       {"slug": "sector_solar", "aliases": ["太陽能", "光電", "solar", "photovoltaic"]},
    "儲能系統整合":     {"slug": "sector_energy_storage", "aliases": ["儲能", "energy storage", "ESS"]},
    "電池關鍵材料":     {"slug": "sector_battery_materials", "aliases": ["電池材料", "battery materials", "正極材料"]},
    "電芯製造與電池模組": {"slug": "sector_battery_cell", "aliases": ["電芯", "電池模組", "battery cell"]},
    "BBU 電池備援":     {"slug": "sector_bbu", "aliases": ["BBU", "電池備援", "backup battery"]},
    "電源供應器":       {"slug": "sector_power_supply", "aliases": ["電源供應器", "power supply", "PSU"]},
    "工業自動化":       {"slug": "sector_industrial_automation", "aliases": ["工業自動化", "自動化", "automation", "機器人"]},
    "CNC 工具機":       {"slug": "sector_machine_tools", "aliases": ["工具機", "CNC", "machine tools"]},
    "精密機構件":       {"slug": "sector_precision_parts", "aliases": ["機構件", "精密機械", "precision parts"]},
    "國防軍工":         {"slug": "sector_defense", "aliases": ["國防", "軍工", "航太", "defense", "aerospace"]},
    "被動元件 MLCC":    {"slug": "sector_mlcc", "aliases": ["被動元件", "MLCC", "passive components"]},
    "IC 測試服務":      {"slug": "sector_ic_testing", "aliases": ["IC 測試", "測試服務", "ic testing"]},
    "封測代工":         {"slug": "sector_ospat", "aliases": ["封測", "封裝測試", "OSAT", "封測代工"]},
    "類比與功率 IC":    {"slug": "sector_analog_power_ic", "aliases": ["類比 IC", "功率 IC", "analog", "power ic"]},
    "NOR Flash 利基記憶體": {"slug": "sector_nor_flash", "aliases": ["NOR Flash", "利基記憶體", "niche memory"]},
    "矽晶圓":           {"slug": "sector_silicon_wafer", "aliases": ["矽晶圓", "silicon wafer"]},
    "晶圓代工":         {"slug": "sector_foundry", "aliases": ["晶圓代工", "foundry"]},
    "晶圓廠設備":       {"slug": "sector_fab_equipment", "aliases": ["半導體設備", "晶圓設備", "fab equipment"]},
    "前段製程材料":     {"slug": "sector_front_end_materials", "aliases": ["製程材料", "前段材料", "process materials"]},
    "前段製程設備":     {"slug": "sector_front_end_equipment", "aliases": ["前段設備", "front-end equipment"]},
    "封裝量測自動化":   {"slug": "sector_pkg_metrology", "aliases": ["量測", "檢測", "metrology", "inspection"]},
    "封裝製程機台":     {"slug": "sector_pkg_equipment", "aliases": ["封裝設備", "packaging equipment"]},
    "導線架與化學品":   {"slug": "sector_leadframe", "aliases": ["導線架", "leadframe", "化學品"]},
    "功率電感":         {"slug": "sector_power_inductor", "aliases": ["電感", "功率電感", "inductor"]},
    "電容器":           {"slug": "sector_capacitor", "aliases": ["電容", "電容器", "capacitor"]},
    "電阻與被動保護":   {"slug": "sector_resistor", "aliases": ["電阻", "被動保護", "resistor"]},
    "連接器 工業消費":  {"slug": "sector_connector", "aliases": ["連接器", "connector"]},
    "玻纖布":           {"slug": "sector_glass_fiber", "aliases": ["玻纖布", "玻璃纖維", "glass fiber"]},
    "智慧型手機":       {"slug": "sector_smartphone", "aliases": ["智慧型手機", "手機", "smartphone"]},
    "整合與委外":       {"slug": "sector_odm", "aliases": ["ODM", "委外", "整合"]},
    "機殼與滑軌":       {"slug": "sector_chassis", "aliases": ["機殼", "滑軌", "chassis", "rail"]},
    "面板產業":         {"slug": "sector_display_panel", "aliases": ["面板", "顯示器", "display", "panel"]},
    "光感測與元件":     {"slug": "sector_optical_sensing", "aliases": ["光感測", "感測元件", "optical sensor"]},
    "日本前段設備":     {"slug": "sector_jp_front_end_equip", "aliases": ["日本設備", "japan equipment"]},
    "日本後段設備":     {"slug": "sector_jp_back_end_equip", "aliases": ["日本後段設備"]},
    "日本矽晶圓":       {"slug": "sector_jp_wafer", "aliases": ["日本矽晶圓"]},
    "日本被動元件":     {"slug": "sector_jp_passive", "aliases": ["日本被動元件"]},
    "電器電纜":         {"slug": "sector_wire_cable", "aliases": ["電線電纜", "電纜", "wire", "cable"]},
    "資源環保工業":     {"slug": "sector_environmental", "aliases": ["環保", "資源回收", "environmental"]},
    "油電燃氣":         {"slug": "sector_oil_gas", "aliases": ["油電", "燃氣", "天然氣", "oil & gas"]},
    "銀行金融":         {"slug": "sector_banks", "aliases": ["銀行", "金控", "banks"]},
    "貨櫃航運":         {"slug": "sector_container_shipping", "aliases": ["貨櫃航運", "container shipping"]},
    "散裝航運":         {"slug": "sector_bulk_shipping", "aliases": ["散裝航運", "bulk shipping"]},
    "石化與塑膠產業":   {"slug": "sector_petrochemical", "aliases": ["石化", "塑膠", "petrochemical", "plastics"]},
    "橡膠":             {"slug": "sector_rubber", "aliases": ["橡膠", "輪胎", "rubber"]},
    "水泥":             {"slug": "sector_cement", "aliases": ["水泥", "cement"]},
    "玻璃陶瓷":         {"slug": "sector_glass_ceramics", "aliases": ["玻璃", "陶瓷", "glass", "ceramics"]},
    "紡織成衣":         {"slug": "sector_textile", "aliases": ["紡織", "成衣", "textile", "garment"]},
    "造紙":             {"slug": "sector_paper", "aliases": ["造紙", "紙業", "paper"]},
    "鋼鐵金屬":         {"slug": "sector_steel_metals", "aliases": ["鋼鐵", "金屬", "steel", "metals"]},
    "電商零售":         {"slug": "sector_ecommerce", "aliases": ["電商", "零售", "ecommerce", "retail"]},
    "居家生活":         {"slug": "sector_home_living", "aliases": ["居家", "家居", "home living"]},
    "文化創意":         {"slug": "sector_culture_creative", "aliases": ["文創", "文化創意", "遊戲", "media"]},
    "觀光餐旅":         {"slug": "sector_tourism", "aliases": ["觀光", "旅遊", "餐飲", "飯店", "tourism", "hospitality"]},
    "貿易百貨":         {"slug": "sector_retail_dept", "aliases": ["貿易", "百貨", "通路", "department store"]},
    "農業科技":         {"slug": "sector_agritech", "aliases": ["農業", "農業科技", "agritech"]},
    "運動休閒":         {"slug": "sector_sports_leisure", "aliases": ["運動", "休閒", "自行車", "sports", "leisure"]},
    "食品飲料":         {"slug": "sector_food_beverage", "aliases": ["食品", "飲料", "food", "beverage"]},
}
# '汽車工業・其他' is the only '・其他' we keep (there is no cleaner 汽車 theme in tide).
KEEP_DESPITE_SUFFIX = {"汽車工業・其他"}

# Nicer per-theme icons so the 題材 tab isn't 93 clones of the group icon.
# All values are icon_ids already used by the current seed -> guaranteed to exist
# in the frontend ICON_REGISTRY.
ICON_BY_SLUG = {
    "sector_hbm": "memory-stick", "sector_memory_module": "memory-stick", "sector_nor_flash": "memory-stick",
    "sector_liquid_cooling": "droplets", "sector_air_cooling": "wind",
    "sector_solar": "sun", "sector_offshore_wind": "wind", "sector_energy_storage": "battery-charging",
    "sector_battery_cell": "battery-charging", "sector_battery_materials": "battery-charging", "sector_bbu": "battery-charging",
    "sector_leo_satellite": "satellite", "sector_cybersecurity": "shield", "sector_saas": "code", "sector_cloud_msp": "network",
    "sector_networking": "network", "sector_optical_module": "radio", "sector_silicon_photonics": "radio",
    "sector_connector": "cable", "sector_auto_connector": "cable", "sector_ai_interconnect": "cable",
    "sector_pcb_substrate": "layers", "sector_pcb_rigid": "layers", "sector_fpc": "layers",
    "sector_foundry": "cpu", "sector_silicon_wafer": "cpu", "sector_fab_equipment": "wrench",
    "sector_front_end_equipment": "wrench", "sector_pkg_equipment": "wrench", "sector_machine_tools": "wrench",
    "sector_industrial_automation": "bot", "sector_defense": "plane", "sector_auto": "car",
    "sector_display_panel": "monitor", "sector_microled": "lightbulb", "sector_ai_pc": "laptop",
    "sector_smartphone": "monitor", "sector_optical_lens": "radio", "sector_optical_sensing": "radio",
    "sector_petrochemical": "flame", "sector_oil_gas": "fuel", "sector_steel_metals": "factory",
    "sector_cement": "mountain", "sector_textile": "shirt", "sector_paper": "package", "sector_rubber": "package",
    "sector_food_beverage": "utensils", "sector_tourism": "plane", "sector_ecommerce": "shopping-cart",
    "sector_retail_dept": "store", "sector_banks": "landmark", "sector_container_shipping": "ship",
    "sector_bulk_shipping": "ship", "sector_wire_cable": "cable", "sector_power_supply": "plug",
    "sector_capacitor": "circuit-board", "sector_mlcc": "circuit-board", "sector_analog_power_ic": "cpu",
    "sector_asic_ip": "cpu", "sector_display_driver_ic": "cpu", "sector_ospat": "package",
}


def load_current_seed():
    spec = importlib.util.spec_from_file_location("cur_seed", BACKEND_SEED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SECTORS_SEED


def build_reuse_index(current):
    """ticker -> (reason, name_en) reused from current curated members (TW only)."""
    reason_by_ticker, name_en_by_ticker = {}, {}
    for sec in current:
        for mem in sec["members"]:
            if mem["market"] != "TW":
                continue
            t = mem["ticker"]
            if mem.get("reason") and t not in reason_by_ticker:
                reason_by_ticker[t] = mem["reason"]
            if mem.get("name_en") and t not in name_en_by_ticker:
                name_en_by_ticker[t] = mem["name_en"]
    return reason_by_ticker, name_en_by_ticker


def is_theme_sub(name: str) -> bool:
    if name in DROP_THEME:
        return False
    if name in KEEP_DESPITE_SUFFIX:
        return True
    if DROP_THEME_SUFFIX in name:
        return False
    return True


def make_member(ticker, names, reason_by_ticker, name_en_by_ticker):
    return {
        "ticker": ticker,
        "name": names.get(ticker, ticker),
        "name_en": name_en_by_ticker.get(ticker),
        "market": "TW",
        "source": "tide",
        "reason": reason_by_ticker.get(ticker, ""),
    }


def pick_leaders(stocks, curated_tw):
    """Current-curated tickers first (they are hand-picked leaders), then tide order."""
    seen, ordered = set(), []
    for t in stocks:
        if t in curated_tw and t not in seen:
            ordered.append(t); seen.add(t)
    for t in stocks:
        if t not in seen:
            ordered.append(t); seen.add(t)
    return ordered[:LEADERS_CAP]


def build(tide_dir: Path):
    groups = json.loads((tide_dir / "sector_groups.json").read_text(encoding="utf-8"))
    latest = json.loads((tide_dir / "latest.json").read_text(encoding="utf-8"))
    names = json.loads((tide_dir / "stock_names.json").read_text(encoding="utf-8"))
    sub_stocks = {s["name"]: s["stocks"] for s in latest["sectors"]}

    current = load_current_seed()
    reason_by_ticker, name_en_by_ticker = build_reuse_index(current)
    curated_tw = set(reason_by_ticker) | {
        m["ticker"] for s in current for m in s["members"] if m["market"] == "TW"
    }

    seed, used_slugs = [], set()

    # --- INDUSTRIES: 10 groups (members = union of their sub-industries' TW stocks)
    for group, subnames in groups.items():
        slug, icon, color, aliases = GROUP_META[group]
        used_slugs.add(slug)
        union = list(OrderedDict.fromkeys(
            t for sn in subnames for t in sub_stocks.get(sn, [])
        ))
        leaders = pick_leaders(union, curated_tw)
        seed.append({
            "exposure_id": slug,
            "exposure_type": "industry",
            "display_name": group,
            "icon_id": icon,
            "color_hex": color,
            "aliases": aliases,
            "members": [make_member(t, names, reason_by_ticker, name_en_by_ticker) for t in leaders],
        })

    # --- THEMES: real sub-industries (drop residual buckets + single-sub dups)
    for group, subnames in groups.items():
        if group in SINGLE_SUB_GROUPS:
            continue
        gslug, gicon, gcolor, _ = GROUP_META[group]
        for sn in subnames:
            if not is_theme_sub(sn):
                continue
            ov = THEME_OVERRIDE.get(sn, {})
            slug = ov.get("slug") or f"sector_{gslug.split('_', 1)[1]}_{_ascii_slug(sn)}"
            base = slug
            i = 2
            while slug in used_slugs:
                slug = f"{base}_{i}"; i += 1
            used_slugs.add(slug)
            stocks = sub_stocks.get(sn, [])
            leaders = pick_leaders(stocks, curated_tw)
            aliases = list(OrderedDict.fromkeys([sn] + ov.get("aliases", [])))
            seed.append({
                "exposure_id": slug,
                "exposure_type": "theme",
                "display_name": ov.get("display", sn),
                "icon_id": ov.get("icon") or ICON_BY_SLUG.get(slug, gicon),
                "color_hex": ov.get("color", gcolor),
                "aliases": aliases,
                "members": [make_member(t, names, reason_by_ticker, name_en_by_ticker) for t in leaders],
            })
    return seed


def _ascii_slug(name: str) -> str:
    """Fallback slug from any ASCII tokens in the name, else a stable hex tag."""
    ascii_tok = "".join(c if (c.isascii() and (c.isalnum() or c == " ")) else " " for c in name)
    toks = [t.lower() for t in ascii_tok.split() if t]
    if toks:
        return "_".join(toks)
    # deterministic, ASCII, unique-enough per group
    return format(abs(hash(name)) % 0xFFFFFF, "06x")


def emit(seed) -> str:
    n_ind = sum(1 for s in seed if s["exposure_type"] == "industry")
    n_thm = sum(1 for s in seed if s["exposure_type"] == "theme")
    header = (
        f'"""Database seed data for {len(seed)} TW sectors and themes '
        f'({n_ind} industries + {n_thm} themes).\n\n'
        'Generated from the tide-tw-data curation by\n'
        'pipelines/libs/shared/scripts/build_sectors_seed_from_tide.py — do not hand-edit;\n'
        're-run that script to regenerate. TW-only (US exposures live in a separate tab).\n'
        '"""\n\n'
    )
    return header + "SECTORS_SEED = " + pprint.pformat(seed, width=110, sort_dicts=False) + "\n"


def emit_reasons(seed) -> str:
    out = {}
    for s in seed:
        bucket = {m["ticker"]: m["reason"] for m in s["members"] if m.get("reason")}
        if bucket:
            out[s["exposure_id"]] = bucket
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tide", default=str(REPO / "tide-tw-data"), type=Path)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    seed = build(args.tide)
    src = emit(seed)
    reasons = emit_reasons(seed)

    n_ind = sum(1 for s in seed if s["exposure_type"] == "industry")
    n_thm = sum(1 for s in seed if s["exposure_type"] == "theme")
    all_tickers = {m["ticker"] for s in seed for m in s["members"]}
    us = [m["ticker"] for s in seed for m in s["members"] if m["market"] != "TW"]
    empty = [s["exposure_id"] for s in seed if not s["members"]]
    with_reason = sum(1 for s in seed for m in s["members"] if m.get("reason"))
    total_members = sum(len(s["members"]) for s in seed)

    print(f"sectors: {len(seed)}  ({n_ind} industries + {n_thm} themes)")
    print(f"unique tickers surfaced: {len(all_tickers)}  members total: {total_members}")
    print(f"US members (must be 0): {len(us)}")
    print(f"empty sectors (must be 0): {empty}")
    print(f"members carrying a reused reason: {with_reason}")
    assert not us, "US tickers leaked into the TW seed"
    assert not empty, f"empty sectors: {empty}"

    if args.write:
        BACKEND_SEED.write_text(src, encoding="utf-8")
        PIPELINE_SEED.write_text(src, encoding="utf-8")
        REASONS_JSON.write_text(reasons, encoding="utf-8")
        print(f"\nwrote {BACKEND_SEED}")
        print(f"wrote {PIPELINE_SEED}")
        print(f"wrote {REASONS_JSON}")
    else:
        print("\n(dry run — pass --write to update the seed files)")


if __name__ == "__main__":
    sys.exit(main())
