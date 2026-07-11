# Sector Universe Data-Quality Audit

**Source:** `backend/src/data/sectors_seed.py` (103 sectors, 1413 member entries, 977 unique tickers)
**Method:** Mechanical metrics computed by `audit_sectors.py` (Part 1). Membership/naming/taxonomy judgment by market knowledge (Part 2). Every table below marks **VERIFIED** (computed or read from the seed) vs **INFERRED** (market judgment).
**Context:** The current fix plan patched one bad membership (2330 in `sector_hbm`) and four `jp_*` names. This audit finds those are two instances of two systemic classes of defect, not isolated bugs.

---

## Headline

| Metric | Value | VERIFIED |
|---|---|---|
| Sectors | 103 (10 industry + 93 theme) | ✓ |
| Total member entries | 1413 | ✓ |
| Unique tickers | 977 | ✓ |
| Member count min / median / max | 3 / 12 / 51 | ✓ |
| **Empty `reason` fields** | **1026 / 1413 (73%)** | ✓ |
| Distinct (ticker, reason) strings reused across ≥2 sectors | 85, spanning 279 member entries (20% of all rows) | ✓ |
| Sector pairs with Jaccard ≥ 0.5 | 17 | ✓ |
| Sector pairs where smaller ⊆ 90%+ of larger | 18 | ✓ |
| Region-prefixed display names | 4 (all `jp_*`) | ✓ |

Two systemic defects dominate:
1. **Reason-reuse over-tagging** — one company gets one generic `reason` string, then that (ticker, reason) is pasted into every loosely-related theme. This is the mechanism that put 2330 in HBM, and it inflates fan-out and pollutes ~20% of rows.
2. **Industry = its own flagship theme** — 6 of the 10 industries are ≥83% identical to one child theme (financials≈banks, software_cloud≈cloud_msp, consumer≈ecommerce, shipping≈container_shipping, manufacturing≈industrial_automation, green_energy≈offshore_wind). The two-level hierarchy is largely fictional.

---

# PART 1 — MECHANICAL METRICS (all VERIFIED)

## 1a. Member counts — outliers

**Sectors with <4 members** (too thin to sustain a page):

| # | sector_id | display | note |
|---|---|---|---|
| 3 | `sector_jp_back_end_equip` | 日本後段設備 | fully ⊆ `pkg_metrology`/`pkg_equipment` |
| 3 | `sector_jp_front_end_equip` | 日本前段設備 | fully ⊆ `fab_equipment`/`front_end_equipment` |

Also borderline at exactly 4: `sector_front_end_equipment`, `sector_agritech`, `sector_glass_ceramics`.

**Sectors with >40 members** (bloated, likely a whole TWSE industry code dumped in):

| # | sector_id | display |
|---|---|---|
| 51 | `sector_textile` | 紡織成衣 |
| 47 | `sector_steel_metals` | 鋼鐵金屬 |
| 47 | `sector_tourism` | 觀光餐旅 |

These three are the raw TWSE industry rosters (紡織/鋼鐵/觀光), not curated themes — they have no thesis, they're just "every listed company in the group."

## 1b. Ticker fan-out distribution

| in N sectors | # tickers |
|---|---|
| 1 | 768 |
| 2 | 114 |
| 3 | 38 |
| 4 | 23 |
| 5 | 13 |
| 6 | 13 |
| 7 | 2 |
| 8 | 3 |
| 9 | 1 |
| 10 | 1 |
| 11 | 1 |

79% of tickers sit in exactly one sector (healthy). The tail (fan-out ≥6, 19 tickers) is where over-tagging concentrates.

**Top 20 tickers by sector count** (the 2330-type suspects):

| fan-out | ticker | name | sectors (VERIFIED list) |
|---|---|---|---|
| 11 | 3017 | 奇鋐 | ai_hardware, ai_pc, ai_server, air_cooling, bbu, chassis, industrial_automation, liquid_cooling, manufacturing, pkg_metrology, power_supply |
| 10 | 3680 | 家登 | ai_adv_packaging, fab_equipment, front_end_equipment, ic_testing, jp_back_end_equip, jp_front_end_equip, ospat, pkg_equipment, pkg_metrology, precision_parts |
| 9 | 6271 | 同欣電 | analog_power_ic, ar_vr_optics, connector, crystal_osc, ic_testing, optical_lens, optical_sensing, ospat, resistor |
| 8 | 6669 | 緯穎 | ai_hardware, ai_interconnect, ai_server, cloud_msp, edge_ai, odm, saas, software_cloud |
| 8 | 3563 | 牧德 | fab_equipment, front_end_equipment, industrial_automation, machine_tools, manufacturing, pkg_equipment, pkg_metrology, precision_parts |
| 8 | 3131 | 弘塑 | ai_adv_packaging, fab_equipment, front_end_equipment, ic_testing, jp_back_end_equip, jp_front_end_equip, pkg_equipment, pkg_metrology |
| 7 | 2382 | 廣達 | ai_hardware, ai_pc, ai_server, cloud_msp, ems, odm, software_cloud |
| 7 | 2454 | 聯發科 | ai_pc, asic_ip, cpu_agentic_ai, cxl, edge_ai, hpc_networking_ic, silicon_photonics |
| 6 | 3105 | 穩懋 | jp_wafer, optical_sensing, semiconductor, silicon_photonics, silicon_wafer, wide_bandgap |
| 6 | 3035 | 智原 | asic_ip, cpu_agentic_ai, cxl, foundry, hpc_networking_ic, semiconductor |
| 6 | 6515 | 穎崴 | cpu_agentic_ai, cxl, edge_ai, foundry, hbm, semiconductor |
| 6 | 4938 | 和碩 | ai_hardware, ai_pc, ai_server, ems, odm, smartphone |
| 6 | 2356 | 英業達 | ai_hardware, ai_pc, ai_server, ems, odm, smartphone |
| 6 | 1519 | 華城 | energy_storage, environmental, green_energy, offshore_wind, power_supply, wire_cable |
| 6 | 1503 | 士電 | battery_materials, energy_storage, environmental, green_energy, offshore_wind, wire_cable |
| 6 | 3576 | 聯合再生 | battery_cell, battery_materials, energy_storage, green_energy, offshore_wind, solar |
| 6 | 3691 | 碩禾 | battery_materials, environmental, front_end_materials, green_energy, leadframe, solar |
| 6 | 5227 | 立凱-KY | battery_cell, battery_materials, bbu, energy_storage, green_energy, solar |
| 6 | 1597 | 直得 | chassis, defense, industrial_automation, machine_tools, manufacturing, precision_parts |
| 6 | 6147 | 頎邦 | ai_adv_packaging, crystal_osc, front_end_materials, ospat, power_inductor, precision_parts |

## 1c. Overlap — merge candidates

**Jaccard ≥ 0.5** (17 pairs). The first 8 are the **industry≈flagship-theme** collapse:

| Jaccard | inter | pair | class |
|---|---|---|---|
| 1.00 | 6 | `silicon_wafer` (6) ↔ `jp_wafer` (6) | **jp_ duplicate** |
| 0.94 | 15 | `software_cloud` (15) ↔ `cloud_msp` (16) | **industry≈theme** |
| 0.94 | 15 | `financials` (15) ↔ `banks` (16) | **industry≈theme** |
| 0.93 | 14 | `consumer` (15) ↔ `ecommerce` (14) | **industry≈theme** |
| 0.87 | 13 | `green_energy` (15) ↔ `offshore_wind` (13) | **industry≈theme** |
| 0.83 | 15 | `manufacturing` (15) ↔ `industrial_automation` (18) | **industry≈theme** |
| 0.80 | 12 | `ai_hardware` (15) ↔ `ai_server` (12) | **industry≈theme** |
| 0.79 | 15 | `shipping_logistics` (15) ↔ `container_shipping` (19) | **industry≈theme** |
| 0.75 | 3 | `front_end_equipment` (4) ↔ `jp_front_end_equip` (3) | jp_ duplicate |
| 0.70 | 7 | `liquid_cooling` (8) ↔ `air_cooling` (9) | genuine near-dup |
| 0.57 | 4 | `fab_equipment` (7) ↔ `front_end_equipment` (4) | nesting |
| 0.57 | 8 | `ems` (13) ↔ `odm` (9) | genuine near-dup |
| 0.53 | 9 | `semiconductor` (15) ↔ `foundry` (11) | industry≈theme |
| 0.50 | 2 | `jp_front_end_equip` (3) ↔ `jp_back_end_equip` (3) | jp_ duplicate |
| 0.50 | 5 | `hbm` (7) ↔ `cxl` (8) | contaminated pair |
| 0.50 | 7 | `ai_server` (12) ↔ `odm` (9) | genuine near-dup |
| 0.50 | 5 | `capacitor` (10) ↔ `jp_passive` (5) | jp_ duplicate |

**Subset pairs (smaller ⊆ 90%+ of larger, 18 pairs).** Notable full (100%) containments confirming the industry-layer is fake:
`financials ⊆ banks`, `software_cloud ⊆ cloud_msp`, `manufacturing ⊆ industrial_automation`, `shipping_logistics ⊆ container_shipping`, `ecommerce ⊆ consumer`, `ai_server ⊆ ai_hardware`, `offshore_wind ⊆ green_energy`. Plus the jp_ nest: `jp_wafer ⊆ semiconductor`, `jp_front_end_equip ⊆ fab_equipment ⊆ …`, `jp_passive ⊆ mlcc`, `jp_passive ⊆ capacitor`, `jp_back_end_equip ⊆ pkg_metrology`.

## 1d. Reason quality (the over-tagging mechanism)

| Metric | Value |
|---|---|
| Empty/missing `reason` | 1026 / 1413 (**73%**) |
| Distinct (ticker, reason) reused across ≥2 sectors | 85 |
| Member entries carrying a reused (ticker, reason) | 279 (20% of all rows) |

**Worst reason-reuse offenders** (one string copied into N sectors — this is literally how far-fetched memberships get created):

| ticker | name | reused in N sectors | the single reused reason |
|---|---|---|---|
| 3680 | 家登 | 10 | 供應極紫外光（EUV）光罩盒與晶圓傳送盒，為先進製程關鍵耗材。 |
| 6271 | 同欣電 | 9 | 生產陶瓷基板與封裝元件，應用於衛星通訊與軍用電子。 |
| 6669 | 緯穎 | 8 | 雲端伺服器與資料中心設備供應商，為全球主要雲端服務商代工。 |
| 3131 | 弘塑 | 8 | 提供濕製程設備與化學品供應系統，廣泛應用於先進封裝與晶圓製造。 |
| 2382 | 廣達 | 7 | 全球最大筆電代工廠，為各品牌組裝AI PC筆電。 |
| 2454 | 聯發科 | 7 | 全球領先的IC設計公司，專注於手機、智慧家庭與物聯網晶片解決方案。 |
| 3105 | 穩懋 | 6 | 全球最大砷化鎵晶圓代工廠，為衛星通訊提供射頻元件。 |
| 4938 | 和碩 | 6 | 全球主要電子代工廠，為蘋果等品牌代工筆電與消費性電子。 |
| 1519 | 華城 | 6 | 重電設備領導廠商，專精於變壓器、開關設備及配電盤。 |

The reason never changes per sector — it's a company blurb, not a per-theme thesis. When the same blurb is pasted into 10 sectors, 9 of them are almost always a stretch.

**Sectors with the most duplicated-reason members** (i.e. built mostly from copied blurbs): `financials`/`banks` (12 each), `green_energy`/`offshore_wind` (8 each), `shipping_logistics`/`container_shipping` (7 each) — exactly the industry≈theme pairs, confirming those pairs were populated by copy-paste.

## 1e. Hierarchy — VERIFIED clean on the mechanical checks

| Check | Result |
|---|---|
| Themes with `group=None` | 0 |
| Themes whose `group` isn't one of the 10 industry ids | 0 |
| Industries carrying a `group` | 0 |
| An `exposure_id` used as a member `ticker` | 0 |

The *referential* hierarchy is well-formed. The *semantic* hierarchy is not (see 2i — industries duplicating their flagship theme). No mechanical guard catches that.

## 1f. Naming scan

**Region/market words in display_name** (4, all Japan):

| sector_id | display_name |
|---|---|
| `sector_jp_front_end_equip` | 日本前段設備 |
| `sector_jp_back_end_equip` | 日本後段設備 |
| `sector_jp_wafer` | 日本矽晶圓 |
| `sector_jp_passive` | 日本被動元件 |

All 4 members are **TW-listed tickers** (環球晶, 穩懋, 家登, 弘塑…) — the "日本" prefix describes the end-market/supply-chain, not the listing. For a TW retail investor browsing TW sectors, "日本矽晶圓" containing 環球晶 is confusing and, per 1c, 100% redundant with the non-jp sibling.

`exposure_id` prefix scan: all 103 correctly start with `sector_`. No anomalies.

---

# PART 2 — JUDGMENT AUDIT (INFERRED unless noted)

## 2g. Far-fetched memberships (top offenders)

Rubric: the theme is **not a material business driver** for the company. Roster membership VERIFIED from the seed; the *stretch* judgment is INFERRED from company business. Confidence H/M.

| # | sector | ticker | name | why it's a stretch | conf |
|---|---|---|---|---|---|
| 1 | `hbm` | 2330 | 台積電 | Foundry, not a DRAM/HBM maker. TSMC does CoWoS around HBM but doesn't make HBM — the theme isn't a driver. (the known bad) | **H** |
| 2 | `hbm` | 5388 | 中磊 | Networking/router ODM. No memory business at all. | **H** |
| 3 | `hbm` | 5269 | 祥碩 | USB/PCIe/SATA controller IC (ASMedia). Not HBM. | **H** |
| 4 | `hbm` | 6515 | 穎崴 | Test-socket maker. Peripheral to HBM at best. | **H** |
| 5 | `cxl` | 5388 | 中磊 | Router ODM again — not a CXL controller/switch player. | **H** |
| 6 | `cxl` | 8261 | 富鼎 | Power MOSFET maker. Unrelated to CXL. | **H** |
| 7 | `cxl` | 6515 | 穎崴 | Test sockets, not CXL silicon. | **H** |
| 8 | `pkg_metrology` | 3017 | 奇鋐 | Thermal/cooling module maker. Not packaging metrology/automation equipment. | **H** |
| 9 | `industrial_automation` | 3017 | 奇鋐 | Cooling company; industrial automation isn't its business. | **H** |
| 10 | `ar_vr_optics` | 6271 | 同欣電 | Ceramic-substrate/hybrid IC packager. AR/VR optics is not a driver — swept in by the copied "衛星/軍用" blurb. | **H** |
| 11 | `crystal_osc` | 6271 | 同欣電 | Not a quartz/frequency-control maker. | **H** |
| 12 | `resistor` | 6271 | 同欣電 | Not a chip-resistor maker. | **H** |
| 13 | `connector` | 6271 | 同欣電 | Not a connector maker. | **H** |
| 14 | `cpu_agentic_ai` | 2330 | 台積電 | Foundry, not a CPU/agentic-AI product company. | M |
| 15 | `cpu_agentic_ai` | 6515 | 穎崴 | Test sockets, not CPU/AI silicon. | **H** |
| 16 | `cpu_agentic_ai` | 5347 | 世界 | Analog/power foundry (Vanguard). Not CPU/agentic AI. | **H** |
| 17 | `saas` | 6669 | 緯穎 | Hardware server ODM. SaaS (software subscription) is not its model. | **H** |
| 18 | `saas` | 2417 | 圓剛 | Video-capture hardware. Not enterprise SaaS. | M |
| 19 | `cloud_msp` | 5321 | 美而快 | E-commerce/apparel platform, not a cloud MSP. | M |
| 20 | `cloud_msp` | 2640 | 大車隊 | Taxi-fleet operator (Taiwan Taxi). Not a cloud MSP. | **H** |
| 21 | `edge_ai` | 6515 | 穎崴 | Test sockets. Not an edge-AI product. | **H** |
| 22 | `silicon_photonics` | 2454 | 聯發科 | Mobile SoC house; silicon photonics/CPO is not a MediaTek driver. | M |
| 23 | `wide_bandgap` | 5269 | 祥碩 | Controller-IC designer, no SiC/GaN business. | **H** |
| 24 | `wide_bandgap` | 6443 | 元晶 | Solar-cell maker (TSEC). Not third-gen semi. | M |
| 25 | `battery_materials` | 1503 | 士電 | Heavy-electrical (transformers/switchgear). Not a battery-material supplier. | **H** |
| 26 | `energy_storage` | 6443 | 元晶 | Solar-cell maker; storage integration isn't its business. | M |
| 27 | `environmental` | 1417 | 嘉裕 | Menswear/apparel (Carnival). Not resource/environmental industry. | **H** |
| 28 | `environmental` | 3691 | 碩禾 | Solar-paste/battery-material maker. Not environmental services. | M |
| 29 | `defense` | 2206 | 三陽工業 | Scooter/motorcycle maker (SYM). Defense is immaterial. | M |
| 30 | `defense` | 1597 | 直得 | Linear-guideway maker. Defense exposure is speculative, not a driver. | M |
| 31 | `hbm` | 5388 & pattern | — | (see #2) whole HBM sector is ~60% non-memory | **H** |

**Concentration:** the offenders cluster in a handful of sectors — `hbm`, `cxl`, `cpu_agentic_ai`, and the `同欣電`/`奇鋐`/`緯穎` over-tag chains. `sector_hbm` alone: only 南亞科 (2408) and 華邦電 (2344) are real memory makers; the other 5 of 7 are stretches. That single sector is majority-wrong, which is why patching just 2330 was insufficient.

## 2h. Naming / ambiguity issues

| sector_id | current display | problem | suggested direction (INFERRED) |
|---|---|---|---|
| `sector_jp_front_end_equip` | 日本前段設備 | Region prefix on TW-ticker sector; 100% redundant with `front_end_equipment` | Merge into `front_end_equipment`; drop the jp_ sector |
| `sector_jp_back_end_equip` | 日本後段設備 | Same | Merge into `pkg_equipment`/`pkg_metrology`; drop |
| `sector_jp_wafer` | 日本矽晶圓 | Same; J=1.0 vs `silicon_wafer` | Merge into `silicon_wafer`; drop |
| `sector_jp_passive` | 日本被動元件 | Same; ⊆ `mlcc`/`capacitor` | Merge into `mlcc`; drop |
| `sector_odm` | 整合與委外 | Vague — "integration & outsourcing" tells a retail investor nothing; near-identical to `ems`/`ai_server` | Rename to something concrete (e.g. 伺服器/系統 ODM) or merge into `ems` |
| `sector_ospat` | 封測代工 | `ospat` id is opaque jargon (OSAT); fine as display but id is cryptic | id → `sector_osat` (cosmetic) |
| `sector_air_cooling` | 氣冷與核心組件 | "核心組件" is a catch-all that overlaps `chassis`/`liquid_cooling` | Tighten to 氣冷散熱; move core components out |
| `sector_environmental` | 資源環保工業 | Broad TWSE bucket; contains apparel (嘉裕) and solar-paste (碩禾) that don't fit | Rename to 環保與資源回收 and purge non-fits |
| `sector_cpu_agentic_ai` | CPU 與 Agentic AI | Two unrelated concepts bolted together; "Agentic AI" is a buzzword with no clean TW roster | Split or rename; likely fold into `asic_ip`/`hpc_networking_ic` |
| `sector_cxl` | CXL 技術 | Niche protocol most retail investors won't recognize; roster is contaminated | Consider folding into a broader memory/interconnect theme |
| `sector_capacitor` / `sector_mlcc` / `sector_resistor` / `sector_power_inductor` | 電容器 / 被動元件 MLCC / 電阻與被動保護 / 功率電感 | Four near-siblings under one real concept (passives); a retail investor won't distinguish them | Consider one 被動元件 theme with sub-tags, or keep but document the boundary |

## 2i. Taxonomy structure issues

**(1) The industry layer is largely fictional — 6–7 industries duplicate one child theme.** VERIFIED overlaps (1c) show industry ≈ flagship theme at Jaccard 0.79–0.94 with 100% subset containment:

| industry | duplicate child theme | Jaccard | verdict |
|---|---|---|---|
| `sector_financials` | `sector_banks` | 0.94 | industry is just "banks"; no distinct content |
| `sector_software_cloud` | `sector_cloud_msp` | 0.94 | " |
| `sector_consumer` | `sector_ecommerce` | 0.93 | " |
| `sector_shipping_logistics` | `sector_container_shipping` | 0.79 | " |
| `sector_manufacturing` | `sector_industrial_automation` | 0.83 | " |
| `sector_ai_hardware` | `sector_ai_server` | 0.80 | " |
| `sector_green_energy` | `sector_offshore_wind` | 0.87 | " |

Root cause: the 10 industries were seeded with ~15 members each rather than aggregating their children, so each industry became a hand-picked "top names" list that happens to equal its most prominent theme. An industry page and its flagship theme page would show the same ~15 stocks.

**(2) Three themes are really raw TWSE industry dumps, not themes** (VERIFIED counts, 1a): `textile` (51), `steel_metals` (47), `tourism` (47) have no thesis — they're the full 紡織/鋼鐵/觀光 rosters. Either promote them to industries or curate down to a real sub-theme.

**(3) Themes too narrow to sustain a page** (INFERRED + VERIFIED counts): `jp_front_end_equip` (3), `jp_back_end_equip` (3) — both fully redundant. `agritech` (4), `glass_ceramics` (4), `front_end_equipment` (4) are thin; the last is ⊆ `fab_equipment`.

**(4) Genuine near-duplicate themes to merge** (VERIFIED overlap, INFERRED merge call):
- `liquid_cooling` + `air_cooling` (J=0.70) → one 散熱 theme, or clean the shared members.
- `ems` + `odm` + `ai_server` (pairwise J 0.5–0.57, all share 廣達/緯創/和碩/英業達) → these three are one "系統代工" cluster wearing three hats.
- `hbm` + `cxl` (J=0.5) → overlap is driven by shared *contamination* (中磊/穎崴/祥碩), not by real dual-play; fix by purging, not merging.
- All 4 jp_ themes → merge into non-jp siblings (see 2h).

**(5) Themes that are really industries / mis-leveled:** `industrial_automation` (18), `container_shipping` (19), `banks` (16) are broad enough to *be* the industry — the current setup has the child bigger and more complete than the parent, inverting the hierarchy.

## 2j. Overall verdict

**Salvageable with a curation layer — the taxonomy skeleton is sound; the population process is the defect.** The referential hierarchy is clean (1e: zero dangling groups, zero mis-typed members), the theme *names* are 96% sensible (only 4 jp_ region-prefixes), and 79% of tickers sit in exactly one sector. The damage is concentrated and mechanical: (a) a **reason-reuse over-tagging bug** that pasted one company blurb into up to 10 themes, polluting 20% of rows and creating every far-fetched membership including 2330-in-HBM; and (b) an **industry layer seeded as a flat top-names list** instead of an aggregation, making 6–7 of the 10 industries duplicate their flagship theme. Neither requires a redesign of the schema — both are fixable with a curation pass: purge memberships where the (ticker, reason) was copied and the theme isn't a real driver, dedupe the industry↔flagship-theme pairs (make industries aggregate children rather than carry their own member list), and drop/merge the 4 jp_ and 3 raw-TWSE-dump sectors. The one structural change worth making is redefining industries as pure roll-ups of their themes so the "top-names duplicates flagship theme" class can't recur.

---

## Appendix — reproduction

- Metrics script: `audit_sectors.py` (stdlib only; `python3 audit_sectors.py <path-to-sectors_seed.py>`). Includes a self-check asserting count consistency.
- Roster dump for judgment calls: `inspect.py`.
- All Part-1 tables are regenerable; all Part-2 stretch/merge judgments are marked INFERRED and should be reviewed by a TW-market analyst before acting.
