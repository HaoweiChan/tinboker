# Delegation Prompt Templates

> Copy the template, fill every `{…}` blank, delete the lines that don't apply — but
> NEVER delete the Acceptance criteria or Report format blocks (a prompt without them
> returns essays and unverifiable claims; see [10-model-dispatch.md](10-model-dispatch.md) §5).
> Defaults column: agent type + `model` param for the Agent tool. Escalation rules:
> dispatch §8.

Shared boilerplate — include at the END of every template:

```
REPORT CONTRACT: Your final message is the deliverable. Conclusions and file:line refs
only; quote at most 2 lines per evidence point; no file dumps. Anything long goes to a
file (deliverables → repo path I named; intermediates → your scratchpad) and you return
the path. Mark every claim VERIFIED (you ran/read it) or INFERRED (you believe it).
If you cannot finish, say exactly where you stopped and what's missing — a partial
truthful report beats a complete-looking guess.
```

---

## T1 — Search / orientation ("where does X live, how does Y work")

Default: `Explore` or matching domain agent (podcast-domain, stock-data, …), `model: sonnet`
(haiku only if it's "find one named symbol").

```
GOAL: Find {what} in {scope, e.g. backend/src}. I need this because {motivation — what
decision this feeds}.
Search breadth: {medium | very thorough}.
ANSWER THESE: {numbered questions — e.g. 1. Where is the TTL set? 2. Who calls it?
3. Any config override?}
ACCEPTANCE: every question answered with file:line, or explicitly "not found — searched
{patterns/dirs}". "Probably" answers must be marked INFERRED.
REPORT FORMAT: numbered answers matching my questions; ≤40 lines.
```

## T2 — Implementation (feature / bugfix)

Default: `general-purpose`, `model: sonnet`. Add `isolation: "worktree"` if other agents
may be editing. Escalate per R1 for auth / CI / Firestore-contract / financial-value paths.

```
GOAL: {change} in {files/area}. Why: {user-visible motivation}.
CONTEXT YOU NEED: read {specific docs from the CLAUDE.md read-first map, e.g.
docs/agents/podcast-domain.md} first. Relevant prior findings: {paste file:line facts
from earlier agents — don't make it rediscover}.
CONSTRAINTS: follow CLAUDE.md § Do Not; match surrounding code style; no drive-by
refactors; do NOT touch {files to leave alone}.
ACCEPTANCE (all must pass, run them yourself and quote output):
- {test command, e.g. cd backend && pytest tests/ -v -k {pattern}} green
- {build/lint command} clean
- {behavioral check, e.g. curl localhost:5174/api/... returns {expected}}
REPORT FORMAT: what changed (per file, one line each) · commands run + trimmed output ·
anything you noticed but did NOT fix (list only, don't fix).
```

## T3 — Refactor / batch mechanical change

Default: `general-purpose`. `model: haiku` when the recipe is fully worked out and
verifiable; `sonnet` when instances need per-site judgment. Always `isolation: "worktree"`
if >5 files and any other agent is active.

```
GOAL: Apply this exact recipe across {scope}: {recipe worked out in advance — old
pattern → new pattern, with one real before/after example pasted in}.
Why: {motivation}.
FIND SITES VIA: {grep pattern / file list — enumerate, don't let it guess}.
DO NOT: change behavior; touch sites matching {exclusions}; reformat untouched lines.
ACCEPTANCE: {test/build command} green after ALL edits; `git diff --stat` touches only
expected files; grep for the OLD pattern returns zero hits outside exclusions.
REPORT FORMAT: sites changed (file:line list) · sites intentionally skipped + why ·
verification output.
```

## T4 — Research (web or cross-repo)

Default: `general-purpose` (has WebSearch/WebFetch), `model: sonnet`; `opus` if the
output directly decides an architecture choice.

```
QUESTION: {precise question}. Decision it feeds: {what I'll do with the answer}.
CONTEXT: our stack is {relevant subset: FastAPI py3.12 / React 19 Vite / uv workspace…};
constraint: {e.g. must run on a 4GB VPS}.
REQUIRED: ≥{2} independent sources for any load-bearing claim; prefer official docs;
note version/date of every source (our cutoff-sensitive facts must be dated).
ACCEPTANCE: a recommendation with a stated confidence + the strongest argument AGAINST
it. "It depends" without a decision rule fails.
REPORT FORMAT: recommendation (≤5 lines) → key facts with source links → risks/against →
what you could NOT verify. Long notes to a scratchpad file, path in report.
```

## T5 — Review / verification (of another agent's or your own work)

Default: FRESH `general-purpose` agent (must not share context with the author),
`model: sonnet`; `opus` for the high-risk list in dispatch §7. This is the D5 verifier.

```
You are reviewing work you did not write. Be adversarial: your job is to find what's
wrong, not to approve. An approval with no checks performed is a failed review.
REVIEW TARGET: {diff / files / doc paths}.
THE TASK IT CLAIMS TO SOLVE: {paste the original ask verbatim}.
CHECK, in order:
1. Does it actually satisfy each clause of the ask? (quote clause → verdict)
2. Run {test/build commands} yourself — do they pass?
3. Correctness traps for this repo: async blocking calls, Zod schema vs actual payload
   mismatch, Firestore-direct reads (banned), secrets in diffs, TTL/cache implications,
   zh-TW copy correctness.
4. R5 zero-diff scan: any change unrelated to the task?
5. What's MISSING that the ask implies? (the completeness question)
ACCEPTANCE: every check has a verdict with evidence; findings ranked by severity.
REPORT FORMAT: VERDICT: {approve | fix-first | reject} → findings as
severity · file:line · one-line issue · suggested fix. ≤40 lines.
```

---

## Picking a template when the task is mixed

Decompose, don't blend: "find where TTLs are set and change them" = T1 (search) feeding
T2 (implementation) — two dispatches, second one carrying the first one's `file:line`
findings. One agent asked to "find and fix and verify" will self-verify, which D5/R2 ban.
The commander sequences; workers execute one template each. Exception: trivial known-file
edits don't need T1 first (dispatch §2 anti-trigger).
