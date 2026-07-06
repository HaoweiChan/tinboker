# Fix plan v2.1 — sector taxonomy: structural curation, per-sector reasons, stock-page membership

> Status: planned 2026-07-06 (v2.1 — v1 patched symptoms; v2 fixed the structure; v2.1
> incorporates the adversarial review: the old reason-generator is dead code, the tide
> input directory is absent locally, so curation is redesigned to run off the committed
> seed). Tracked as **TKB-008** in `TODO.md`.
> Audience: implementing agents (Sonnet/Opus). Follow this doc literally. Do NOT
> improvise schema or naming beyond what a milestone specifies. One milestone = one PR,
> in order.
>
> **Companion evidence docs (read the relevant one before its milestone):**
> - `docs/fix-plans/2026-07-06-grouping-logic-spec.md` — every generation rule with
>   file:line (read before M0/M1).
> - `docs/fix-plans/2026-07-06-sector-universe-audit.md` — full data audit of all 103
>   sectors: metrics, offender tables, merge candidates (read before M2).
> - `docs/fix-plans/assets/audit_sectors.py` — working stdlib-only metrics script
>   (productized in M5; do not rewrite from scratch).

---

## 1. Problems (user-reported symptoms → audited root causes)

The audit (2026-07-06, all 103 sectors / 1413 member rows / 977 tickers; numbers
re-verified independently) shows the two reported symptoms are instances of **systemic**
defects:

| # | Symptom | Systemic root cause (evidence) |
|---|---------|-------------------------------|
| P1 | 2330 in `sector_hbm` is far-fetched | Membership inherited verbatim from external `tide-tw-data` with zero per-ticker vetting, plus a **reason-reuse bug** (`build_sectors_seed_from_tide.py:213` `build_reuse_index()`: global first-wins ticker→reason map) that pastes one company blurb into up to 10 themes, making stretches look justified. Audit: 85 reused strings taint 279 rows (20%); ~30 high-confidence far-fetched memberships (audit §2g); `sector_hbm` is **majority-wrong** (only 2408 南亞科 + 2344 華邦電 of 7 members are real memory makers). |
| P2 | `sector_jp_wafer` / `sector_jp_passive` confusing (all TW tickers) | The 4 `jp_*` sectors are tide's "Japan supply-chain" themes AND are **100% redundant**: `jp_wafer` ↔ `silicon_wafer` at Jaccard 1.0; the other three ⊆ their non-jp siblings (audit §1c/§1f). Renaming keeps duplicate pages; the structural fix is **merge + redirect**. |
| P3 | Stock page doesn't show a ticker's sectors | No reverse ticker→sectors endpoint exists anywhere in backend/src. |
| P4 | Per-(ticker, sector) reasons must be sector-specific | Same reuse bug — the reason is a company blurb, never a per-theme thesis. |
| P5 | Reasons incomplete; no maintenance mechanism | **73% of reasons are EMPTY** (1026/1413). The weekly workflow is DEAD (see §2); the old LLM reason script is dead code (see §2). Only 2 build invariants exist (`build_sectors_seed_from_tide.py:392-393`). |
| P6 *(found by audit)* | Industry layer largely fictional | 6–7 of 10 industries are 79–94% identical to one child theme (financials≈banks, software_cloud≈cloud_msp, consumer≈ecommerce, shipping_logistics≈container_shipping, manufacturing≈industrial_automation, ai_hardware≈ai_server, green_energy≈offshore_wind) — industries were seeded as flat "top-~15" lists, not aggregations (audit §2i). |
| P7 *(found by audit)* | Three "themes" are raw TWSE dumps | `textile` (51), `steel_metals` (47), `tourism` (47) — full TWSE rosters, no thesis (audit §1a/§2i). |

## 2. System map — verified 2026-07-06 (v1's map was wrong on three points)

Exactly **ONE live generation chain**:

```
tide-tw-data  (external dir, gitignored .gitignore:53, ⚠ NOT PRESENT LOCALLY; the
        │      importer expects sector_groups.json / latest.json / stock_names.json,
        │      build_sectors_seed_from_tide.py:269-271, and CANNOT RUN without them)
        │  manual re-import only: python build_sectors_seed_from_tide.py --write
        ▼
backend/src/data/sectors_seed.py            ← canonical COMMITTED seed (103 sectors)
pipelines/.../shared/sectors_seed_backup.py ← pipelines fallback copy
backend/src/data/sector_reasons.json        ← mirror, emitted by the SAME build script
                                              (emit_reasons :360, write :398)
        │
        ├── backend startup: sync_sectors() (backend/src/tag_registry.py:234) upserts
        │   into Postgres tag_registry (kind='sector').
        │   ⚠ sync only writes members/aliases when the row's are EMPTY
        │   (`if not existing.members:` tag_registry.py:265); display/icon/color/type
        │   always overwrite. Seed member fixes do NOT reach existing rows on redeploy.
        │   Fixed in M1.5.
        │
        ├── served: GET /api/sectors/universe (tags.py:241, reads TagRegistry) →
        │   pipelines fetch at ingest (falls back to sectors_seed_backup.py) →
        │   episode docs embed a SNAPSHOT of sector_exposures[]
        │   (docs/firestore-contract.md §2.1.1). Universe changes do NOT retro-update
        │   episodes — run pipelines/services/podcast/scripts/
        │   backfill_sector_exposures.py --commit (dry-run by default).
        │
        └── runtime reason lookup: backend/src/data/sector_reasons.py::
            reason_for(exposure_id, ticker) reads sector_reasons.json.

DEAD CODE (do not run, delete in M5): refresh_industry_members.py,
compile_sector_and_theme_universe.py, generate_sector_reasons.py (reads the universe
JSON deleted in commit b3fae75 → FileNotFoundError; it is NOT the live reasons writer),
and .github/workflows/refresh-sectors.yml (cron still live, targets the deleted files).
```

Serving endpoints (all `backend/src/routers/tags.py`): `/api/episodes/by-sector/{id}`
:211 (SectorPage), `/api/sectors` :143, `/api/sectors/board` :160,
`/api/sectors/performance` :189 (TopicsCloud), `/api/sectors/universe` :241 (pipelines).

Facts an implementer must not miss:

- **Two membership read paths disagree**: board/performance read live `tag_registry`
  via `_sector_membership_index()` (`podcast.py:1225`); SectorPage's constituent grid
  comes from episode-embedded snapshots. A membership fix is fully live only after
  (a) seed artifacts regenerated, (b) sync overwrite lands (M1.5) + backend restart,
  (c) `backfill_sector_exposures.py --commit` run.
- **`exposure_id` is immutable** (URLs, episode snapshots). Merges/drops need a
  redirect map, never an id rename (POL-6).
- **Sector follows are SERVER-SIDE, keyed by DISPLAY NAME**: SectorPage subscribes via
  `toggleTagSubscription(displayName)` (`SectorPage.tsx:160,198`) →
  `useAppStore.ts:356` → `POST /api/user/subscriptions/tags/{tagName}/toggle`
  (`frontend/src/services/api/user.ts:143`); localStorage is only an optimistic cache.
  **Nothing matches subscriptions against `aliases`** — a rename/merge REQUIRES the
  server-side migration in M2.6 or users silently lose follows.
- **Never hand-edit generated artifacts** (`sectors_seed.py`, `sectors_seed_backup.py`,
  `sector_reasons.json`). Fixes go into the curation inputs (M1.1), then re-run
  `curate_sectors.py`.
- Per-member `reason` is already rendered on SectorPage
  (`SectorTickerCard.tsx:79-83`); P4/P5 are data problems, not missing UI.
- The 10 industries are hardcoded in `GROUP_META` (`build_sectors_seed_from_tide.py:55-76`);
  theme exclusion drops `其他` buckets (`:47-51,228-235`). Full rule list: the
  grouping-logic-spec doc.
- pipelines/ is a uv workspace (`uv sync`, never pip). OpenRouter key: env-first with
  gcloud Secret Manager fallback — copy the pattern from
  `generate_sector_reasons.py:42-53` (pattern only — never RUN that script, it reads
  deleted inputs). Never write key values anywhere.

## 3. Target design — the structural fix

**Key architectural move (v2.1):** curation is decoupled from the tide importer.
A new standalone step, `pipelines/libs/shared/scripts/curate_sectors.py`, reads the
**committed seed** + the curation inputs and rewrites the three seed artifacts. Because
it runs off the committed seed, every milestone below (and CI) works **without
tide-tw-data**; the tide importer is only for future raw re-imports, and its last step
becomes "call the curate module".

```
INPUTS (committed, human/LLM-curated):
  pipelines/libs/shared/curation/sector_overrides.json      ← exclude/include/merge/
                                                               rename/reclassify/descriptions
  pipelines/libs/shared/curation/sector_member_reasons.json ← {"<exposure_id>": {"<ticker>": "reason"}}

curate_sectors.py:  committed seed + curation inputs
  → apply overrides (exclude → include → merge → reclassify → rename → descriptions)
  → merge reasons file (it is the authoritative reason source; seed-carried reasons are
    a fallback during migration only)
  → POL-1 industry roll-ups
  → POL validators
  → rewrite sectors_seed.py + sectors_seed_backup.py + sector_reasons.json
    (curate is the SINGLE writer of all three; the tide importer defers to it)
```

Policy (validators in M1, content compliant by end of M3):

- **POL-1 Industries are pure roll-ups.** Industry members := union of child themes'
  members (dedup by ticker; curated-first ordering). The two theme-less industries
  (`生技醫療`, `營建地產`) keep their tide rosters. Kills P6 permanently; artifact shape
  and all consumers unchanged.
- **POL-2 Every theme has a thesis.** Per-sector `description` (zh-TW, 1–2 sentences:
  what the theme is AND the inclusion criterion). Member belongs only if the theme is a
  **material driver**.
- **POL-3 No duplicate reasons.** The same non-empty (ticker, reason) string in ≥2
  sectors fails the build — EXCEPT the parent-child case: an industry roll-up member may
  reuse its child-theme reason. Zero-EMPTY reasons becomes a hard failure at end of M3.
- **POL-4 No redundant sectors.** Jaccard ≥ 0.8 between two sectors fails the build —
  EXCEPT parent-child pairs, defined mechanically as: one sector's `group` equals the
  other's `exposure_id`.
- **POL-5 Theme size guideline 4–40 members** → build warning only.
- **POL-6 IDs immutable; merges leave a redirect** in `SECTOR_REDIRECTS` (emitted into
  the seed artifacts); old URLs and un-backfilled episode snapshots keep resolving.

## 4. Decision points (defaults chosen; Willy overrides in PR review)

| # | Decision | Default |
|---|---|---|
| D1 | Far-fetched members | **Purge via overlay** — starting set = audit §2g confidence-**H** rows (~20 pairs); M-confidence rows go to Willy as a review list. No "peripheral member" role field. |
| D2 | `jp_*` sectors | **Merge + redirect** (jp_wafer→silicon_wafer, jp_front_end_equip→front_end_equipment, jp_back_end_equip→pkg_equipment, jp_passive→mlcc; all four targets verified present in the seed). |
| D3 | Stock-page card placement | StockDashboard only; CompanyOverviewPage deferred. |
| D4 | Industry layer | **POL-1 roll-ups.** Visible effect: industry board cards/pages grow (semiconductor ~15 → ~100+ members); avg_change becomes a broader mean. |
| D5 | Raw-dump themes (`textile`, `steel_metals`, `tourism`) | **Reclassify as industries** (ids/URLs unchanged; only `exposure_type`/group placement). |
| D6 | Other merges (audit §2i.4) and renames (§2h) | **Not auto-applied.** M2 ships them as a proposed change-set table; Willy approves line-by-line. Only D1/D2/D5 are pre-approved. |
| D7 | Blanked blurbs (M2.3) leave more members reason-less on SectorPage until M3 lands | Accepted — 73% are already empty; M3 follows immediately. |

---

## M0 — Retire the dead chain (small PR, no data change)

1. Remove the `schedule:` trigger from `.github/workflows/refresh-sectors.yml` (keep
   `workflow_dispatch` + header comment: "inputs deleted in b3fae75; replaced by TKB-008
   M5"). Do NOT delete the workflow file or the dead scripts in this PR — M5 deletes
   them together with their replacement.
2. Drift inventory: read-only script (scripts/ tier) diffing each `tag_registry`
   `kind='sector'` row's members against the current seed; list diverging rows in the PR
   description. (No hand-edited flag exists — sync skips ANY non-empty row,
   `tag_registry.py:265`.) Port deliberate-looking edits into the M1 overlay file.

Acceptance: `grep -n 'schedule:' .github/workflows/refresh-sectors.yml` empty; drift
list in PR description.

## M1 — `curate_sectors.py` + validators + redirect machinery (mechanism only, no content)

Runs entirely off the committed seed — no tide-tw-data needed. Curation inputs start
empty except one smoke entry.

1. **`curate_sectors.py`** (pipelines/libs/shared/scripts): load `sectors_seed.py` (it
   is a Python literal — parse with `ast`, don't import backend code), apply
   `sector_overrides.json` in the order given in §3, merge
   `sector_member_reasons.json`, emit the three artifacts. Log every applied entry.
   Refactor `build_sectors_seed_from_tide.py` so its final stage calls the same curate
   module (extract shared code into `pipelines/libs/shared/src/shared/curation.py`);
   the importer's own `build_reuse_index` (:213) is deleted — reason carry-forward is
   now the reasons file's job. ⚠ The importer refactor is verified via unit tests that
   STUB the tide-read step only — do NOT attempt to run
   `build_sectors_seed_from_tide.py` end-to-end; tide-tw-data does not exist locally
   and the script cannot run without it.
2. **Policy validators** in the curate module, gated by `--enforce` (off by default;
   M2 flips it on — today's content would fail otherwise): POL-3 duplicate non-empty
   (ticker, reason) across sectors → hard fail listing offenders, exempting parent-child
   (industry member reusing its child theme's reason); POL-4 Jaccard ≥ 0.8 → hard fail,
   exempting pairs where one's `group` == the other's `exposure_id`; POL-5 size band →
   warnings. Keep the two existing asserts. Zero-empty-reason check starts as
   "must not exceed baseline 1026" and becomes a hard zero in M3.4.
3. **POL-1 roll-ups** in the curate module, also behind `--enforce` (ships with M2's
   content flip).
4. **Redirect machinery**: curate emits `SECTOR_REDIRECTS: dict[str, str]` into both
   seed artifacts. Backend: `sync_sectors` skips redirected ids; `get_episodes_by_sector`
   (`podcast.py:962`) and `_sector_membership_index` (`podcast.py:1225`) resolve
   old→canonical; responses carry the canonical `exposure_id`. Also IN THIS MILESTONE:
   `sync_sectors` must mark any existing `tag_registry` row whose id appears in
   `SECTOR_REDIRECTS` as hidden (they iterate registry rows filtered by
   `hidden_sector_exposure_ids`; merely skipping redirected ids on upsert would leave a
   stale visible row). Unit-test this with the synthetic fixture (M1.7a).
   NOTE: appending the merged display_name to the target's `aliases` helps
   pipeline text-matching ONLY — it does NOT preserve follows (nothing matches
   subscriptions against aliases); follows are handled in M2.6.
5. **Fix `sync_sectors`**: always overwrite `members` (and description) from the seed.
   Repo is the single source of truth (M0.2 ported drift). Note in `admin_tags.py`'s
   PATCH docstring that member edits last only until next deploy — durable edits belong
   in the overlay.
6. **Schema plumbing for `description`**: `backend/src/schemas/sector.py` (optional
   field) → thread through `/api/episodes/by-sector/{id}` and `/api/sectors` → render in
   SectorPage header (`SectorPage.tsx:171-208`) → add to `EpisodesBySectorResponse`
   (`frontend/src/services/api/podcasts.ts:622`).
7. **Tests**: (a) unit tests for the curate module using a SMALL synthetic seed fixture
   (~5 sectors) covering every override type, both validator exemptions, roll-ups, and
   redirects; (b) invariant pytest over the real committed seed
   (`uv run --package tinboker-shared pytest`): no excluded pair present, every redirect
   target exists, empty-reason count ≤ 1026 baseline; (c) round-trip: `curate_sectors.py`
   with empty inputs and no `--enforce` reproduces the current seed byte-identical
   except the new empty `SECTOR_REDIRECTS = {}`.

Acceptance: round-trip test (7c) green; smoke overlay entry visibly applied on a re-run;
redirect unit test green; after local backend restart with an edited seed,
`curl localhost:5174/api/sectors/board | jq` reflects the change (proves M1.5); backend
`pytest tests/ -v`, frontend `npm run build && npm run lint` green.

## M2 — Full-universe content pass (the actual cleanup)

Read `2026-07-06-sector-universe-audit.md` in full first. One PR; its review IS Willy's
sign-off gate. Everything below runs via `curate_sectors.py` — no tide needed.

1. **Populate the overlay**: `exclude` = all §2g confidence-**H** rows (~20 pairs);
   `merge` = the 4 `jp_*` per D2; `reclassify` = textile/steel_metals/tourism per D5;
   `descriptions` = hand-write for the 4 merge targets + post-purge `sector_hbm`.
2. **Proposed-changes table in the PR description** (NOT applied): §2g M-confidence
   rows, §2i.4 merge candidates (liquid/air cooling, ems/odm/ai_server), §2h renames
   (odm, air_cooling, environmental, cpu_agentic_ai, cxl). One row each: current state,
   proposed action, audit evidence. Willy ticks; a follow-up commit in the same PR
   applies ticked rows.
3. **Blank the tainted blurbs**: add a one-time curate step (`--blank-duplicate-reasons`)
   that empties EVERY occurrence of a (ticker, reason) string appearing in ≥2 sectors
   (excluding parent-child copies) — all ~279 rows. These are company blurbs, not
   theses; even the "original" sector deserves a rewritten reason (M3). This is what
   lets POL-3 pass when `--enforce` flips on below. (D7 accepts the temporary extra
   empties.) Mechanics, to be explicit: the blanking runs inside `curate_sectors.py`
   and lands ONLY in the regenerated seed artifacts — it does not touch
   `sector_member_reasons.json` (still near-empty at this point). The seed's surviving
   non-blanked reasons remain in place until M3.1's `--import-seed-reasons` promotes
   them into the reasons file, which from then on is authoritative. At no point does
   anyone write reasons into `sectors_seed.py` by hand.
4. Flip `--enforce` on permanently (validators + POL-1 roll-ups). Expected: the
   industry≈theme Jaccard failures disappear via the parent-child exemption; if
   `hbm`/`cxl` still trip POL-4 after the purge, purge further per audit §2i.4 (their
   overlap IS the contamination). Re-run curate; commit the three artifacts.
5. Verify `sector_hbm` post-purge has ≥4 members with real memory exposure — if only
   2408/2344 remain, ADD real HBM-chain members via `include` with hand-written reasons
   in the reasons file, or Willy folds the sector into a broader memory theme (his call
   in the PR).
6. **Follows migration (server-side, mandatory)**: follows live behind
   `POST /api/user/subscriptions/tags/{tagName}/toggle` keyed by display-name string
   (`user.ts:143`; locate the backend table via that route's handler). Write a one-off
   migration mapping each renamed/merged sector's old display name → new display name
   (dedupe if a user has both). Acceptance: a user subscribed to 「日本矽晶圓」 is
   subscribed to the merge target's name after deploy.
7. After merge to `develop`: run `backfill_sector_exposures.py --commit`; quote
   before/after counts in the PR.

Acceptance: `audit_sectors.py` re-run quoted in PR: 0 non-parent-child pairs at
Jaccard ≥ 0.8, `sector_hbm` majority real-memory, fan-out max < 8, duplicate-reason rows
= 0; the 4 old `jp_*` urls return the canonical payload
(`curl /api/episodes/by-sector/sector_jp_wafer | jq .exposure_id` →
`"sector_silicon_wafer"`); dev-env spot check `dev.tinboker.com/sector/sector_hbm` has
no 2330; follows migration verified per M2.6.

## M3 — Fill reasons + descriptions (~1300 empty reasons after M2.3, ~98 descriptions)

The old `generate_sector_reasons.py` is DEAD (reads inputs deleted in b3fae75) — do not
run or resurrect it. Write a NEW script; copy only its retry pattern (:82-110) and
secret fallback (:42-53).

1. **`fill_sector_reasons.py`** (pipelines/libs/shared/scripts): reads the committed
   seed (membership + descriptions) and `sector_member_reasons.json`; for every member
   whose reason is missing there, and every sector missing a description, one LLM call
   per sector returning STRICT JSON `{"description": "...", "reasons": {ticker: ...}}`.
   Writes ONLY into `sector_member_reasons.json` and the overlay's `descriptions` —
   never into seed artifacts; the caller then re-runs `curate_sectors.py` to regenerate
   them. Defaults: skip-existing; flags `--only <exposure_id>`, `--overwrite`.
   Model via `SECTOR_REASONS_MODEL` env (default `deepseek/deepseek-v4-pro`).
   One-time bootstrap flag `--import-seed-reasons`: exports the surviving (non-blanked)
   seed reasons into the reasons file first, so the file becomes complete and authoritative.
2. **Prompt requirements**: include the sector's display_name + description; 每檔理由
   必須說明「這檔為什麼屬於**這個**產業/題材」，禁止泛用公司簡介；1–2 句 zh-TW。
   Roll-up members are skipped (they reuse the child-theme reason per POL-3's exemption).
3. **Distinctness check** post-run: identical reason for one ticker across ≥2
   non-parent-child sectors → re-ask once → still identical → write to
   `reasons_flagged.json`, exit 0 (report, don't block).
4. Run: `--import-seed-reasons`, then the default fill, then `--only` re-runs for
   flagged sectors. Re-run curate; commit reasons file + overlay + regenerated
   artifacts. Flip the M1.7 empty-reason invariant to hard zero.

Acceptance: invariant pytest green with zero-empty enforced; `reasons_flagged.json`
empty or listed in the PR; spot-check quoted: 2330's reason differs between
`sector_semiconductor` and every other sector containing it; SectorPage on dev shows
per-member reasons for a previously-empty sector.

## M4 — Stock page: 「所屬產業與題材」

1. Backend `GET /api/sectors/by-ticker/{ticker}` in `tags.py` (mirrors
   `/api/episodes/by-sector/{id}`; keeps sector logic out of stock.py). Reuse
   `_sector_membership_index()` — do NOT re-derive; attach
   `reason_for(exposure_id, ticker)`. Items: `exposure_id, exposure_type, display_name,
   icon_id, color_hex, group, reason`; industries first, themes after, alphabetical
   within. Redis cache_get→compute→cache_set, TTL 1h. Unknown ticker → `{"items": []}`,
   200.
2. Frontend: Zod schema in `validation/schemas.ts` (REQUIRED — new endpoint follows the
   project convention even though legacy sector payloads don't); client in
   `services/api/stocks.ts`; new card in `StockDashboard.tsx` inserted after the
   關鍵數據 card (after line ~287, inside the grid that closes at :289-291). This is a
   NEW component: icon + name chip linking to `/sector/{exposure_id}` with the
   per-sector `reason` as secondary text — copy the reason-rendering pattern from
   `SectorTickerCard.tsx:79-83` (note: `SectorExposureList.tsx` does NOT render reasons;
   it's only a reference for the chip-link + icon layout). Hide the card when `items`
   is empty.

Acceptance: `curl localhost:5174/api/sectors/by-ticker/2330 | jq` → ≥1 item, all
reasons non-empty and pairwise different; `/stock/2330` renders chips that navigate;
`npm run build && npm run lint` + backend `pytest` green.

## M5 — Ongoing maintenance (replaces the dead chain; fully CI-runnable — no tide)

1. Productize `docs/fix-plans/assets/audit_sectors.py` →
   `pipelines/libs/shared/scripts/audit_sector_universe.py` (same metrics + markdown
   report; add `--judge`: one LLM call per sector given description + members + reasons,
   flagging members that fail the stated inclusion criterion — report-only, never
   auto-remove).
2. New workflow `.github/workflows/sector-maintenance.yml`: monthly cron +
   workflow_dispatch; jobs: audit (`--judge`) → `fill_sector_reasons.py` (skip-existing;
   fills any members added since) → `curate_sectors.py --enforce` → invariant pytest →
   PR to `develop` embedding the audit report + added/removed/filled counts.
   **In this same M5 PR** (not earlier): delete `refresh-sectors.yml`,
   `refresh_industry_members.py`, `compile_sector_and_theme_universe.py`,
   `generate_sector_reasons.py`.
3. CI guard: the invariant pytest runs on every PR touching
   `backend/src/data/sectors_seed.py` (hook into the existing pipelines test job).
4. Tide re-imports remain a MANUAL runbook: document at the top of
   `build_sectors_seed_from_tide.py` (obtain tide-tw-data from Willy; run with
   `--tide <dir> --write`; the importer ends by calling curate, so overrides/reasons
   survive re-imports by construction).

Acceptance: `workflow_dispatch` dry-run produces a PR with the audit report embedded and
zero unexplained membership churn; a seed-touching PR without green invariants fails CI;
running the workflow twice back-to-back produces a second PR with no reason churn.

---

## Out of scope

- Renaming any live `exposure_id` (redirects only, POL-6).
- Retrofitting Zod onto legacy sector payloads (only the new M4 endpoint gets Zod).
- The 12-member cap on SectorPage's grid (`SectorPage.tsx:220-240`).
- Market-cap-weighted composite index (performance stays a simple mean).
- Rebuilding tide-tw-data itself or replacing it as the raw-import source.
- Deleting dead scripts/workflow before M5.

## Verification protocol (every milestone)

Per `docs/ai-ops/20-judgment-rubrics.md` R2: quoted command output in each PR —
backend `pytest tests/ -v`, frontend `npm run build && npm run lint`, the milestone's
`curl`/`jq` checks, `uv run --package tinboker-shared pytest` for pipelines changes,
and re-running the audit script after any membership change (quote the headline table).
Deploy path is git → PR → CI only; post-merge verify on
`https://dev-api.tinboker.com` + `dev.tinboker.com/sector/...`.
