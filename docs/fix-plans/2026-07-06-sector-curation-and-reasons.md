# Fix plan v3 — sector taxonomy: Postgres as source of truth, reasons fill, stock-page membership

> Status: v3, 2026-07-06. Tracked as **TKB-009** in `TODO.md`.
> v1 patched symptoms → v2/v2.1 fixed grouping structurally with git-as-truth → **v3
> changes the source of truth to Postgres** after (a) Willy's IP requirement — this repo
> is PUBLIC and the curated taxonomy + rationale text are proprietary, and (b) a
> methodology research pass whose sources converge on DB-as-truth for data that is
> served live by an API and updated regularly (see §1). Research notes with citations:
> `docs/fix-plans/pg-governance-research.md`, `docs/fix-plans/taxonomy-governance-research.md`.
> Audience: implementing agents (Sonnet/Opus/Codex). Follow literally; one milestone =
> one PR, in order. Companion evidence docs (unchanged from v2):
> `2026-07-06-grouping-logic-spec.md`, `2026-07-06-sector-universe-audit.md`,
> `assets/audit_sectors.py`.

---

## 1. The architecture decision (locked — do not relitigate)

**Postgres `tag_registry` is the single source of truth for the sector taxonomy**
(structure, membership, per-member reasons, descriptions). Git carries the engine code
and a synthetic test fixture only. Rationale, from the research:

- dbt's own guidance names our exact shape as the anti-pattern for data-in-git:
  data that is *"regularly updated"* or that *"other systems need to update"* or served
  at runtime belongs in *"a centralized database or API"*.
- GICS/ICB/TRBC (the real-world analogues of this taxonomy) all separate **structural
  change** (rare, versioned, dated, with published rationale) from **membership change**
  (frequent, low-ceremony annual re-reviews) — two tempos, one database.
- The M0 drift disaster (42 stale rows, 46 divergent member lists served for weeks) was
  caused by **two independently-writable truths** (seed + admin edits), the exact
  failure mode every hybrid-pattern source flags. v3 removes the second truth entirely.
- IP: the proprietary dataset lives only in the private prod DB and private backups.
  NOTE: the pre-v3 taxonomy is already public in git history — that snapshot is
  unrecoverable; v3 protects the future increments (the M3 reasons corpus and all
  later curation), which is where the IP accrues.

**Governance rules (from the research, kept deliberately minimal — no governance
theater):**

- **G1 — One write path.** All taxonomy mutations go through the authenticated admin
  API, which runs the POL validators transactionally and rejects violations
  (validate-on-write replaces CI-on-PR). Nothing else writes: no startup sync
  overwrite, no scripts writing artifacts, no direct psql as routine practice.
- **G2 — Trigger-based audit table.** Every INSERT/UPDATE/DELETE on `tag_registry` is
  captured by a Postgres trigger into `tag_registry_audit` (JSONB before/after row
  image, actor, timestamp, note). Catches ALL write paths including manual psql.
  "As of" questions are answered from the audit table; the live table stays
  current-state-only. No temporal/SCD machinery.
- **G3 — Two tempos (GICS-style).** Structural changes (sector add/remove/merge/
  reclassify) bump a `taxonomy_version` row and append a dated changelog entry with a
  one-line rationale. Member/reason/description edits are low-ceremony (audit trail
  only).
- **G4 — Survivorship: manual beats machine.** Rows/fields last written by a human
  admin (`updated_by` not in the bot allowlist) are NEVER overwritten by an LLM bulk
  pass unless the operator passes an explicit `--force`. Write this check into the bulk
  endpoint, not into the client scripts.
- **G5 — Draft → publish for bulk writes.** LLM bulk output lands as a draft (dry-run
  report reviewed by Willy, then an explicit publish call). Human single-row admin
  edits publish directly.
- **G6 — One-way private export.** A scheduled job dumps the taxonomy (JSON + pg_dump)
  to the private GCS bucket for diffable snapshots and disaster recovery. Export is
  never a write path back (the two-writable-paths failure mode). Nothing
  taxonomy-shaped is ever committed to this public repo again — including future audit
  reports (they go to GCS or the PR-free maintenance report path).

## 2. Current state (post-M2, PR #436) and what changes

Shipped so far: **M0** (dead weekly chain retired; drift inventory), **M1** (curation
engine `curate_sectors.py` + validators + redirects + authoritative sync),
**M2** (content pass: 21 purges, 4 `jp_*` merges with redirects, HBM rebuilt, industry
roll-ups, blurbs blanked, enforcement in CI, Firestore follows migration). PR #436
merges as-is — its cleaned seed becomes the **initial import payload** for the DB.

What v3 changes about the v2 architecture:

| v2 (git-as-truth) | v3 (Postgres-as-truth) |
|---|---|
| `sectors_seed.py` canonical; sync overwrites DB at startup | `tag_registry` canonical; seed demoted to empty-DB bootstrap fixture; startup sync-overwrite retired (M2.5.4) |
| POL validators run in CI on the committed seed | Validators run transactionally in the admin write endpoint (G1); CI keeps engine unit tests on a synthetic fixture only |
| Reasons in `sector_reasons.json`, served by `reason_for()` | Reasons live in `tag_registry.members[].reason` JSONB; `reason_for()` reads the registry (M2.5.5) |
| Curation via committed overlay files + PR review | Curation via admin API (single edits) and draft→publish bulk endpoint (LLM passes); review = audit trail + dry-run reports (G2/G5) |
| M5 monthly workflow opens PRs in this public repo | Maintenance runs against the DB from a private context; reports go to private storage (M5) |
| Admin PATCH edits are temporary until next deploy | Admin edits are durable and first-class (G4 protects them) |

Everything already true stays true: episode snapshots + `backfill_sector_exposures.py`
semantics, `exposure_id` immutability + `SECTOR_REDIRECTS` (redirect map moves into the
DB as registry rows' `redirect_to` or a small table — implementer picks the smaller
diff, plan assumes a `redirect_to` column), the follows display-name coupling, the
`/api/sectors/*` serving endpoints, `_sector_membership_index()`.

## 3. Decision points (defaults; Willy overrides in PR review)

| # | Decision | Default |
|---|---|---|
| D1 | Where does the M3 LLM fill run? | Operator-run from a dev machine against the admin API (needs `SECTOR_REASONS_MODEL` + OpenRouter key + admin token). Not public-repo CI. |
| D2 | Redirect storage | `redirect_to` column on `tag_registry` (nullable FK-ish string). |
| D3 | Bot identity for G4 | `updated_by` values: `bot:reasons-fill`, `bot:import`, `admin:<email>`; survivorship checks the prefix. |
| D4 | Export cadence (G6) | Weekly + on-demand after bulk passes; GCS bucket `graphfolio-articles` sibling path or a new private bucket — implementer confirms bucket privacy before first export. |
| D5 | M2's review-queue items (9 M-confidence purges, 2 merge clusters, 5 renames in PR #436 body) | Applied post-migration via the admin API once Willy ticks them — no longer via overlay files. |

---

## M2.5 — Truth migration (the v3 core; one PR + one operational import)

Backend + one pipelines touch. No taxonomy content changes beyond the import itself.

1. **Schema** (idempotent DDL in `backend/src/database/postgres.py`, following the M1
   description-column pattern):
   - `tag_registry_audit` (id, tag_registry_id, exposure_id, action, actor, note,
     before JSONB, after JSONB, at timestamptz) + the Postgres trigger on
     `tag_registry` capturing INSERT/UPDATE/DELETE (pattern: Postgres wiki
     `audit_trigger_91plus`, simplified to JSONB).
   - `taxonomy_changelog` (id, version, dated entry, rationale, actor) + a
     `taxonomy_version` counter (single-row table or max(version)).
   - `tag_registry.redirect_to` column (D2); `updated_by` semantics per D3.
2. **Write API** (new router `backend/src/routers/admin_taxonomy.py`, admin JWT like
   the existing admin endpoints):
   - `PUT /api/admin/taxonomy/sectors/{exposure_id}` — single-sector upsert
     (structure/members/reasons/description). Runs POL validators against the
     would-be state of the WHOLE taxonomy (load registry, apply change in memory,
     validate — reuse `shared/curation.py` validator functions by extracting them into
     a backend-importable module or duplicating the ~100 lines; implementer picks,
     duplication is acceptable here to avoid a cross-tier import).
     Rejects violations with the offender list in the 422 body.
   - `POST /api/admin/taxonomy/bulk` — bulk draft: accepts a full or partial taxonomy
     payload, validates, stores as draft (status column or a `taxonomy_drafts` row —
     single-table status column preferred per research), returns a diff report
     (added/removed/changed counts + samples).
   - `POST /api/admin/taxonomy/bulk/{draft_id}/publish` — applies the draft
     transactionally, honoring G4 survivorship (skip human-authored fields unless
     `force=true`), bumps changelog for structural changes (G3).
   - `GET /api/admin/taxonomy/audit?exposure_id=...` — read the audit trail.
3. **One-time import**: operator script (scripts/ tier is fine, it calls the API)
   pushing the post-#436 seed (99 sectors incl. redirects) through the bulk
   draft→publish path with actor `bot:import`. This is changelog version 1.
4. **Retire the old write paths**: `sync_sectors` no longer overwrites from seed; it
   becomes bootstrap-only (`if tag_registry has zero kind='sector' rows → seed it from
   the fixture, log loudly`). Delete the seed-regeneration writers from the runtime
   path: `curate_sectors.py` survives ONLY as a dev tool operating on the fixture, or
   is deleted with its logic absorbed into the backend validators — implementer keeps
   whichever is the smaller diff. The tide importer's runbook gains: "re-imports are
   drafted through POST /api/admin/taxonomy/bulk, never committed to git".
5. **Read-path swap**: `reason_for(exposure_id, ticker)` and description resolution
   read from `tag_registry` (registry already reaches the relevant services;
   `sector_reasons.json` is deleted). Redirect resolution reads `redirect_to` instead
   of the seed's `SECTOR_REDIRECTS`. Pipelines' offline fallback
   (`sectors_seed_backup.py`) is frozen with a header comment "stale-acceptable
   emergency fallback; truth is the API" — do not delete (ingest must survive API
   downtime).
6. **G6 export job**: small script + schedule (VPS cron via existing infra patterns or
   GitHub Actions in a PRIVATE context — NOT this repo's public Actions) dumping
   taxonomy JSON + audit table to private GCS. Verify bucket is not public before
   first write.
7. **Public-repo hygiene**: the curation overlay JSONs stop being the mechanism
   (already-public content stays in history; files get a deprecation header). CI keeps
   the curation-engine unit tests on the synthetic fixture; the real-seed invariant
   test is retired (its job moved into validate-on-write).

Acceptance: audit trigger captures a psql UPDATE (test via a unit/integration test with
the trigger installed); single-sector PUT rejects a POL violation with offenders listed;
bulk draft→publish round-trips the full 99-sector payload byte-equal (export and
compare); after import + deploy, `/api/sectors/board` serves from registry with zero
behavioral diff vs pre-migration (compare responses); `sync_sectors` on a non-empty DB
writes nothing (log assertion); backend `pytest` green; export lands in GCS and the
bucket is confirmed private.

## M3 — Reasons + descriptions fill (~1,870 reasons, ~94 descriptions) — via the API

1. `fill_sector_reasons.py` (pipelines scripts, operator-run per D1): reads current
   taxonomy from `GET /api/sectors/universe` (or admin GET), finds members with empty
   reasons + sectors with empty descriptions, one LLM call per sector returning strict
   JSON `{"description": "...", "reasons": {ticker: reason}}`, retries ×3, model from
   `SECTOR_REASONS_MODEL` (default `deepseek/deepseek-v4-pro`), OpenRouter key
   env→gcloud fallback (copy the pattern from the dead `generate_sector_reasons.py:42-53`;
   never run that script). Skips roll-up members (industry members reuse the child-theme
   reason server-side — the validator's parent-child exemption).
2. Prompt: sector display_name + description in context; 每檔理由必須說明「這檔為什麼
   屬於**這個**產業/題材」，禁止泛用公司簡介；1–2 句 zh-TW。
3. Output goes to `POST /api/admin/taxonomy/bulk` as a draft; the returned diff report
   + a sampled reasons sheet go to Willy; publish only after his OK (G5). Distinctness
   check before submission: identical reason for one ticker across ≥2 non-parent-child
   sectors → re-ask once → still identical → include in the report as flagged, publish
   anyway (server tolerates; validator blocks only exact-duplicate strings — flagged
   pairs get manual review).
4. After publish: zero-empty-reasons becomes a standing validator warning→error switch
   in the write path (server setting), so future member additions without reasons are
   rejected at write time.

Acceptance: post-publish `GET`-based audit shows 0 empty reasons / 0 empty
descriptions; 2330's reasons differ across its sectors; SectorPage on dev renders
reasons for a previously-empty sector; audit table shows the bulk pass under
`bot:reasons-fill`.

## M4 — Stock page 「所屬產業與題材」 (unchanged from v2.1 except the reason source)

1. `GET /api/sectors/by-ticker/{ticker}` in `tags.py`: reuse
   `_sector_membership_index()`; attach reason/description from the registry (NOT from
   `sector_reasons.json`, which is gone). Items: `exposure_id, exposure_type,
   display_name, icon_id, color_hex, group, reason`; industries first; Redis TTL 1h;
   unknown ticker → `{"items": []}`, 200.
2. Frontend: Zod-validated client + a new card in `StockDashboard.tsx` after the
   關鍵數據 card (insertion after ~:287, grid closes :289-291); chip links to
   `/sector/{exposure_id}` with the per-sector reason as secondary text; copy the
   reason-rendering pattern from `SectorTickerCard.tsx:79-83` (note:
   `SectorExposureList.tsx` renders NO reasons — layout reference only). Hide when
   empty.

Acceptance: `curl /api/sectors/by-ticker/2330 | jq` → ≥1 item, reasons non-empty and
pairwise different; `/stock/2330` renders; `npm run build && npm run lint` + backend
`pytest` green.

## M5 — Ongoing maintenance (private, PR-free)

1. Productize `docs/fix-plans/assets/audit_sectors.py` →
   `audit_sector_universe.py` reading from the API (not the seed), plus `--judge`
   (one LLM call per sector flagging members that fail the stated inclusion criterion
   — report-only).
2. Monthly job (private context per M2.5.6 — VPS cron or private Actions): audit
   (`--judge`) → fill (skip-existing) as a DRAFT → notify Willy with the report +
   draft id; nothing publishes without his call. Report artifact → private GCS.
   Weekly G6 export runs on its own schedule.
3. Membership refresh from FinMind (the old `refresh_industry_members.py` purpose)
   returns later as another drafted bulk pass — out of scope here; note it in the
   runbook as the pattern.
4. Delete from this repo: `refresh-sectors.yml`, `refresh_industry_members.py`,
   `compile_sector_and_theme_universe.py`, `generate_sector_reasons.py` (all dead), and
   the real-seed CI invariant if not already retired in M2.5.7.

Acceptance: one full dry-run of the monthly job produces a report + an unpublished
draft; a second run produces no new draft content (skip-existing verified against the
DB); the dead files are gone and CI is green.

---

## Out of scope

- Rewriting public git history to scrub the already-published taxonomy (impractical;
  accepted loss — see §1).
- Renaming any live `exposure_id` (redirects only).
- Zod retrofit on legacy sector payloads; SectorPage 12-member cap; market-cap
  composite index.
- Multi-user editorial workflow / approval committees (governance theater at this
  scale — revisit only if the team grows).

## Verification protocol

Per `docs/ai-ops/20-judgment-rubrics.md` R2: quoted command output in each PR —
backend `pytest tests/ -v` (use `uv run --python 3.12`, the default env breaks on
3.14), pipelines `uv run --package tinboker-shared --with pytest pytest`, frontend
`npm run build && npm run lint`, plus each milestone's `curl`/`jq` checks. For
migration steps that touch prod data (M2.5.3 import, M3 publish): dry-run report
reviewed BEFORE the mutating call, and a G6 export taken immediately before as the
restore point. Deploy path is git → PR → CI only; post-merge verify on
`https://dev-api.tinboker.com`.
