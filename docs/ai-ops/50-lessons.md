# Lessons Log

> Append-only during normal work; newest first. Entry format and routing rules:
> [40-maintenance-protocol.md](40-maintenance-protocol.md) §4. Consolidate at 40 active
> entries or ~250 lines (§5). Entries below dated 2026-07-03 are the founding seed —
> real findings from the session that built `docs/ai-ops/`, kept as format examples.

---

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
