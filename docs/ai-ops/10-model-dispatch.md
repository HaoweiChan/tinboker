# Model Dispatch Rules — the main loop is a commander, not a worker

> Read this before spawning any subagent, and re-read §Escalation after any subagent
> failure. Delegation prompt templates live in
> [30-delegation-templates.md](30-delegation-templates.md) — use them verbatim.
> Environment facts below verified 2026-07-03; re-verify anything older than ~3 months
> (see [40-maintenance-protocol.md](40-maintenance-protocol.md)).

---

## 1. Roles

**The main conversation (you) is the commander.** Your context is the most expensive
resource in the session: everything you read stays billed and attention-degrading for
every later turn. Workers (subagents) have disposable context — they can read 50 files,
distill, and throw the reading away.

**Commander does:** talk to the user, decide, dispatch, integrate conclusions, make the
few edits that are genuinely small, verify via fresh agents.
**Commander does NOT:** repo-wide scans, reading files for orientation, web research,
log spelunking, batch edits. Those go to workers.

## 2. Delegation thresholds — mandatory, not advisory

Delegate when ANY of these is true:

| # | Trigger | Delegate to |
|---|---------|-------------|
| D1 | You'd need >2 Grep/Glob rounds or >3 file reads just to orient | `Explore` (read-only) or the matching domain agent |
| D2 | Any question of the form "where/how does X work across the repo" | Domain agent (see §3 table) — they exist precisely for this |
| D3 | Web research, doc lookup, >1 page of external reading | `general-purpose` (it can WebSearch/WebFetch) |
| D4 | Batch mechanical edits across >5 files | `general-purpose` or `claude`, with `isolation: "worktree"` if other agents may be active |
| D5 | Verifying your own completed work | Fresh `general-purpose` agent — **never yourself** (§7) |
| D6 | Reading logs/CI output longer than ~50 lines | Any agent; it returns the 5 lines that matter |

Anti-trigger: if you already know the exact file and symbol, just Read that one spot
yourself — spawning an agent to read one known file is slower and wasteful. Rule of
thumb: **known address → go yourself; search required → send a worker.**

While a delegated search runs, do NOT run the same search yourself in parallel "to be
safe" — that doubles cost and splits attention. Wait for the report.

## 3. What workers exist here (verified 2026-07-03)

**Read-only analysts** (they CANNOT edit files; use them for mapping/diagnosis, never
for implementation):
- Domain agents (tools: Read/Glob/Grep/Bash only): `podcast-domain`, `stock-data`,
  `auth-admin`, `devops-infra`, `content-pipeline`, `graph-visuals`, `search-discovery`,
  `qa-tester`. Also `claude-code-guide` (questions about Claude Code itself; can also
  WebSearch/WebFetch).
- `Explore` and `Plan` (built-in): broader toolset (incl. web fetch) but no
  Edit/Write/NotebookEdit — still analysis-only.

**Full-capability workers** (all tools, can edit/run): `general-purpose`, `claude`.

Domain routing: episodes/comments/Firestore content → `podcast-domain` · market data /
FinMind / Massive / charts → `stock-data` · OAuth/JWT/admin → `auth-admin` · Docker/
Caddy/CI/Redis/VPS → `devops-infra` · anything under `pipelines/` → `content-pipeline` ·
knowledge graph / design system → `graph-visuals` · search/trending/tags →
`search-discovery` · env QA / bug repro → `qa-tester`.

**Continuing an agent:** the Agent tool result includes an agent ID; use `SendMessage`
to that ID for follow-ups so it keeps its context. Spawning a new agent for a follow-up
question throws away everything it learned.

## 4. Choosing model and effort — write it explicitly, never inherit by accident

The `Agent` tool accepts `model: "haiku" | "sonnet" | "opus" | "fable"`. There is **no
effort parameter on the Agent tool** — effort exists only inside the `Workflow` tool's
`agent()` calls (`'low'|'medium'|'high'|'xhigh'|'max'`), and Workflow itself may only be
used when the user explicitly opts in (says "ultracode" / "use a workflow"). Do not
reach for Workflow as ordinary delegation.

`fable` may not be available to your session's plan; if a spawn with `model: "fable"`
errors, retry once with `opus` — do not build any process that depends on fable.

| Task shape | Model | Why |
|---|---|---|
| Mechanical, verifiable, low-ambiguity: rename sweeps, format fixes, single-file lookup, applying an already-worked-out pattern | `haiku` | Cheap; failure is detectable |
| Default for everything: search, implementation, refactors, research, first-pass review | `sonnet` | Right cost/quality for >80% of subtasks |
| Cross-module design, debugging that survived 2 failed hypotheses, security-sensitive changes, adversarial final review, judgment calls | `opus` | Escalation tier — use deliberately, state why in the prompt |

Omitting `model` makes the worker inherit the session model. That's acceptable for
one-off spawns; for anything batched (≥3 agents), set the model explicitly so cost is a
decision, not an accident.

## 5. The dispatch triad — every delegation prompt contains all three

1. **Goal + motivation** — what to produce AND why/for whom, so the worker can make the
   hundred micro-decisions you didn't specify. ("Find where episode TTLs are set, because
   we suspect stale cache after deploys" beats "find TTL code".)
2. **Acceptance criteria** — objectively checkable. "Works" is not a criterion;
   "`npm run build` exits 0 and the new prop renders on /episodes" is.
3. **Report format** — see §6. Say it explicitly in every prompt; workers otherwise
   return essays.

A delegation prompt missing any leg gets garbage back, and the garbage costs more than
writing the prompt properly. Templates: [30-delegation-templates.md](30-delegation-templates.md).

## 6. Report contract — what workers may send back

- **Conclusions, decisions, and evidence pointers only**: `path/to/file.py:123`, one-line
  quotes (≤2 lines each), verdicts, numbers.
- **No file dumps.** Anything long (diffs, generated docs, research notes, logs) is
  written to a file — repo path for deliverables, the session scratchpad for
  intermediates — and the report carries the path.
- Soft cap ~40 lines / ~400 words. A worker that needs more than that should split its
  report into "conclusions" (inline) and "details" (file path).
- Reports must separate **VERIFIED** (I ran/read it) from **INFERRED** (I believe it).
  The commander treats INFERRED claims as unchecked.

Put this contract into the worker's prompt (the templates include it); workers don't
read this file.

## 7. Verification — never self-verify

The agent that did the work is the least qualified to check it (it re-reads its own
intent). Acceptance therefore comes from one of:

1. **Objective command** — tests / build / lint / `curl .../health`, run by you or the
   worker, with the actual output quoted in the report. This is the cheapest and
   strongest verifier; prefer it whenever one exists.
2. **Fresh-context read-back** — for docs/config/prose: a NEW agent (no shared history)
   reads the artifact and answers: does it satisfy criteria X, Y, Z? Does it contradict
   file W?
3. **Second opinion / N-sample** — for high-risk judgment (schema changes, security,
   anything touching prod data): either one `opus` reviewer prompted to *refute* the
   work, or 2–3 independent attempts with a judge picking the best. Reserve this for
   genuinely high stakes; it triples cost.

"High-risk" here means: touches the Firestore contract, auth, CI/CD, deploy config,
cache TTLs, or anything a user-facing financial number flows through.

## 8. Escalation and de-escalation ladder

- **haiku fails once** on a subtask → resend to `sonnet` immediately. Do not debug
  haiku's attempt; do not retry haiku.
- **sonnet fails the same subtask twice** (two genuinely different attempts, not the
  same attempt twice) → escalate to `opus`, and the escalation prompt MUST carry the
  full failure trail: what was tried, exact error output, current hypothesis. Escalating
  without the trail forces opus to rediscover the dead ends you already paid for.
- **opus fails twice** → stop. This is no longer an execution problem. Write the
  evidence table (attempts, outputs, hypotheses) into a scratch file and surface it to
  the user with your best guess. See rubric R4 (wrong-direction signals) — often the
  right move was a different approach, not a stronger model.
- **De-escalate after solving:** when an expensive model has worked out the pattern
  (the fix recipe, the migration shape), extract the recipe into the prompt and
  batch-apply the remaining instances with `haiku`/`sonnet`. Paying opus prices for
  find-and-replace is the classic waste.
- **Global cap: two retry rounds per approach.** The third attempt must change something
  structural — different approach, different decomposition, more context, or a question
  to the user. "Try again but harder" is banned.

## 9. Hygiene

- Independent spawns go in ONE message (they run concurrently). Dependent spawns wait.
- Long-running work: `run_in_background: true`; you're notified on completion — don't poll.
- Parallel *editing* agents: give each `isolation: "worktree"` or disjoint file sets;
  two agents editing one file will clobber each other.
- Out-of-scope discoveries (dead code, stale docs, unrelated bug): don't fix inline —
  flag via the spawn_task chip (`mcp__ccd_session__spawn_task`) with a self-contained
  prompt, and keep moving.
- Sonnet-and-below compatibility rule for anything you write into ai-ops: a rule that
  requires judgment to apply ("delegate when it seems complex") is broken; a rule a
  weak model can apply ("delegate at >3 orientation reads") is fixed. Write the second kind.
