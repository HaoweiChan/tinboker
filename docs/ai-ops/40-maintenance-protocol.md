# Maintenance Protocol — how to change these files without wrecking them

> Read before editing CLAUDE.md, anything in `docs/ai-ops/`, or any doc another file
> points to. The failure this prevents: each session adds "one more rule", nothing is
> ever deleted, and in six months CLAUDE.md is 400 stale lines again (that is literally
> how it got that way the first time — [00-diagnosis.md](00-diagnosis.md) Problem 2).

---

## 1. Permission tiers

**Tier A — edit freely (no user approval needed):**
- Append entries to [50-lessons.md](50-lessons.md) in the format of §4.
- Fix objectively wrong facts (broken path, renamed file, stale command) — the fix must
  cite evidence (`file:line` or command output) in the lesson entry you add alongside it.
- Add a missing pointer to the CLAUDE.md read-first map when a new canonical doc appears.
- Add an example to an existing rubric (keep the rule text itself unchanged).
- Update "verified YYYY-MM-DD" stamps after re-verifying a fact.

**Tier B — edit with mandatory backup + fresh-agent read-back (see §3):**
- Rewording rules for clarity (meaning preserved).
- Consolidation passes (§5).
- Restructuring any single file's sections.

**Tier C — ASK THE USER FIRST (propose the diff, wait for approval):**
- Changing thresholds or ladder steps in [10-model-dispatch.md](10-model-dispatch.md)
  (delegation triggers, retry caps, escalation rules).
- Deleting or weakening any rule, rubric, or Do-Not item.
- Changing CLAUDE.md's structure or what it routes to.
- Anything that would let an agent self-verify, skip backups, or touch prod with less
  friction than today. (If a change makes life easier by removing a check, it's Tier C.)

When unsure which tier applies: it's the higher one.

## 2. Backup rule (unchanged from founding session)

Before modifying any existing file covered by this protocol: copy to
`docs/ai-ops/_backups/` with the path flattened by double underscores plus a date suffix
— `docs/infra-runbook.md` → `docs__infra-runbook.md.YYYY-MM-DD.bak`. Never overwrite an
existing .bak (add `-2` etc.). **Scrub any secret values from backups** (replace with
`<REDACTED>`); backups preserve structure, not secrets. Backups whose change has merged
to `main` may be deleted in a later cleanup (Tier A).

## 3. Verification after editing (applies to all tiers)

Never self-verify an ai-ops edit. After editing, dispatch a fresh-context agent
(template T5 in [30-delegation-templates.md](30-delegation-templates.md)) with the
specific questions: (a) do the changed lines contradict any other ai-ops file or
CLAUDE.md? (b) does every path/tool/parameter named in the changed lines actually exist
in the repo/harness? (c) would a weak model misread any changed sentence? Fix findings
before ending the session.

## 4. The lessons log — [50-lessons.md](50-lessons.md)

Append-only during normal work; newest entries at the top. Entry format (copy exactly):

```markdown
## YYYY-MM-DD — <one-line title>
- **Situation:** what was being attempted (1–2 lines)
- **Wrong assumption / failure:** what was believed vs. what was true, with evidence (file:line, command output)
- **Rule:** the one-sentence instruction that would have prevented it
- **Status:** logged | promoted → <which file §> | obsolete (YYYY-MM-DD, why)
```

Routing — where a lesson ultimately belongs:
- About **the user** (preferences, corrections, working style) → user-level memory files
  (see system-prompt memory instructions), NOT the repo. The repo is shared; user quirks
  aren't repo truth.
- About **this repo/infra** (doc drift, gotchas, env facts) → 50-lessons.md; if it
  invalidates a doc, ALSO fix the doc (Tier A).
- About **how to run agents** (dispatch, verification, escalation) → 50-lessons.md first;
  promotion into 10/20/30 is Tier B (rewording) or Tier C (changing thresholds).

## 5. Size budgets and consolidation

| File | Budget | When exceeded |
|---|---|---|
| CLAUDE.md | 170 lines | Move detail out to a referenced doc; CLAUDE.md gets one pointer line |
| Each `docs/ai-ops/1x–4x` file | 300 lines | Consolidation pass (below) |
| 50-lessons.md | 40 active entries or ~250 lines | Consolidation pass (below) |

Consolidation pass (Tier B, one session, ideally the strongest model available):
1. Backup all files being touched (§2).
2. Group lessons by theme; a theme with ≥2 entries becomes ONE rule candidate; mark the
   entries `promoted` (don't delete them yet — delete promoted/obsolete entries only in
   the NEXT consolidation, so one bad pass can't destroy history).
3. Promotion of rule candidates into 10/20/30 follows their tier (threshold changes =
   Tier C → batch them into one proposal for the user).
4. Fresh-agent read-back per §3, PLUS one adversarial check: "which existing rule does
   this new rule conflict with?"
5. Log the consolidation itself as a lesson entry (what was merged, what was dropped).

## 6. Dated facts and re-verification

Any claim about the environment (model names, tool parameters, URLs, ports, TTLs, GCP
resources) must carry a "verified YYYY-MM-DD" stamp at first writing. When you rely on a
stamped fact older than ~90 days, re-verify it first (run the command / read the code)
and update the stamp — or mark it `STALE?` and route around it. Never delete a stamped
fact just because it's old; verify then update.

## 7. Single source of truth

A fact lives in exactly one file; every other mention is a pointer. When you find the
same fact stated in two places (the pre-2026-07-03 disease), pick the canonical home by
the CLAUDE.md read-first map, keep it there, and replace the other with a link — Tier B.
Special case: root `AGENTS.md` (non-Claude tools) still duplicates repo facts; reconciling
it is a known open task, not something to do as a side effect.
