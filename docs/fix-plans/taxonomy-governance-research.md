# Taxonomy Governance Research — TinBoker Sector/Theme Taxonomy

Context: ~100 proprietary curated sectors, member stocks, per-member rationale text, Taiwan
market. Solo maintainer, ~monthly LLM-assisted bulk updates + occasional manual fixes,
served live by an API, must not live in public git. Deciding: DB-as-truth vs data-as-code
(git), and what change-management methodology to borrow.

---

## 1. How the financial industry governs classification taxonomies

**GICS (MSCI/S&P Dow Jones Indices)**
- Structure: 11 sectors → 25 industry groups → 74 industries → 163 sub-industries.
  Classification driven primarily by revenue (>60% threshold for principal business
  activity), with earnings/market perception as secondary signals.
  Source: https://www.msci.com/indexes/index-resources/gics
- **Annual structural review cycle**, changes announced far in advance of the effective
  date:
  - 2018 revision: announced 2017-11-15, effective 2018-09-28 EOD ET (~10 months notice).
  - 2023 revision: announced 2022-03-31, effective 2023-03-17 EOD ET (**~1 year notice**).
  Source: https://press.spglobal.com/2022-03-31-S-P-DOW-JONES-INDICES-AND-MSCI-ANNOUNCE-REVISIONS-TO-THE-GLOBAL-INDUSTRY-CLASSIFICATION-STANDARD-GICS-R-STRUCTURE-IN-2023 ;
  https://penserra.com/gics-revision-everything-wanted-revisions/
- Each structural change ships as a **named, dated methodology document** (versioned PDF)
  plus a plain-language change summary/rationale, distributed to clients (index funds,
  data vendors) so they can re-map holdings before the effective date.
  Source: https://www.spglobal.com/spdji/en/documents/methodologies/methodology-gics.pdf
- Individual company reclassifications (not structural changes) happen more frequently
  and are communicated per-name, separate from the annual structural cycle.

**ICB (FTSE Russell / LSEG)**
- Current version: ICB v5.0 (March 2026 Ground Rules).
  Source: https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/icb-ground-rules.pdf
- Governance body: **FTSE Russell Industry Classification Advisory Committee**
  recommends structural changes; **FTSE Russell Governance Board** approves.
  Source: https://www.lseg.com/en/ftse-russell/industry-classification-benchmark-icb
- Hard rule, direct quote: *"Any changes to the ICB structure (subsectors, sectors,
  supersectors or industries) shall take place with a minimum of six months' notice."*
  Changes are motivated by **long-term structural trends, not temporary fluctuations**.
  IPOs get an expedited path: minimum T+2 notice for classifying a new listing.
  Source: https://research.ftserussell.com/products/index-notices/home/getmethodology/?id=2609359
- Published a formal **challenges and appeals policy** — constituents/users can dispute a
  classification through a defined process.
  Source: https://www.lseg.com/content/dam/ftse-russell/en_us/documents/policy-documents/icb-challenges-and-appeals.pdf
- Major re-platform precedent: ICB integrated Russell Global Sectors in 2019, with the
  implementation date **extended** (originally earlier, pushed to 2019-07-01) — shows even
  majors slip/extend deadlines rather than rush a taxonomy migration.
  Source: https://www.marketsmedia.com/ftse-russell-extends-implementation-of-new-industry-classification-benchmark/

**TRBC (LSEG, formerly Refinitiv/Thomson Reuters)**
- Structure: 10 economic sectors → 28 business sectors → 54 industry groups → 136
  industries → 837 activities (deeper than GICS/ICB).
  Source: https://en.wikipedia.org/wiki/The_Refinitiv_Business_Classification
- Versioning is **named-edition**, not continuous: RBSS 2004 → TRBC 2008 → TRBC 2012 →
  TRBC 2020 — four major editions in ~16 years. Structural change is rare/deliberate;
  day-to-day maintenance is a different, higher-frequency track.
  Source: https://en.wikipedia.org/wiki/The_Refinitiv_Business_Classification
- Day-to-day maintenance: **every company reviewed at least annually**; ~50,000+ companies
  reviewed per year by a dedicated content-operations team using filings, news, and
  corporate-action feeds as triggers for re-review (not just calendar-driven).
  Source: https://www.lseg.com/en/data-analytics/financial-data/indices/trbc-business-classification

**Essence a one-person shop can copy cheaply (this is the reusable pattern, not the
bureaucracy):**
1. **Separate two change tempos explicitly**: rare *structural* changes (add/remove/split
   a sector) vs frequent *membership* changes (move a stock, tweak rationale text). Don't
   govern both the same way.
2. **Any structural change gets a dated, versioned changelog entry with rationale** —
   even if it's one paragraph in a CHANGELOG, not a press release.
3. **Give structural changes a landing runway** (their "6 months" / "1 year" scaled down
   to "give it a version bump and a date, don't silently mutate a category identity").
4. **A single named edition/version per meaningful revision** (their "TRBC 2020" ↔ your
   "taxonomy vN") so any consumer (your own API clients, your future self) can say "which
   version was this rationale written against."
5. A lightweight **correction/appeal channel** — for a solo shop this is just "how do I
   flag and fix a wrong classification" documented as a runbook, not a committee.

---

## 2. MDM core practices at tiny scale

- **Golden record** concept: one authoritative record per entity, built via
  ingest → match → **survivorship** (pick the winning value when sources conflict) →
  validate → maintain. The valuable part for a solo shop is just "survivorship rule" =
  decide *in advance* who wins when your LLM bulk-update and your manual fix disagree
  (manual should always win — write that down once).
  Source: https://www.verdantis.com/material-mastery-crafting-golden-records/ ;
  https://profisee.com/blog/what-is-a-golden-record/
- **Stewardship**: someone (even if it's the same solo person wearing a different hat) is
  explicitly accountable for judgment calls on ambiguous classifications. Worth keeping
  as a *documented convention* (e.g., a REVIEW.md checklist), not a role or a tool.
  Source: https://www.latentview.com/blog/mdm-golden-record/
- **Automation + human-in-the-loop hybrid** is explicitly recommended for small teams:
  automated rules do the bulk cleansing/validation, humans approve only flagged
  exceptions. This maps directly onto "LLM does bulk monthly update, human reviews the
  diff before it ships" — which is already close to what you'd do naturally.
  Source: (search synthesis, MDM golden-record lightweight-maintenance sources above)
- **What's enterprise theater for a solo maintainer:** a dedicated governance committee,
  formal RACI matrices, multi-system reconciliation (you have one system), a data-quality
  scorecard dashboard, and change-approval workflows with multiple human approvers.
  Explicit finding: *"Data governance frameworks are valuable at scale, but for a
  two-person ops team, they add process overhead without proportional benefit."* Also:
  *"governance theater"* named directly as a failure mode — the appearance of governance
  without substance (e.g., a policy doc nobody follows).
  Source: (bluent.com / cleansmartlabs.com search synthesis — CXO governance-vs-MDM
  overhead discussion)
- **What IS worth it even solo:** a golden-record/survivorship rule (conflict resolution
  policy), a lineage trail (which run/prompt/commit produced this row), and validation
  gates before publish (schema + sanity checks). These map 1:1 onto version control +
  CI-style checks — you get MDM's real value from git/DB tooling you already run, no
  MDM platform needed.

---

## 3. Data-as-code vs database-as-truth

**dbt seeds (data-as-code, git-native) — practitioner consensus on when appropriate:**
- Best for: **small, stable, infrequently-changing** reference data, tightly coupled to
  a single codebase, single-writer, wants code review + diff history for free.
  Source: https://dagster.io/guides/working-with-dbt-seeds-quick-tutorial-critical-best-practices
- Explicit anti-patterns (all apply increasingly to TinBoker's taxonomy as it scales):
  - **Size**: seeds become inefficient past "5–10MB or tens of thousands of rows" — git
    diffs and clone times degrade. ~100 sectors × members is comfortably under this, so
    size is not a blocker today.
  - **Update frequency**: "when the dataset is updated regularly... seeds require manual
    updates, which breaks automation." Monthly LLM bulk updates sit right at the edge of
    what seeds tolerate gracefully — still fine if the update *is* a PR/commit, not fine
    if it needs a live API write path.
  - **Collaborative write access**: "seeds are read-only once loaded... if other systems
    need to update the data, seeds introduce version drift. Use a centralized database or
    API for shared data instead." **This is the decisive criterion for TinBoker**: the
    taxonomy is served live by an API, i.e., there's a runtime write/read consumer, not
    just a build-time compile step. That's the textbook trigger to prefer a DB.
  Source: https://oneuptime.com/blog/post/2026-01-28-dbt-seeds-and-sources/view ;
  https://mbvyn.medium.com/understanding-dbt-seeds-and-sources-c5611be17d32
- Best practice if you do keep any seed-like csv: "if the seed is meant to replicate an
  authoritative source, cite that source explicitly" — i.e., never let a copy silently
  become an ambiguous second source of truth.

**Dolt (git-for-data, DB with native version control):**
- Positioned explicitly for: *"data that changes over time and needs to be audited,
  reviewed, or rolled back: application configuration, feature flags, **curated reference
  datasets**, and data pipelines where a bad import needs to be undone cleanly."* This is
  close to a direct match for TinBoker's use case description.
  Source: https://github.com/dolthub/dolt ; https://www.dolthub.com/docs/introduction/getting-started/git-for-data/
- Mechanism: SQL database queryable normally, but every write is a commit; branch/merge/
  diff/push/pull work like git, diffs are **cell-level not text-level**, full history
  queryable via SQL system tables (`dolt_diff`, `dolt_history_*`, etc.).
  Source: https://betterstack.com/community/guides/databases/dolt-git-version/
- Self-hostable (DoltLab) or managed (Hosted Dolt) — relevant to the "must not be public
  git" constraint: a private Dolt remote/DoltLab instance gives git-style diff/audit
  without ever touching GitHub/public VCS.
  Source: https://www.dolthub.com/

**Practitioner decision criteria (synthesized across sources), roughly in order of
weight:**
| Criterion | Favors data-as-code (git/dbt seed) | Favors DB-as-truth |
|---|---|---|
| Edit frequency | Rare, batch | Frequent / continuous / live |
| Editor count | 1, or small trusted set via PR | Multiple, or programmatic writers |
| Consumer | Build-time only (compiled into app) | **Runtime API reads/writes** |
| Review need | Wants mandatory PR review | Wants approve-then-publish inline |
| Size | Small (well under 10MB) | Any size, especially growing |
| Sensitivity/IP | Fine in a repo everyone can see | Needs access control finer than repo-clone |

TinBoker's own description ("served live by an API") already lands it on the DB side of
the decisive axis per dbt's own stated anti-pattern.

---

## 4. Hybrid patterns

- **DB-as-truth + periodic git-tracked export snapshot** is the pattern most people
  converge on for "want DB's live-serving + API convenience, but want git's diffability
  and public-facing changelog." Practically: a scheduled job dumps the taxonomy to
  JSON/CSV into a **private** git repo/branch on every change or on a cron, giving you
  free diffs and a changelog without making the DB itself the review surface.
- **Git-as-truth + DB as serving layer (derived/rebuilt)**: the dbt-seed model taken to
  its logical extreme — CI rebuilds the serving DB from the git-committed data on every
  merge. Works well when writes are infrequent and go through one person/PR gate; breaks
  down the moment there's a second, faster write path (e.g., a quick manual fix via
  admin UI) because now there are two truths that must be reconciled — exactly the "seeds
  become stale vs the live system" drift dbt docs warn about.
  Source: https://dagster.io/guides/working-with-dbt-seeds-quick-tutorial-critical-best-practices
- **Failure mode named explicitly across sources**: drift between the git copy and the
  live DB happens whenever there are **two write paths** that don't both funnel through
  the same commit/audit mechanism (e.g., an admin-UI "quick fix" that never gets exported
  back to git). The fix practitioners converge on is **one-way flow only**: either (a) all
  writes go to DB, and git is a read-only mirror/export, or (b) all writes go to git, and
  DB is a rebuilt/read-only cache — never let both be independently writable.
- Audit-log tooling that gives DB-as-truth most of git's diff/history value cheaply:
  Postgres trigger-based audit tables (`pgMemento`, `PGHist`) capture before/after row
  images, who/when, and support "as of" time-travel queries — this is the low-effort way
  to get "git-like history" without leaving Postgres.
  Sources: https://pghist.org/ ; https://github.com/pgMemento/pgMemento ;
  https://wiki.postgresql.org/wiki/Audit_trigger

---

## 5. IP/confidentiality angle

- **git-crypt**: transparent per-file encryption within a git repo — good for a repo
  that's mostly public with a few secret files, not a good fit for "the whole dataset is
  the IP" (you'd be encrypting most of the repo, defeating the point of using git for
  diffability, since diffs of encrypted blobs are opaque).
  Source: https://github.com/AGWA/git-crypt
- **Private git submodule**: keep the proprietary dataset in a wholly separate **private**
  repo, referenced only by commit-hash pointer from any public/shared code repo. Clean
  separation of "public code" vs "private data," each with independent access control.
  Caveat found: git-crypt and submodules interact poorly together, and submodule history
  has the standard git caveat — anyone who ever had access to a commit can still read
  that snapshot even after access is revoked (key rotation doesn't retroactively protect
  history).
  Source: https://handbook.cal.com/engineering/codebase/git-private-submodules ;
  https://github.com/AGWA/git-crypt/issues/42
- **Simplest fit for TinBoker's actual constraint ("must not live in public git")**: this
  doesn't require encryption tooling at all — a **private repository** (private GitHub
  repo, or a private Dolt/DoltLab remote) already satisfies "not in public VCS" while
  preserving full history. git-crypt/submodule tricks solve a *different* problem (mixed
  public+private in one repo) that doesn't apply if nothing here is meant to be public.
- **DB-native alternative to git privacy**: Postgres row-level security + column
  encryption (pgcrypto) can restrict who/what can read sensitive fields even within a
  shared DB, layered with schema-level access revocation (put sensitive views in an
  unexposed schema). Useful if the DB itself is otherwise shared infra (e.g., same
  Postgres instance as other TinBoker services) and you want IP isolation *within* the
  instance rather than a separate private store.
  Source: https://www.enterprisedb.com/postgres-tutorials/how-implement-column-and-row-level-security-postgresql ;
  https://postgreshelp.com/postgresql-rls/

---

## Recommendation matrix

**Scenario:** solo maintainer, proprietary taxonomy, ~monthly LLM-assisted bulk updates +
occasional manual fixes, served live by an API, must not live in public git.

**What the sources collectively support:** **DB-as-truth, git/version-history as a
derived audit trail — not the reverse.** The decisive signal is dbt's own stated
anti-pattern list: "served live by an API" (runtime consumer) + "regular updates" both
independently push away from seeds/git-as-truth and toward a database. Dolt is the one
data-as-code tool explicitly marketed for this exact shape of workload ("curated
reference datasets," audit/rollback needs) — but it's a DB with git ergonomics, which is
really just "DB-as-truth done well," reinforcing rather than contradicting this pick.
Meanwhile GICS/ICB/TRBC contribute the *change-management ritual* to layer on top,
independent of storage choice — that's a separate axis from where bytes live.

**Non-negotiable components (3–5):**

1. **Postgres as the single source of truth, in the existing private infra** (not
   public git, not a seed file) — satisfies "served live by API" and "must not be
   public" simultaneously with zero extra tooling.
2. **Trigger-based audit table (pgMemento/PGHist-style, or hand-rolled JSONB
   before/after)** on the taxonomy tables — gives who/what/when + rollback, i.e., the
   MDM lineage/stewardship value, without a git dependency or an MDM platform.
3. **Structural-vs-membership change split, borrowed from GICS/ICB/TRBC**: bulk
   LLM-assisted membership/rationale edits are low-ceremony (audit-logged, reviewed
   ad hoc); adding/removing/splitting/renaming a *sector itself* gets a version bump +
   one-paragraph dated changelog entry before it ships — cheap insurance against silently
   mutating a category's identity out from under API consumers.
4. **Survivorship rule written down once**: manual fix always wins over the next LLM
   bulk pass (prevents the bulk job from silently reverting a hand-corrected entry) —
   this is the one MDM ritual worth keeping; skip stewardship committees, RACI, and
   dashboards as theater at this scale.
5. **Periodic private export snapshot (JSON dump to a private repo or private Dolt
   remote) on a cron or per-release**, purely for human-diffable history and disaster
   recovery — optional but cheap, and it's the "hybrid" pattern that gets you git's
   diff-reading ergonomics without making git a second writable truth (avoid the
   two-write-paths drift failure mode every source flags).

Full sourced notes: see file above (this document).
