# Letter to Future Sessions

> Written 2026-07-03 by the session that founded `docs/ai-ops/` (running Claude Fable 5;
> every session after this one is expected to run a smaller model — these files were
> written for you with that in mind, deliberately concrete, nothing here needs a stronger
> model to execute). Read this once when you start substantial work in this repo, or when
> you suspect the system around you is decaying.

---

## Three things nobody asked me to tell you

### 1. The dangerous seams are the data contracts, not the code

This platform is mid-migration (Firestore/GCS → VPS Postgres; see
`pipelines/docs/data-consolidation-plan.md`), and three tiers — `pipelines/` (producer),
`backend/` (server), `frontend/` (consumer, Zod-validated) — share field-level contracts
documented in `docs/firestore-contract.md`. Almost any "weird bug" that isn't a plain
code error is one of these seams: a field renamed in one tier, a TTL misaligned with the
pipeline cadence, a Zod schema stricter than the payload. Before debugging cross-tier
symptoms, diff the contract against BOTH sides' actual code. And never change a shared
field without `docs/workflows/firestore-data-change.md`. The Zod validation layer
(`frontend/src/validation/schemas.ts`) is your best tripwire — when it screams, believe
it; the payload really changed.

### 2. zh-TW fidelity and numeric correctness ARE the product

This is a Traditional-Chinese (Taiwan) financial-information product. Two quality bars
that generic coding instincts miss, and where smaller models slip most:
- **Language:** user-facing text is zh-TW with Taiwan financial vocabulary. Watch for
  simplified-Chinese character contamination and China-market terms in generated copy
  (the pipeline-debug skill literally scores "Traditional-Chinese fidelity" — that's how
  real this failure mode is). If you generated Chinese text, have a fresh agent check it.
- **Numbers:** prices, sentiment, P/E — a wrong number is worse than a crash here.
  Hardcoding financial values is banned (CLAUDE.md § Do Not); any change on a path that
  produces a user-visible number gets the high-risk verification of dispatch §7,
  even when the diff looks trivial.

### 3. You will often be running unattended — act like it

Many sessions here run autonomously (worktrees, background agents, scheduled runs), with
the user reading results later. Two consequences: (a) a question mid-task blocks
everything — batch questions at the start or choose the reversible default and state it
in the report (rubric R3 tells you which is which); (b) the one place where the
calculus flips is the deploy pipeline and prod data — there, irreversibility means R3's
"stop and ask" wins even if it stalls the task overnight. Nothing on staging/dev is worth
fearing; nearly everything on prod is.

## How this system will probably decay, and the countermeasures

1. **Re-bloat.** Sessions add rules, none delete. The smell: CLAUDE.md creeping past 170
   lines, ai-ops files past 300. Countermeasure exists (maintenance §5 consolidation) —
   the decay mode is nobody *running* it. If you see the smell, run the pass; it is
   Tier B, you don't need permission.
2. **Ritual compliance.** The lethal one, because it looks like health: agents get
   spawned (dispatch followed!) but the commander redoes their work anyway; T5 reviewers
   return "VERDICT: approve" without running a single check; lessons get logged as vague
   platitudes ("be more careful"). Countermeasure: evidence requirements — a report
   without quoted command output / file:line is treated as NOT DONE, an approval without
   per-check verdicts is a failed review, a lesson without evidence gets deleted at
   consolidation. Enforce these on each other; no one else will.
3. **Stale environment facts.** Model names, tool parameters, URLs, the `fable` enum —
   all true 2026-07-03, all perishable. Countermeasure: the date stamps (maintenance §6).
   When a stamped fact >90 days old is load-bearing, re-verify before relying.
4. **The unread constitution.** If sessions stop reading these files, everything above is
   moot. That's why CLAUDE.md is short with concrete triggers — protect that property
   above any individual rule. A 40-line addition that makes CLAUDE.md unreadable costs
   more than the rule earns. (If the user wants stronger enforcement, per-directory
   hooks or a session-start hook via `.claude/settings.json` can inject reminders — a
   user decision, propose it, don't self-install.)

## Honest limits (repeated from 00-diagnosis because it matters most here)

Process fixes execution, not judgment. When the task is taste, product ambiguity, or a
genuinely novel cross-system failure: present options / an evidence table instead of
grinding retries; escalate the isolated question to the strongest available model; or
tell the user plainly it needs their call. A smaller model following that honestly
outperforms a smarter model bluffing.

## Open tasks left by the founding session (2026-07-03)

- **Rotate `DEV_BYPASS_TOKEN`** — a live value sat committed in `docs/agents/auth-admin.md`
  (removed 2026-07-03, but it lives in git history). User was told; if it hasn't
  happened, remind them. Secret: `DEV_BYPASS_TOKEN` in GCP Secret Manager + VPS env.
- **Reconcile root `AGENTS.md`** with CLAUDE.md + docs/ (it forked; currently marked
  legacy). Tier C — propose to user.
- Stale docstring: `backend/src/routers/episodes.py` `/recent` says "CDN Cache: 30
  minutes"; code says 10. Trivial, fix in any passing PR.
- `docs/infra-runbook.md` states the VPS service-account path inconsistently
  (`/app/gcp-service-account.json` vs `/app/backend/gcp-service-account.json`) —
  pre-existing; verify against the deploy scripts and fix (found by review 2026-07-03).
- Consider gitignoring `docs/ai-ops/_backups/` (user decision; backups currently in-repo
  per founding instruction, secrets scrubbed).
- This institution was created on branch `claude/competent-cray-950c92`; it protects
  nothing until merged to `develop`/`main`.
