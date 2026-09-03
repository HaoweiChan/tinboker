# Lessons Log

> Append-only during normal work; newest first. Entry format and routing rules:
> [40-maintenance-protocol.md](40-maintenance-protocol.md) §4. Consolidate at 40 active
> entries or ~250 lines (§5). Entries below dated 2026-07-03 are the founding seed —
> real findings from the session that built `docs/ai-ops/`, kept as format examples.

---

## 2026-09-03 — CLAUDE.md described three GCP services that no longer exist
- **Situation:** needed to reach `podcast_db` to run a backfill. CLAUDE.md:98 said
  "Cloud SQL `34.14.119.47:5432/podcast_db`", so I hunted for a Cloud SQL instance and a
  proxy binary, then burned a fail2ban lockout probing SSH usernames to find the host.
- **Wrong assumption / failure:** there is no Cloud SQL. `gcloud sql instances list` is
  empty across all 5 projects on the account and `describe tinboker-db` 404s;
  `gcloud firestore databases describe --database=graphfolio-db` returns NOT_FOUND and
  `gcloud storage ls gs://graphfolio-articles` 404s. `podcast_db` is a `postgres:16-alpine`
  container on the VPS bound to `127.0.0.1:5433` (`docker ps` on 152.53.136.182), and the
  media tree is `/srv/tinboker-media` served by Caddy — `graphfolio-articles` survives only
  as a directory name (`service/gcs_storage_service.py:53` MEDIA_BUCKETS).
- **Rule:** A migration is not finished until the docs that name the old infrastructure
  are changed in the same PR; when a doc names a hosted resource, verify it with a
  `describe`/`ls` before building on it, because a stale name costs more than a missing one.
- **Status:** logged; CLAUDE.md:25 and :96–98 fixed 2026-09-03 (Tier A, evidence above).

## 2026-07-05 — FinMind silent-zero signature struck a third time (/topics blank)
- **Situation:** /topics bubbles empty; `/api/sectors/performance` served all-zero
  `trading_value_windows_twd` for 139 exposures while heat/returns were healthy.
- **Wrong assumption / failure:** assumed the sector-classification work or a missing
  API key; actually (a) the recompute's ~1,740 per-ticker FinMind calls (580 members × 3
  datasets) self-exhaust the 1,500/hr budget, (b) the Yahoo fallback was structurally
  dead — `import yfinance` inside `list_yahoo_tw_daily_range` (`finmind_service.py:48`)
  ImportError-returns `[]` and **yfinance was never in the backend image**, (c) truthy-empty
  `{"1":{},...}` results pass `if vals:` and cache for a day (`podcast.py:1628`).
  Same signature previously fixed in `090bb92` and `317233f`.
- **Rule:** a fallback that can `except ImportError: return []` must have its dependency
  proven present in the deployed image (`docker exec <c> python -c "import x"`), and
  empty-shaped results must never be cached at full TTL. When a FinMind-fed field goes
  all-zero, check the budget counter and the fallback's import FIRST, not the data model.
  Full diagnosis: `docs/fix-plans/2026-07-05-topics-bubbles-zero-trading-value.md`.
- **Status:** logged; fix plan handed to implementer 2026-07-05.

## 2026-07-04 — Root AGENTS.md reconciled into a real symlink, not just a "canonical" note
- **Situation:** User decided root `AGENTS.md` should be a literal symlink to `CLAUDE.md`
  (closing the open task from `60-letter-to-future-sessions.md`), after confirming that
  `AGENTS.md`'s unique content (TODO.md task workflow, financial-content rules, SEO
  structured-data rules) should be preserved elsewhere first, not silently dropped.
- **Wrong assumption / failure:** None on the top-level decision — this was a deliberate
  migration, not a discovered error. Verified before deleting: `TODO.md` and
  `scripts/sync_todo_to_github.py` are real and actively used (git history shows `TKB-001`
  shipped through the exact workflow AGENTS.md described), so that content was genuinely
  load-bearing, not stale boilerplate. BUT the first migration pass itself was incomplete —
  a fresh-context T5 review (per §3, required for CLAUDE.md edits) caught two real misses
  on the first attempt: the `scripts/` implementation-boundary note (use for dev
  automation/GitHub sync, don't put production pipeline logic there) was dropped entirely,
  and the per-tier "don't place ingestion jobs in frontend/" / "don't place long-running
  pipelines in backend request handlers" boundary lines were migrated as rules content but
  not as the explicit boundary statements. Both fixed same-day (see Status). Two other
  original Do-Not items ("put secrets in code", "break the deploy flow") were intentionally
  NOT re-added as separate rules — verified they're already subsumed by CLAUDE.md's
  existing "Do Not" secrets rule (broader: any secret value, not just code) and its
  Deployment section (states the develop→dev/main→staging/tag→prod flow directly).
- **Rule:** Before honoring a "just delete/symlink this file" instruction, check whether
  the file has content that exists nowhere else — a symlink that drops real, active
  process documentation is a regression even when explicitly requested; surface it first.
  Second rule, from the T5 miss: a migration claiming "every piece was moved" needs a
  section-by-section diff against the original, not a scan for the pieces you remember
  being interesting — an adversarial fresh-context reviewer found gaps the author didn't.
- **Status:** promoted → content migrated to `docs/workflows/task-management.md` (TODO.md
  workflow + `scripts/` boundary), `docs/agents/podcast-domain.md` § Financial content
  rules, `frontend/AGENTS.md` § SEO conventions + Boundary, `backend/AGENTS.md` § Stability
  & External API Rules + Boundary (+ pointer from `pipelines/AGENTS.md`). CLAUDE.md
  read-first map got one new row (task-management.md); its "AGENTS.md has drifted" note was
  corrected to describe the symlink. Root `AGENTS.md` is now `AGENTS.md -> CLAUDE.md`
  (verified: `readlink AGENTS.md` resolves to `CLAUDE.md`, and since it IS the same inode
  content is trivially identical — that's a symlink-correctness check, not evidence content
  was preserved; the section-by-section diff is what verified preservation). Old AGENTS.md
  content is fully recoverable from git history if anything was still missed.

## 2026-07-03 — Founding session's open-tasks list gets a follow-up pass
- **Situation:** User pointed at merged PR #415 and asked what it describes that isn't
  implemented yet. Walked the "Open tasks" list in
  [60-letter-to-future-sessions.md](60-letter-to-future-sessions.md) and verified each
  against current code, not the letter's 2026-07-03 snapshot.
- **Wrong assumption / failure:** Two items on that list were stale by the time they were
  read. (1) `backend/src/routers/episodes.py` docstrings said "CDN Cache: 30 minutes" in
  three places (lines 42, 122, 160) but the decorators disagree with each other:
  `/recent` uses `@cdn_cached(s_maxage=600...)` = 10 min (episodes.py:27), while
  `/by-ticker/{ticker}` and `/{episode_id}` use `@cdn_cache_podcast` = `CacheProfile.PODCAST`
  = 1 hour (`backend/src/cache/cdn_cache.py:48`). All three said "30 minutes" — none were
  right. (2) The "inconsistent" GCP service-account path in `docs/infra-runbook.md` was
  NOT actually inconsistent — `/app/gcp-service-account.json` is the container-internal
  path and `/app/backend/gcp-service-account.json` is the VPS host path, per the volume
  mount `./gcp-service-account.json:/app/gcp-service-account.json:ro` in
  `backend/docker-compose.multi.yml:42`. The doc just never labeled which was which.
- **Rule:** A "known open task" written by a prior session is a claim about that day's
  state, not a standing fact — re-verify against current code before either fixing it or
  reporting it as still-open (same rule as R2/lessons routing, applied to task lists too).
- **Status:** promoted → episodes.py docstrings fixed (3 sites, now say 10 minutes / 1
  hour matching their actual decorator); infra-runbook.md § 2.1 now labels host vs.
  container path explicitly. Remaining open items (secret rotation, AGENTS.md
  reconciliation, backup cleanup/gitignore, session-start hook) surfaced to the user —
  they require manual action or Tier C/user-decision per maintenance protocol §1, not a
  code fix.

## 2026-07-03 — Docs drift silently; code is the only tiebreaker
- **Situation:** Consolidating cache-TTL documentation for `/api/episodes/recent`.
- **Wrong assumption / failure:** `docs/agents/devops-infra.md` claimed a 5-min CDN TTL;
  CLAUDE.md claimed 10 min. Code says `@cdn_cached(s_maxage=600, max_age=120, stale=300)`
  (`backend/src/routers/episodes.py:27`) — CLAUDE.md was right, the domain doc stale, and
  even the endpoint's own docstring says "30 minutes" (also stale).
- **Rule:** When two docs disagree — or a doc disagrees with intuition — read the code
  before writing anything; cite `file:line` in whichever doc you fix.
- **Status:** promoted → docs fixed (devops-infra.md, infra-runbook.md § Cache TTLs); rule
  reflected in CLAUDE.md header ("trust the doc over this file, trust code over docs").

## 2026-07-03 — A secret was pasted into a repo doc despite a rule against it
- **Situation:** Coverage audit of auth docs found a live `DEV_BYPASS_TOKEN` value
  committed in plaintext at `docs/agents/auth-admin.md:62`, with a false note claiming
  the value "lives in CLAUDE.md".
- **Wrong assumption / failure:** the rule "never paste the token into docs" existed
  (CLAUDE.md, qa-flow.md) but nothing checked it; the leak sat in git history unnoticed.
- **Rule:** Secrets are referenced by Secret Manager name only, never by value — and any
  security-relevant review should `grep` for known secret shapes, not just trust rules.
  The token remains in git history: treat it as compromised until rotated.
- **Status:** logged; doc fixed 2026-07-03; token rotation recommended to user.

## 2026-07-03 — Two "sources of truth" for agent instructions had quietly diverged
- **Situation:** CLAUDE.md stated "`AGENTS.md` is symlinked here"; `AGENTS.md` is
  actually a separate 6.9 KB file with different content.
- **Wrong assumption / failure:** a weak model reading either file would assume it read
  both. Instructions in one were invisible to tools reading the other.
- **Rule:** Never claim two files are identical/symlinked without `ls -la` proof; when
  instruction files fork, declare one canonical (done: CLAUDE.md + docs/ for Claude
  sessions) and mark the other as legacy in its header. Full reconciliation of AGENTS.md
  is an open task.
- **Status:** logged; canonical-file note added to CLAUDE.md 2026-07-03.
