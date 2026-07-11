# Postgres governance for curated/reference data — research notes

Context: solo maintainer, FastAPI+Postgres, ~100 taxonomy rows w/ JSONB member lists +
~2000 LLM-generated rationale text fields, few writes/month, live API reads, currently
git-versioned.

## 1. Audit trail / change history

- **Trigger-based audit table** (row snapshot or hstore diff) is the accepted baseline
  for low-write-volume curated tables. The canonical reference implementation is the
  Postgres wiki's `audit_trigger_91plus` pattern: one `audit.logged_actions` table,
  hstore full-row snapshot + changed-fields-only for updates, captures txid/user/query
  text. Documented limitation: superuser/table-owner writes can bypass/tamper with it —
  fine for operational history, not for adversarial/compliance-grade tamper-evidence.
  https://wiki.postgresql.org/wiki/Audit_trigger_91plus
- **pgMemento** — trigger-based, logs only deltas as JSONB into one log table, adds
  DDL/schema-change tracking and restore/repair tooling. Heavier (its own schema,
  restore functions) — positioned for "full audit trail + point-in-time restore of
  whole schema," i.e. overkill unless you actually need automated restore, not just
  visibility. https://github.com/pgMemento/pgMemento
- **pgaudit** — logs to Postgres's logging facility (session/object level), including
  SELECTs; good for compliance log shipping, bad for "show me what changed" queryability
  (logs, not structured rows). Considered a different tool for a different job
  (security/compliance logging) vs. an app-level history feature.
  https://www.pgaudit.org/ , https://www.tigerdata.com/learn/what-is-audit-logging-and-how-to-enable-it-in-postgresql
- **SQL:2011 temporal tables / `temporal_tables` extension / `periods` extension** —
  standardized system-versioning (automatic history table + `PERIOD`/`SYSTEM_TIME`
  semantics). Native Postgres core support is still incomplete; `temporal_tables`
  (PL/pgSQL, no C ext needed in the nearform fork) and `xocolatl/periods` are the
  practical add-ons. Right tool if you want SQL-standard "AS OF" querying without
  hand-rolling it; overkill machinery for a hand-maintained ~100-row table where a
  simple audit table already answers "what changed and when."
  https://wiki.postgresql.org/wiki/Temporal_Extensions ,
  https://wiki.postgresql.org/wiki/SQL2011Temporal ,
  https://github.com/nearform/temporal_tables , https://github.com/xocolatl/periods
- **Plain `updated_at`/`updated_by` columns** — the universal minimum; tells you *that*
  and *when* a row last changed but nothing about prior values or who touched what
  earlier. Consensus: fine as a supplement, not sufficient alone once you want rollback
  or diff history.

**Baseline vs overkill:** for a few-writes/month, ~100-row table, a single Postgres-wiki-
style audit trigger (or even simpler: an app-level `INSERT INTO audit_log` in the same
write transaction) is the accepted floor. pgMemento/temporal-tables/pgaudit solve
problems (automated schema-wide restore, DDL tracking, compliance log shipping) this
system doesn't have yet.

## 2. Versioning & rollback for reference data ("as of last Tuesday")

- **Full-row audit/history table + "reconstruct as of timestamp" query** is the
  practitioner-standard way to answer "what did this look like on date X" for
  low-volume curated data — you already have this for free if you did (1) with row
  snapshots; no separate mechanism needed. This is effectively what pgMemento's
  restore functions formalize, and what the audit-trigger pattern's hstore snapshots
  make possible manually (`row_value || changed_fields` at each point in time).
  https://wiki.postgresql.org/wiki/Audit_trigger_91plus
- **Effective-dated rows / SCD Type 2** (`valid_from`/`valid_to` + current-row flag) —
  standard in data-warehouse/dimensional contexts where multiple "versions" of a
  dimension must be joined against historical facts. Overkill for a single
  live-reads-only API table with no downstream fact-table joins; the complexity buys
  you point-in-time joins you don't need.
- **Full-version tables with a published flag / snapshot-and-restore** — the pattern
  Neon's docs describe generically (branch/restore preserving a stable connection
  string) is really "snapshot the whole DB, restore later," aimed at AI-agent/codegen
  workflows needing instant whole-environment rollback, not row-level reference-data
  history. Confirms: for row-level "what did the taxonomy look like," a snapshot of the
  whole DB is the wrong grain — you want row-level audit trail (1), not DB-level
  snapshots. https://neon.com/docs/ai/ai-database-versioning
- **Standard for reference data behind a live API:** keep the live table as-is (current
  state only, fast reads, no version logic in the read path) and answer "as of"
  questions from the audit/history table out-of-band. Don't push temporal complexity
  into the hot read path for a table that's read far more than it's written.

## 3. Write-path integrity

- **DB constraints are the last line of defense, not the whole defense** — Postgres
  docs and Citus/cybertec both frame it this way: use CHECK/UNIQUE/FOREIGN
  KEY/EXCLUSION constraints for what the database can express declaratively, then
  application validation for everything richer. https://www.postgresql.org/docs/current/ddl-constraints.html ,
  https://www.citusdata.com/blog/2018/03/19/postgres-database-constraints/
- **EXCLUDE constraints handle cross-row rules Postgres can express declaratively** —
  e.g. non-overlapping ranges (`EXCLUDE USING GIST (room_id WITH =, range WITH &&)`),
  with partial-exclusion `WHERE` clauses for conditional rules. Postgres docs
  explicitly recommend EXCLUDE/UNIQUE/FK over triggers for cross-row constraints
  *when the rule fits that shape*. https://www.postgresql.org/docs/current/ddl-constraints.html ,
  https://dev.to/franckpachot/postgresql-exclude-constraints-for-better-concurrency-than-serializable-pob
- **"No two categories may overlap >80%" does not fit EXCLUDE** (it's a fuzzy/
  computed-similarity rule over JSONB member-list sets, not a range/equality
  operator Postgres indexes support) — consensus for this class of rule is
  **single write-endpoint application validation**, optionally backed by a trigger if
  writes can happen outside that endpoint. Practitioner consensus (Medium/dev.to
  pieces on constraints-vs-app-validation, and Postgres's own "Data Consistency
  Checks at the Application Level" doc) converges on: DB constraints for structural
  invariants, application code (ideally centralized at one write path) for anything
  requiring aggregation/comparison across rows with business semantics.
  https://www.postgresql.org/docs/9.4/applevel-consistency.html
- **CI-level checks** are a supplement (catch rule regressions/drift in bulk-loaded
  data before it reaches prod) not a substitute for either — didn't find a strong
  practitioner consensus advocating CI as a primary gate for single-writer curated
  data; it's mentioned mainly in CI/CD-for-data-quality contexts (dbt tests, etc.),
  which assume pipeline-style bulk writes rather than a single API endpoint.

## 4. Draft → review → publish workflows

- **Status-column pattern** (single table, an enum/status field: draft / in_review /
  published / archived) is what mainstream CMS practice converges on for small-to-
  medium systems — Payload CMS injects a `_status` field automatically; recommended
  over a plain boolean because editorial states are rarely binary.
  https://payloadcms.com/docs/versions/drafts ,
  https://www.getflashboard.com/docs/editing-content/drafts-and-publishing-workflows
- **Two-table draft/published split** — used when the published table must stay
  simple/fast for readers and drafts need richer editing metadata (locks, reviewer
  comments) without polluting the read schema; costs you a promote/copy step and
  keeping both schemas in sync. Practitioner framing: pick two-table when reads
  vastly outnumber writes and you don't want draft-only columns/joins touching the
  hot read path — matches this system's "live API reads, few writes/month" profile.
  https://www.phpdbg.com/drafts-published-posts-and-content-statuses-designing-a-small-cms-properly-before-the-project-starts-growing/
- **Workflow-states-as-data pattern** (separate table listing states + JSON
  transitions/permissions) — general software-engineering pattern for when transition
  rules themselves need to be configurable/auditable; explicitly the heavier option,
  for multi-actor/multi-state workflows. Overkill for solo-maintainer + one automated
  writer with effectively 2-3 states.
  https://medium.com/@herihermawan/the-ultimate-multifunctional-database-table-design-workflow-states-pattern-156618996549
- Consensus: for one human + one LLM bulk-writer, a `status` column
  (`draft`/`published`, maybe `needs_review`) on the same table beats a second table —
  simpler, and the read path just filters `WHERE status = 'published'`.

## 5. Backups for small curated datasets

- **pg_dump remains the base primitive**; the practitioner-level addition on top of it
  for small/rarely-changing datasets is **committing the dump into git** — multiple
  independent write-ups (DenBeke, Viget, ludusrusso, Benjamin Rancourt) describe the
  same pattern: cron/CI job runs `pg_dump`, commits the (often compressed) SQL/dump
  file to a private repo, timestamp or dated filename per run. Cited rationale: small,
  infrequently-changing DBs get free version history, diffability, and off-site
  storage essentially for free from git hosting — no object-storage setup needed.
  https://denbeke.be/blog/software/backup-your-databases-in-git/ ,
  https://www.viget.com/articles/backup-your-database-in-git/ ,
  https://www.ludusrusso.dev/blog/2022/04/database-backup-on-github-actions ,
  https://www.benjaminrancourt.ca/how-to-periodically-backup-your-databases-to-git/
- **Object storage (S3/GCS) + lifecycle/retention policy** is the standard "grown-up"
  answer once dump size or write frequency makes git unwieldy — not needed at this
  scale (~100 rows + ~2000 short text fields is a tiny dump).
- **Export-to-git-for-history hybrid**: since this system's data already originated as
  git-versioned YAML/JSON, the natural hybrid is exactly what the blogs describe:
  keep (or resume) a scheduled `pg_dump` (or a `COPY ... TO` per-table logical export,
  which is more diff-friendly than a full custom-format dump) committed to the existing
  git repo — reusing the audit history you already trust, rather than standing up new
  infra.

## Minimum sound setup for this scale (~100 rows, ~2000 text fields, few writes/month, live API reads)

1. **Audit:** one Postgres-wiki-style audit trigger (or equivalent app-level insert in
   the same transaction) on the taxonomy table(s), hstore/JSONB row snapshot +
   changed-fields on UPDATE. This alone answers "what changed, when, by what
   process" and lets you reconstruct any past state — no temporal-tables extension,
   no pgMemento, no pgaudit needed.
2. **Rollback:** no live-table versioning machinery — restore "as of last Tuesday" by
   replaying/reversing the audit log (or worst case, restoring the last pre-Tuesday
   pg_dump into a scratch DB and diffing). Keep the live table single-current-state.
3. **Write-path integrity:** one write endpoint in FastAPI that all mutations funnel
   through (human edits + LLM bulk writes alike); DB CHECK/UNIQUE constraints for
   structural rules (non-empty names, valid enum categories, JSONB shape via a CHECK
   with `jsonb_typeof`), the cross-row ">80% overlap" rule validated in that endpoint
   (or in a `BEFORE INSERT/UPDATE` trigger if you can't guarantee all writers go
   through the endpoint) before commit.
4. **Draft/publish:** add a `status` column (`draft` / `published`) to the existing
   table rather than a second table; API reads default-filter to `published`. Skip
   the two-table split and the workflow-states table — not enough concurrent
   editors/states to earn the complexity.
5. **Backups:** keep pg_dump (or per-table `COPY TO` for git-diffability) on a
   scheduled job, committed into the repo you already use for the current
   git-versioned taxonomy — you get history, off-site copy, and diffability from
   infra you already operate, no new object-storage bucket required.
