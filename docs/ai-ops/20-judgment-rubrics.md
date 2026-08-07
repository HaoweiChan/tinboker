# Judgment Rubrics — decisions made checkable

> Each rubric turns a judgment call into signals a smaller model can test. Format:
> trigger signals → action → one positive example (rule correctly applied) → one negative
> example (the mistake the rule prevents). Examples use this repo's real domain.
> Referenced from CLAUDE.md and [10-model-dispatch.md](10-model-dispatch.md).

---

## R1 — When to escalate to a stronger model

**Escalate the *subtask* (not the whole session) to the next tier when ANY:**
- Two genuinely different fix attempts failed (mechanics: dispatch §8 ladder).
- The task requires holding ≥3 modules' behavior in mind at once (e.g. a change that
  spans `pipelines/` extraction → Firestore contract → `backend/` API → frontend Zod
  schema).
- Evidence contradicts itself (test passes locally, fails in CI; doc says X, code does Y)
  and you cannot name which source is stale.
- The change touches auth, CI/CD, the Firestore contract, cache purging, or anything a
  user-visible financial number flows through — escalate the *review* even if the
  implementation was easy.

✅ **Right:** sonnet twice failed to make a flaky `pytest -m integration` test pass, each
attempt a different hypothesis. It stopped, wrote the two failure outputs into the
escalation prompt, and dispatched to opus. Opus found event-loop reuse across tests.
❌ **Wrong:** haiku's rename sweep missed dynamic imports; the commander asked haiku to
"try again more carefully." Same miss. The ladder says: haiku fails once → sonnet, no
haiku retry. Cost of the wasted retry exceeded the sonnet premium.

**Do NOT escalate when** the failure is missing information (an unread doc, an unfetched
error log) — escalating a starved task starves a costlier model. Feed it first.

## R2 — When a task is actually done

"Done" requires ALL THREE, per task type:

| Task type | Required evidence |
|---|---|
| Backend code | `pytest tests/ -v` green on touched areas AND `ruff check src/` clean — outputs quoted, not paraphrased |
| Frontend code | `npm run build` exits 0 AND `npm run lint` clean; behavior change confirmed in dev server or by a verify agent |
| Pipelines code | `uv run --package <pkg> pytest` green; if extractor/writer logic changed, one real stored episode run through it (see the pipeline-debug skill) |
| Docs / config | Fresh-context agent read-back answers "does it satisfy the acceptance criteria?" YES with quotes |
| Deploy | Both CI runs green AND `/health` returns `"status":"healthy"` on the target env AND the deployed change is observable there |

1. The named evidence exists and is quoted in your report.
2. The evidence was produced AFTER your last edit (stale green runs don't count).
3. The original ask is re-read and every clause is covered — not just the clause you
   remember. (Re-read the user's actual message, not your summary of it.)

✅ **Right:** "Done: `npm run build` exit 0 (output below), lint clean, verify-agent
confirmed the ticker card renders on /episodes with the new field. The user also asked
for zh-TW copy — added, screenshot attached."
❌ **Wrong:** "I've updated the cache TTL and the code looks correct, so this is
complete." No test run, no health check, "looks correct" is the author grading their own
exam. This exact pattern is why dispatch §7 bans self-verification.

## R3 — When to stop and ask the user

**Stop and ask (one batched message, with your recommendation) when ANY:**
- The action is destructive or outward-facing and not explicitly requested: prod deploys,
  tag pushes, data deletion/backfill on staging/prod, force-push, posting to external
  services, anything touching Firestore prod data.
- Money, credentials, or user data beyond what the task named.
- Two careful readings of the ask yield two different legitimate deliverables (see
  diagnosis § honest limits — this is a judgment gap, not an execution gap).
- Fulfilling the ask requires violating a hard rule in CLAUDE.md § Do Not — say which
  rule, don't silently comply or silently refuse.

**Do NOT ask when:** the decision is reversible and any reasonable default exists
(pick it, state it in the report); the answer is discoverable in the repo/docs (go look);
you're just nervous (name the risk in your report instead).

✅ **Right:** task said "clean up old episodes in Firestore" — agent prepared the exact
delete query, ran it in COUNT mode, and asked: "this matches 1,204 documents on prod;
here's the filter; confirm before I execute."
❌ **Wrong:** "Should I use a table or a list for this component?" — reversible, either
is defensible, the user is not watching. Pick one, note the choice, move on.

## R4 — Signals the direction is wrong (change approach, don't retry)

Retrying harder is the weak model's default failure. Any of these means the APPROACH is
wrong:

- The same error survives two *different* fixes → your model of the system is wrong.
  Next step is diagnosis (add logging, minimal repro), not fix #3.
- Your fix keeps growing: you estimated 2 files, you're now editing the 6th → you're
  fighting the architecture; stop and re-plan (or ask if a refactor is in scope).
- You're weakening assertions/types/lint rules to make checks pass → the check was the
  point; you're deleting the signal. Hard stop.
- You need to mock/patch the very behavior under test.
- The framework fights back (working around Vite/FastAPI/Zod instead of with it) —
  someone has solved this properly; delegate a research agent to find the idiomatic way.
- (Meta-signal) You notice you are explaining to yourself why the failing evidence
  doesn't matter.

✅ **Right:** after two failed attempts to stop a Zod parse error, the agent stopped
patching the schema, dispatched an agent to diff the actual API payload against the
schema, and found the backend had renamed a field — a one-line contract fix, not a
frontend problem at all.
❌ **Wrong:** test asserts an episode list is sorted by `released_at_ms`; implementation
returns unsorted; agent "fixes" the test to not check order. Green, and wrong.

## R5 — Quality floor (checked before shipping anything)

Run this checklist on any change; a NO means not shippable:

1. Does R2's evidence table pass for this task type?
2. Zero-diff scan: does `git diff` contain ONLY changes the task needed? (No drive-by
   reformatting, no debug prints, no commented-out code, no unrelated "improvements".)
3. Does the change respect the Do-Not list in CLAUDE.md (secrets, Firestore-direct
   reads, `pip install` in pipelines, …)?
4. New/changed user-facing strings: zh-TW, consistent with `frontend/AGENTS.md`
   localization rules?
5. Anything learned that tomorrow's session needs? → write it per R6 now, not "later".

✅ **Right:** before reporting, the agent ran `git diff --stat`, noticed it had
auto-formatted an untouched file, reverted that file, then reported.
❌ **Wrong:** shipping a fix plus 300 lines of import re-ordering "while I was there" —
review burden explodes and the actual fix is unreviewable.

## R6 — What deserves to be written down (and where)

Write it down THE SAME SESSION when:
- The user corrects you, states a preference, or approves an approach → memory file
  (type `feedback` or `user`), per the memory instructions in your system prompt.
- You burned >20 minutes on a dead end a future session would plausibly repeat, or you
  discovered repo truth that contradicts a doc → lessons log
  (`docs/ai-ops/50-lessons.md`), format in [40-maintenance-protocol.md](40-maintenance-protocol.md).
- A doc you relied on was stale → fix the doc itself (that IS the lesson), backup first.

Do NOT write down: things the repo already records (git history, code structure),
session-local trivia, or guesses. A lesson must name the evidence.

✅ **Right:** "devops-infra.md claimed 5-min CDN TTL for /api/episodes/recent; code says
600s (episodes.py:27). Fixed the doc." — doc fixed, one-line lesson logged.
❌ **Wrong:** ending a session having learned the user hates emoji in UI copy, and
writing nothing. Next session ships emoji again. That's this harness's former default —
the empty memory directory was Problem 3 in [00-diagnosis.md](00-diagnosis.md).
