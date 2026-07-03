# Harness Diagnosis — Top 3 Failure Modes and Fixes

> Written 2026-07-03. This is the founding document of `docs/ai-ops/`. Every other file in
> this directory exists to fix one of the problems named here. If you are a future session
> wondering "why do these rules exist" — this is why.
>
> **Reader contract for all of `docs/ai-ops/`:** these files are written for the model
> operating the main conversation (any tier: Haiku, Sonnet, Opus). Rules are mandatory
> unless marked "prefer". When a rule conflicts with a direct user instruction, the user
> wins; note the conflict in your reply.

---

## Problem 1 — The main conversation does bulk work itself (biggest token leak)

**Symptom.** The main loop greps the repo, reads whole files, tails logs, and pastes web
pages into its own context. Each dump costs tokens *forever after* — every later turn
re-reads it through the cache, and long context measurably degrades focus: the model
starts answering the last file it read instead of the user's question.

**Evidence in this environment (verified 2026-07-03).**
- Eight read-only domain subagents exist (`.claude/agents/`: podcast-domain, stock-data,
  auth-admin, devops-infra, content-pipeline, graph-visuals, search-discovery, qa-tester),
  plus built-in read-only `Explore` and full-capability `general-purpose` — but nothing
  in CLAUDE.md forced their use.
- The system prompt already carries ~30 skills + MCP tool listings before the first user
  word; there is no slack for file dumps.

**Fix (implemented in [10-model-dispatch.md](10-model-dispatch.md)).** The main loop is a
dispatcher, not a worker. Hard thresholds: more than 2 search rounds, more than 3 file
reads for orientation, any repo-wide scan, any web research, any batch edit across >5
files → delegate to a subagent that returns *conclusions + file:line refs only*.

---

## Problem 2 — Always-loaded context is bloated, duplicated, and partly false

**Symptom.** CLAUDE.md was 400 lines / 17 KB, loaded into every session. Most of it is
procedure detail needed in <10% of sessions (full deploy steps, Cloudflare purge scripts,
dev-bypass walkthrough, env-var blocks). Worse, some of it was **wrong**, and a weak model
cannot tell: it stated "`AGENTS.md` is symlinked here" while `AGENTS.md` is actually a
divergent 6.9 KB separate file — two conflicting sources of agent instructions; the
"Known Issues" section pointed at bugs already resolved.

**Why this hurts weak models most.** A strong model discounts stale text against what it
sees in the repo. A weak model treats loaded context as ground truth and acts on it.
Every stale sentence in an always-loaded file is a standing landmine.

**Fix (implemented in the CLAUDE.md rewrite + [40-maintenance-protocol.md](40-maintenance-protocol.md)).**
- CLAUDE.md becomes a router: identity, layout, commands, hard rules, and *pointers with
  trigger conditions* ("deploying? read docs/workflows/deploy-flow.md"). Detail lives in
  exactly one referenced file each.
- Single-source-of-truth rule: a fact may live in one file only; everywhere else links to it.
- Size budget: CLAUDE.md ≤ 170 lines; any ai-ops file ≥ 300 lines triggers consolidation
  (procedure in the maintenance protocol).
- Dated facts: any environment claim (URLs, IPs, model names, tool params) carries a
  "verified YYYY-MM-DD" stamp so future sessions know to re-verify old ones.

---

## Problem 3 — No verification discipline and no lesson persistence (biggest error source)

**Symptom, part 1 — self-verification.** Nothing required proof of "done". The failure
pattern of weaker models: edit a file → declare success without running the build/tests;
or "verify" their own change by re-reading the diff they just wrote (which validates
intent, not effect).

**Symptom, part 2 — amnesia.** The persistent memory directory
(`~/.claude/projects/-Users-willy-Documents-tinboker/memory/`) was **completely empty** as
of 2026-07-03, despite the project having months of history and heavy multi-agent use.
Every mistake has been re-learnable. Every user correction evaporated with its session.

**Fix (implemented in [10-model-dispatch.md](10-model-dispatch.md) §Verification,
[20-judgment-rubrics.md](20-judgment-rubrics.md) R2/R6, and [40-maintenance-protocol.md](40-maintenance-protocol.md)).**
- Never self-verify: acceptance is checked by a **fresh-context** subagent, or by an
  objective command (tests, build, curl on a health endpoint) whose output is pasted.
- Per-task-type done-criteria are enumerated in the rubrics file — "done" without meeting
  them is a false report.
- Every user correction and every costly dead-end gets written down the same day:
  user preferences → memory files; repo-truth lessons → the ai-ops lessons log
  (format and routing in the maintenance protocol).

---

## Secondary issues (real, but smaller — don't fix these before the top 3 are stable)

- **Workflow tool is opt-in only.** Multi-agent orchestration via the `Workflow` tool
  requires the user to explicitly ask (e.g. "ultracode", "use a workflow"). Do not launch
  it on your own judgment; use the `Agent` tool for ordinary delegation.
- **Non-interactive sessions cannot OAuth.** Several MCP servers (github, linear, slack,
  bigquery…) need interactive auth. If a task depends on one and it's unauthenticated,
  say so and route around it (e.g. `gh` CLI for GitHub) instead of retrying.
- **Deferred MCP tools load via ToolSearch.** Batch all needed tools into ONE ToolSearch
  call (`select:a,b,c`); loading one-by-one wastes a round-trip each.
- **Skill sprawl.** 30+ skills are listed; weak models sometimes narrate a skill instead of
  invoking it, or guess names. Rule: only invoke names that appear in the available-skills
  list, and invoke *before* answering about the task.
- **AGENTS.md divergence.** `AGENTS.md` (for Codex/Cursor/Aider) and CLAUDE.md drifted
  apart. Until they are reconciled, treat CLAUDE.md + `docs/` as canonical for facts; if
  you edit shared rules, check whether AGENTS.md states the opposite.

---

## Honest limits — what this system cannot fix

Decomposition, verification, and multi-sample review recover most *execution* quality on
smaller models. They do **not** recover:

1. **Taste and ambiguous product judgment** (naming, UX trade-offs, "is this article
   good", what the user *meant* by a vague ask). Mitigation, in order: (a) generate 2–3
   genuinely different options and let the user pick; (b) escalate the subtask to the
   strongest available model (`opus`) with the decision isolated into one question;
   (c) say plainly "this needs your judgment" — a stated limitation beats a confident
   wrong guess.
2. **Novel-situation debugging** where the failure crosses systems (CDN + Redis + Firestore
   interplay). Checklists help isolate; they don't substitute for insight. After 2 failed
   hypotheses, stop, write down the evidence table, and either escalate the model tier or
   present the table to the user.
3. **Knowing what's missing.** A weak model won't notice the question it should have asked.
   Partial mitigation: the "stop and ask" rubric (R3) and the completeness questions in
   the review template. Accept residual risk.

When in doubt whether something falls in this list: if two careful readings of the task
produce two different legitimate deliverables, it's a judgment problem — don't grind on it
with retries.
