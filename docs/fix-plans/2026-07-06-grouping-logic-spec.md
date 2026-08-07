# TinBoker sector/theme taxonomy — full generation spec (verified 2026-07-06)

Repo root: /Users/willy/Documents/tinboker/.claude/worktrees/loving-raman-0e1ab1

## 0. TOP-LEVEL FINDING: two generator lineages, only ONE is live

There are **two unrelated generation chains** for the sector/theme universe, from
two different eras of this codebase. Any redesign must pick one, not both.

- **Chain A (LIVE, current source of truth):**
  `pipelines/libs/shared/scripts/build_sectors_seed_from_tide.py` → writes
  `backend/src/data/sectors_seed.py` (`SECTORS_SEED`, committed Python literal) →
  loaded at backend startup → `sync_sectors()`
  (`backend/src/tag_registry.py:234-311`) upserts into Postgres `tag_registry`
  table (`kind='sector'`) → served by `/api/sectors/*` routes in
  `backend/src/routers/tags.py` and read by `backend/src/services/podcast.py`
  (`_sector_membership_index`, `list_sectors`, `sector_board`).
  Last touched by commit `57766c3` (theme→industry parent link), after `a82e1dc`
  (the tide rewrite, 2026-06-2x era) and after `096d055` — this is the newest
  lineage and the one the fix-plan doc (`docs/fix-plans/2026-07-06-sector-curation-and-reasons.md`)
  targets.

- **Chain B (DEAD/ORPHANED — do not build on this):**
  `refresh_industry_members.py` (`FinMind → sector_and_theme_universe.json`) →
  `compile_sector_and_theme_universe.py` (merges `curated_themes.json` +
  `tickers.json` → `sector_and_theme_universe.json`) → `generate_sector_visuals.py`
  → `generate_sector_reasons.py`, wired together by
  `.github/workflows/refresh-sectors.yml` (weekly cron, Mon 04:00 UTC).
  **All of `curated_themes.json`, `tickers.json`, `sector_and_theme_universe.json`,
  `finmind_industry_map.json` were DELETED from the repo on 2026-06-28 in commit
  `b3fae75` ("refactor(data): eliminate JSON files and maintain sector/theme
  universe and ticker registry entirely in DB")** — VERIFIED via
  `git show --stat b3fae75` (14 files, -19053/+28256 lines) and confirmed those
  paths do not exist on disk today (`find pipelines/libs/shared/src/shared` shows
  no `data/` directory at all). `refresh_industry_members.py`
  (last touched `62375df`, pre-`b3fae75`) and `compile_sector_and_theme_universe.py`
  (last touched `096d055`, pre-`b3fae75`) were never updated after the JSON
  elimination — running them today would `FileNotFoundError` immediately
  (`pipelines/libs/shared/scripts/compile_sector_and_theme_universe.py:26-27`
  hardcodes `ROOT / "tickers.json"` / `"curated_themes.json"`, neither exists).
  `.github/workflows/refresh-sectors.yml` (unchanged since `62375df`) still runs
  this dead chain on a live cron schedule and would fail on every Monday run
  (or silently produce a broken PR) — this is exactly what fix-plan M0 flags as
  a risk ("the weekly chain no longer agrees with the tide-based seed").
  `pipelines/libs/shared/src/shared/sectors.py:127-135` (`_universe()`) confirms
  the runtime resolver no longer reads any local JSON — it calls
  `fetch_sectors_universe()` (`platform_client.py:104-121`, an HTTP GET to
  `{backend}/api/sectors/universe`) and only falls back to the **committed
  Python seed** `shared.sectors_seed_backup.py` (`SECTORS_SEED`, a byte-identical
  copy of `backend/src/data/sectors_seed.py`, both written by Chain A) if that
  HTTP call fails. There is no code path left that reads `sector_and_theme_universe.json`.

**Practical implication for the redesign:** the entire input-shape investigation
(curated_themes.json / tickers.json layout) requested in the task is now
answered "these files do not exist"; Chain B's scripts and its GitHub Action are
dead weight that should be deleted or fixed as part of any redesign (fix-plan M0
already scopes this).

---

## 1. Input sources — `tide-tw-data`

File: `pipelines/libs/shared/scripts/build_sectors_seed_from_tide.py`

- Default path: `REPO / "tide-tw-data"` where `REPO = Path(__file__).resolve().parents[4]`
  (`build_sectors_seed_from_tide.py:39,371`) — i.e. the monorepo root, sibling to
  `pipelines/`, `backend/`, `frontend/`.
- **Does not exist locally.** `find` across `/Users/willy/Documents` and repo root
  found no `tide-tw-data` directory anywhere on this machine. It is listed in
  `.gitignore:53` as `tide-tw-data/` — confirmed gitignored, one-shot input, never
  committed (script docstring line 26-27: "tide-tw-data is gitignored... we commit
  the generated .py, not this input").
- Expected file layout, read at `build_sectors_seed_from_tide.py:269-271`:
  - `sector_groups.json` — `{group_name: [subindustry_name, ...]}`, exactly 10 keys
    (the 10 industries). Parsed as `groups = json.loads(...)`.
  - `latest.json` — `{"sectors": [{"name": subindustry_name, "stocks": [ticker,...]}, ...]}`
    (plus unused money-flow fields per docstring line 6). Parsed into
    `sub_stocks = {s["name"]: s["stocks"] for s in latest["sectors"]}` (line 272).
  - `stock_names.json` — `{ticker: zh_name}` flat map, used in `make_member()`
    (line 238-246) to fill each member's `name`.
- What we know of tide-tw-data's own curation: only the inline comments in this
  script (no README ships with it locally). Docstring says it is "a 2-level,
  Taiwan-only taxonomy" and that display metadata (slug/icon/colour/aliases/
  per-ticker reasons) is **not** in tide — TinBoker reuses/derives all of that
  itself (lines 16-21). No other provenance doc for tide-tw-data exists in this
  repo; it is treated as an external, hand-curated upstream (per the fix-plan's
  data-flow diagram, `docs/fix-plans/2026-07-06-sector-curation-and-reasons.md:25`:
  "tide-tw-data (external dir, gitignored, hand-curated upstream)").

---

## 2. Industry derivation (the 10 industries)

- The 10 industries are exactly the 10 top-level keys of tide's
  `sector_groups.json`, iterated in file order (`for group, subnames in
  groups.items()`, `build_sectors_seed_from_tide.py:283`). No other source
  contributes industries — the 10 names are fixed a priori in `GROUP_META`
  (lines 55-76), a hardcoded dict keyed by the **exact Chinese group name** tide
  must use: `半導體, AI與電子硬體, 軟體雲端資安, 綠能與電力, 金融, 航運物流,
  傳產製造, 民生消費, 營建地產, 生技醫療`. If tide ever renames/adds/removes a
  top-level group, `GROUP_META[group]` (line 284) raises `KeyError` — there is
  no fallback/validation for unknown groups (see §7).
- Each industry's `exposure_id` (slug), `icon_id`, `color_hex`, `aliases` come
  verbatim from `GROUP_META` (lines 55-76) — NOT derived from tide, hand-authored
  in this script.
- **Membership**: an industry's members = the **union** (dedup via
  `OrderedDict.fromkeys`, order-preserving) of the TW stock lists of ALL its
  sub-industries (`union = ... for sn in subnames for t in sub_stocks.get(sn, [])`,
  lines 286-288) — including sub-industries that are later dropped as themes
  (e.g. `其他產業`, any `・其他` bucket) — the industry-level union does not
  apply `is_theme_sub()` filtering, only the theme loop does.
- **Ordering**: `order_members(union, curated_tw, cap=LEADERS_CAP)`
  (line 289, function at 249-265): tickers that are members of the **current**
  committed seed (`curated_tw`, built from `load_current_seed()` /
  `build_reuse_index()`, lines 274-278 — i.e. hand-picked/curated TW members of
  the seed that exists BEFORE this regeneration run) come first, in tide's own
  order among themselves; then all remaining tide tickers in tide's order.
  Industries are **capped to `LEADERS_CAP = 15`** members (line 44) — these are
  "display leaders" only (docstring lines 20-21); full attribution for
  discussion-heat is derived from the industry's child themes via the `group`
  link, not from this capped leader list (see `_sector_membership_index`,
  §5/§6).
- `group` field for every industry entry is hardcoded `None` (line 296) —
  industries are always top-level, never nested under another industry.

---

## 3. Theme derivation — FULL `THEME_OVERRIDE` table + fallback rule

File: `build_sectors_seed_from_tide.py:81-175`. Verbatim, all 93 entries (tide
sub-industry name → override dict). Keys not in this table fall through to the
auto-slug rule below.

```
"PCB 載板": {"slug": "sector_pcb_substrate", ...}
"汽車工業・其他": {"slug": "sector_auto", "display": "汽車", ...}
"AI 先進封裝": {"slug": "sector_ai_adv_packaging", ...}
"HBM 高頻寬記憶體": {"slug": "sector_hbm", ...}
"CXL 技術": {"slug": "sector_cxl", ...}
"客製 ASIC 矽智財": {"slug": "sector_asic_ip", ...}
"CPU 與 Agentic AI": {"slug": "sector_cpu_agentic_ai", ...}
"HPC 與網通 IC": {"slug": "sector_hpc_networking_ic", ...}
"第三代半導體": {"slug": "sector_wide_bandgap", ...}
"記憶體模組": {"slug": "sector_memory_module", ...}
"顯示驅動 IC": {"slug": "sector_display_driver_ic", ...}
"IC 通路": {"slug": "sector_ic_distribution", ...}
"AI 伺服器組裝": {"slug": "sector_ai_server", ...}
"液冷散熱": {"slug": "sector_liquid_cooling", ...}
"氣冷與核心組件": {"slug": "sector_air_cooling", ...}
"高速光模組": {"slug": "sector_optical_module", ...}
"矽光子與 CPO": {"slug": "sector_silicon_photonics", ...}
"AI 互連元件": {"slug": "sector_ai_interconnect", ...}
"車用連接器": {"slug": "sector_auto_connector", ...}
"軟板": {"slug": "sector_fpc", ...}
"PCB 硬板製造": {"slug": "sector_pcb_rigid", ...}
"玻璃基板": {"slug": "sector_glass_substrate", ...}
"AI PC 筆電與平板": {"slug": "sector_ai_pc", ...}
"EMS 電子代工": {"slug": "sector_ems", ...}
"MicroLED 顯示供應鏈": {"slug": "sector_microled", ...}
"光學鏡頭": {"slug": "sector_optical_lens", ...}
"AR VR XR 光學": {"slug": "sector_ar_vr_optics", ...}
"Edge AI AIoT": {"slug": "sector_edge_ai", ...}
"高速交換器與無線網路": {"slug": "sector_networking", ...}
"低軌衛星": {"slug": "sector_leo_satellite", ...}
"石英頻率控制": {"slug": "sector_crystal_osc", ...}
"雲端與 MSP": {"slug": "sector_cloud_msp", ...}
"企業 SaaS": {"slug": "sector_saas", ...}
"資安防護": {"slug": "sector_cybersecurity", ...}
"離岸風電": {"slug": "sector_offshore_wind", ...}
"太陽能產業": {"slug": "sector_solar", ...}
"儲能系統整合": {"slug": "sector_energy_storage", ...}
"電池關鍵材料": {"slug": "sector_battery_materials", ...}
"電芯製造與電池模組": {"slug": "sector_battery_cell", ...}
"BBU 電池備援": {"slug": "sector_bbu", ...}
"電源供應器": {"slug": "sector_power_supply", ...}
"工業自動化": {"slug": "sector_industrial_automation", ...}
"CNC 工具機": {"slug": "sector_machine_tools", ...}
"精密機構件": {"slug": "sector_precision_parts", ...}
"國防軍工": {"slug": "sector_defense", ...}
"被動元件 MLCC": {"slug": "sector_mlcc", ...}
"IC 測試服務": {"slug": "sector_ic_testing", ...}
"封測代工": {"slug": "sector_ospat", ...}
"類比與功率 IC": {"slug": "sector_analog_power_ic", ...}
"NOR Flash 利基記憶體": {"slug": "sector_nor_flash", ...}
"矽晶圓": {"slug": "sector_silicon_wafer", ...}
"晶圓代工": {"slug": "sector_foundry", ...}
"晶圓廠設備": {"slug": "sector_fab_equipment", ...}
"前段製程材料": {"slug": "sector_front_end_materials", ...}
"前段製程設備": {"slug": "sector_front_end_equipment", ...}
"封裝量測自動化": {"slug": "sector_pkg_metrology", ...}
"封裝製程機台": {"slug": "sector_pkg_equipment", ...}
"導線架與化學品": {"slug": "sector_leadframe", ...}
"功率電感": {"slug": "sector_power_inductor", ...}
"電容器": {"slug": "sector_capacitor", ...}
"電阻與被動保護": {"slug": "sector_resistor", ...}
"連接器 工業消費": {"slug": "sector_connector", ...}
"玻纖布": {"slug": "sector_glass_fiber", ...}
"智慧型手機": {"slug": "sector_smartphone", ...}
"整合與委外": {"slug": "sector_odm", ...}
"機殼與滑軌": {"slug": "sector_chassis", ...}
"面板產業": {"slug": "sector_display_panel", ...}
"光感測與元件": {"slug": "sector_optical_sensing", ...}
"日本前段設備": {"slug": "sector_jp_front_end_equip", ...}
"日本後段設備": {"slug": "sector_jp_back_end_equip", ...}
"日本矽晶圓": {"slug": "sector_jp_wafer", ...}
"日本被動元件": {"slug": "sector_jp_passive", ...}
"電器電纜": {"slug": "sector_wire_cable", ...}
"資源環保工業": {"slug": "sector_environmental", ...}
"油電燃氣": {"slug": "sector_oil_gas", ...}
"銀行金融": {"slug": "sector_banks", ...}
"貨櫃航運": {"slug": "sector_container_shipping", ...}
"散裝航運": {"slug": "sector_bulk_shipping", ...}
"石化與塑膠產業": {"slug": "sector_petrochemical", ...}
"橡膠": {"slug": "sector_rubber", ...}
"水泥": {"slug": "sector_cement", ...}
"玻璃陶瓷": {"slug": "sector_glass_ceramics", ...}
"紡織成衣": {"slug": "sector_textile", ...}
"造紙": {"slug": "sector_paper", ...}
"鋼鐵金屬": {"slug": "sector_steel_metals", ...}
"電商零售": {"slug": "sector_ecommerce", ...}
"居家生活": {"slug": "sector_home_living", ...}
"文化創意": {"slug": "sector_culture_creative", ...}
"觀光餐旅": {"slug": "sector_tourism", ...}
"貿易百貨": {"slug": "sector_retail_dept", ...}
"農業科技": {"slug": "sector_agritech", ...}
"運動休閒": {"slug": "sector_sports_leisure", ...}
"食品飲料": {"slug": "sector_food_beverage", ...}
```
(exact `aliases`/`display`/`icon`/`color` sub-fields: see file lines 82-175
verbatim — omitted here as the sub-values are not decision-relevant to the
grouping *logic*, only to display copy.)

- **Fallback for sub-industries NOT in `THEME_OVERRIDE`:** auto-slug —
  `slug = f"sector_{gslug.split('_', 1)[1]}_{_ascii_slug(sn)}"`
  (line 310), i.e. `sector_<industry-slug-without-"sector_"-prefix>_<ascii-slug-of-subindustry-name>`.
  `_ascii_slug()` (lines 336-343) strips non-ASCII chars, lowercases, joins
  surviving alnum tokens with `_`; if the sub-industry name has NO ASCII tokens
  at all (pure CJK), it falls back to a **deterministic hash tag**:
  `format(abs(hash(name)) % 0xFFFFFF, "06x")` — note this uses Python's
  built-in `hash()`, which is **only stable within one `PYTHONHASHSEED`
  process run** for str hashing unless `PYTHONHASHSEED` is fixed; this is a
  latent slug-stability risk for any never-overridden pure-CJK sub-industry
  name (not currently triggered because every entry the tide data has produced
  so far is in the override table, per script comment lines 78-80: "Everything
  else falls back to the group icon/colour and a transliterated slug").
  Slug collisions across sub-industries append `_2`, `_3`, ... (lines 312-315).
- **Sub-industries excluded/dropped from becoming themes**, decided by
  `is_theme_sub()` (lines 228-235):
  1. Name is in `DROP_THEME = {"其他產業"}` (line 47) → dropped unconditionally.
  2. Name is in `KEEP_DESPITE_SUFFIX = {"汽車工業・其他"}` (line 177) → kept
     even though it matches the suffix rule below (explicit carve-out, comment
     line 176: "the only '・其他' we keep — there is no cleaner 汽車 theme in tide").
  3. Name contains the literal substring `DROP_THEME_SUFFIX = "・其他"` (line 48)
     → dropped (residual/catch-all buckets).
  4. Otherwise kept as a theme.
  - Additionally, **industries in `SINGLE_SUB_GROUPS = {"生技醫療", "營建地產"}`**
    (line 51) are skipped **entirely** in the theme loop (`if group in
    SINGLE_SUB_GROUPS: continue`, lines 303-304) — these two groups' sole
    sub-industry equals the group name itself, so making a theme would be a
    literal duplicate of the industry; they surface as industry-only.

---

## 4. Hierarchy — `group` field

- Every **theme** entry's `group` = its parent industry's `exposure_id` (the
  `gslug` computed from `GROUP_META[group]` for the outer-loop's tide group,
  `build_sectors_seed_from_tide.py:329`). A theme's parent is 1:1 determined by
  which tide top-level group its sub-industry name was nested under in
  `sector_groups.json` — there is no cross-industry theme (a sub-industry can
  only belong to one group in tide's own structure, and this script does not
  attempt to re-assign it).
- Every **industry** entry's `group` = `None` (line 296) — industries can never
  have a parent; there is no 3rd hierarchy level.
- A theme can never have `group = None` in this generator's output — every
  theme is produced inside the per-group loop (line 302), so it always inherits
  a `gslug`. (Themes from **Chain B**'s `curated_themes.json`, if that JSON
  file existed, could in principle omit a `group` — but Chain B is dead, see §0.)
- This `group` link is what `_sector_membership_index()`
  (`backend/src/services/podcast.py:1225-1289`) uses at read time to also
  credit a theme's tickers to its parent industry for discussion-heat
  attribution (`parent = r.parent_id`, lines 1273-1280) — i.e. hierarchy is
  re-derived from the DB's `parent_id` column (`TagRegistry.parent_id`,
  `backend/src/database/models.py:290`), which is synced from `group` in
  `sync_sectors()` (`tag_registry.py:264`: `existing.parent_id =
  sector.get("group")  # pipeline-owned, refresh always` — this is the ONE
  field `sync_sectors` always overwrites even on existing rows, unlike members/
  aliases which are only set once, see §5-§6).

---

## 5. Member assembly — precedence, dedup, ordering, market filter, reason reuse

Everything below is `build_sectors_seed_from_tide.py` logic (Chain A, live).

- **Sources merged, in order of precedence:**
  1. `curated_tw` — the set of TW tickers from the CURRENT committed seed
     (`load_current_seed()` loads `backend/src/data/sectors_seed.py`'s
     `SECTORS_SEED` before regeneration, lines 206-210, 274). This is "what a
     human curated previously" — it wins ordering priority (see below) but is
     NOT an independent membership source; a ticker only appears in a new
     theme/industry if tide's `latest.json` currently lists it under that
     sub-industry — `curated_tw` only affects **order**, not **inclusion**
     (confirmed by `order_members`, lines 249-265: it reorders `stocks` — the
     tide list — it never adds tickers absent from `stocks`).
  2. tide's `latest.json` per-sub-industry stock list (`sub_stocks[sn]`) — this
     is the actual membership source for both industries (unioned across
     sub-industries) and themes (per sub-industry).
  - **FinMind (Chain B's `refresh_industry_members.py`) is a SEPARATE, now-dead
    lineage** (see §0) — it is not merged into Chain A's output at all today.
    Historically (per its own docstring) it was meant to be additive breadth on
    top of curated members for `exposure_type='sector'`/`'industry'` rows only,
    never touching themes, with FinMind ranked by market cap and curated always
    first (`merge_sector_members`, `refresh_industry_members.py:126-157`,
    `_member_sort_key`, `sectors.py:102-110`) — but this code path is currently
    unreachable because its input file (`sector_and_theme_universe.json`) no
    longer exists (§0).
- **Dedup rule:** `OrderedDict.fromkeys` for the industry union (line 286-288,
  order-preserving de-dup across sub-industries); `order_members`'s `seen` set
  (lines 256-264) guarantees each ticker appears exactly once per sector even if
  present in both the curated-first pass and the tide-order pass.
- **Ordering rule:** `order_members()` (lines 249-265) — NOT market-cap-based
  in Chain A. It is "curated-first, then tide's own order": tickers already in
  `curated_tw` come first (in the order they appear in tide's `stocks` list,
  not their previous curated order), then all other tide tickers in tide's
  list order. There is no market-cap sort anywhere in this generator (market
  cap ranking exists only in the dead Chain B, `build_finmind_members`,
  `refresh_industry_members.py:103-123`, and in the runtime `_member_sort_key`
  used only to re-sort whatever `members` array is already stored,
  `sectors.py:102-110,141` — curated `source` still sorts first there too).
- **Market filter:** **TW-only, hard-enforced.** `make_member()`
  (lines 238-246) hardcodes `"market": "TW"` for every member. The final
  assertion in `main()` (line 392: `assert not us, "US tickers leaked into the
  TW seed"`) checks `m["market"] != "TW"` across every member of every sector
  (line 382) and aborts the script if any slip through — there is currently no
  way for a US ticker to end up in the seed via this generator (docstring
  line 14: "US tickers are intentionally dropped — a separate US topics tab
  handles them"). `build_reuse_index()` (lines 213-225) also filters
  `if mem["market"] != "TW": continue` when building the reuse index from the
  PRIOR seed, so even a residual US member from an older seed vintage can't leak
  into the reuse map.
- **Reason-reuse logic (`build_reuse_index`, lines 213-225):** Builds TWO global
  maps from the seed that existed before this run: `reason_by_ticker` (first
  non-empty `reason` found for a ticker, scanning ALL prior sectors in seed
  order — **first-wins across sectors, not keyed per-sector**) and
  `name_en_by_ticker` (same first-wins pattern for `name_en`). `make_member()`
  (lines 238-246) then looks up `reason_by_ticker.get(ticker, "")` for every
  new member in every new sector — meaning the SAME reason string, authored for
  whichever sector a ticker first appeared in historically, gets copied
  verbatim into every other sector containing that ticker. **This is exactly
  the bug flagged as P4 in the fix-plan** (`docs/fix-plans/2026-07-06-sector-curation-and-reasons.md:17`),
  proposing to re-key `build_reuse_index()` by `(exposure_id, ticker)` instead
  of bare `ticker` (fix-plan M2 step 1).

---

## 6. `refresh_industry_members.py` weekly-run semantics (volatile vs frozen) — CAVEAT: dead code path

Described as designed (the logic itself is unit-testable and coherent), but
**this script cannot currently run successfully** because its input
`sector_and_theme_universe.json` was deleted (§0) and it is not wired to Chain A
at all.

- **What it would change on each run** (if its inputs existed):
  - Only `exposure_type == 'sector'` rows (line 198) whose `exposure_id` is a
    value in `finmind_industry_map.json`'s category map (`mapped_ids`, line 200)
    — themes are never touched by this script.
  - Per mapped industry: `members` field is replaced by `merge_sector_members()`
    output — curated entries preserved, FinMind entries added/refreshed
    (`market_cap_rank` on existing FinMind members bumped; brand-new FinMind
    tickers appended with no `reason`, capped to `universe["max_tickers"]`,
    default 12, line 196).
  - `tickers.json`'s per-ticker `sector` label, but **only non-regressing**
    updates (`resolve_ticker_sector_updates`, lines 160-181): only overwrites
    when FinMind's category maps cleanly to a **different** current label, and
    never writes the raw `電子工業` catch-all category (so a fine curated label
    is never downgraded to a coarse one).
- **What stays fixed / untouched by this script even in its intended design:**
  curated members (rank-preserved, `source: "curated"` always sorts first via
  `_member_sort_key`), any `exposure_id` not in `finmind_industry_map.json`
  (`unmapped` list printed at line 229-230), every theme (`exposure_type ==
  'theme'`), all display metadata (icon/color/aliases/display_name/`group`) —
  this script never touches those fields at all.
- Actual current volatility in the LIVE system (Chain A): **nothing is
  scheduled to change automatically.** `build_sectors_seed_from_tide.py` is a
  manual, on-demand script (docstring: "Re-run when tide updates the
  curation" — no cron references it). The only cron touching sectors is
  `.github/workflows/refresh-sectors.yml`, which drives the dead Chain B and
  would fail today (§0). So in practice the entire taxonomy (industries,
  themes, membership, ordering, reasons) is **100% frozen** between manual
  `build_sectors_seed_from_tide.py --write` runs — there is no live weekly
  refresh happening despite the cron schedule existing.

---

## 7. Validation — asserts / schema checks (or confirm none)

- `build_sectors_seed_from_tide.py:392-393` (Chain A, live, runs at every
  invocation including dry-run): two hard `assert`s —
  `assert not us, "US tickers leaked into the TW seed"` (no non-TW market
  members) and `assert not empty, f"empty sectors: {empty}"` (no sector with
  zero members). These are the ONLY structural invariants enforced anywhere in
  the generation pipeline today.
- No schema validation (no Pydantic/jsonschema) of `sector_groups.json`,
  `latest.json`, or `stock_names.json` shape — a malformed tide export would
  surface as a raw `KeyError`/`TypeError` at the point of use (e.g.
  `GROUP_META[group]` at line 284 raises `KeyError` for any tide group name not
  hardcoded in `GROUP_META`; `s["name"]`/`s["stocks"]` at line 272 assumes
  every entry in `latest["sectors"]` has both keys).
- No dedup/uniqueness assertion on generated `exposure_id`s beyond the
  in-function collision-avoidance loop (lines 312-316) — collisions are
  resolved silently (append `_2`, `_3`, ...), not flagged.
- No reason-coverage assertion (nothing enforces every member has a non-empty
  `reason` — this is exactly fix-plan M2's proposed new invariant test, which
  does not exist yet).
- No membership-exclusion assertion (nothing like fix-plan M1's proposed
  `membership_overrides.json.exclude` mechanism exists today — there is
  currently NO way to hand-exclude a specific ticker from a specific sector
  short of editing the tide input itself or hand-patching the generated seed,
  which the tooling explicitly warns against, docstring line 27 "do not
  hand-edit", and fix-plan line 72 "Never hand-edit generated artifacts").
- Chain B (`compile_sector_and_theme_universe.py`, `refresh_industry_members.py`)
  has no asserts of its own; `refresh_industry_members.py`'s logic is unit
  tested offline per its docstring (line 18: "pure and unit-tested offline") —
  confirm test file location if pursuing that chain further:
  `pipelines/libs/shared/tests/test_sector_exposures.py` /
  `test_tickers.py` (found, not read in this pass — flag for redesign work if
  Chain B is revived rather than deleted).

---

## Files read in full for this spec

- `pipelines/libs/shared/scripts/build_sectors_seed_from_tide.py` (408 lines)
- `pipelines/libs/shared/scripts/compile_sector_and_theme_universe.py` (115 lines)
- `pipelines/libs/shared/scripts/refresh_industry_members.py` (260 lines)
- `pipelines/libs/shared/scripts/generate_sector_visuals.py` (131 lines)
- `pipelines/libs/shared/src/shared/sectors.py` (382 lines)
- `pipelines/libs/shared/src/shared/platform_client.py` (fetch_sectors_universe, lines 104-121)
- `backend/src/tag_registry.py` (sync_sectors + related, lines 180-320)
- `backend/src/database/models.py` (TagRegistry model, lines 261-296)
- `backend/src/services/podcast.py` (_sector_membership_index 1225-1289, list_sectors 2020-2060ish)
- `.github/workflows/refresh-sectors.yml` (96 lines)
- `docs/fix-plans/2026-07-06-sector-curation-and-reasons.md` (298 lines)
- `pipelines/AGENTS.md` (131 lines)
- git history: `b3fae75`, `096d055`, `62375df`, `a82e1dc`, `57766c3`, `23f4b48`
