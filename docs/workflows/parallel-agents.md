# Parallel Agents — Worktree Discipline

Moved from CLAUDE.md 2026-07-03; canonical home for multi-agent worktree rules.

This repo is under **heavy concurrent agent development**. Multiple agents sharing the one
primary checkout collide on each other's uncommitted changes and branch switches. To avoid that,
do **implementation work in a dedicated git worktree** when other agents may be active.

**Use a worktree for:** multi-file work, refactors, or anything you'll commit.
**Skip it for:** read-only exploration, a single trivial edit, or when you're the only agent.

```bash
git fetch origin
git worktree add ../tinboker-<task> -b <type>/<name> origin/develop   # <type> = feat|fix|docs|hotfix
cd ../tinboker-<task>
# install only what you touch: (cd frontend && npm install) | (cd backend && uv sync) | (cd pipelines && uv sync)
# copy env only if you need to RUN it: cp ../tinboker/backend/.env backend/.env   (NEVER commit .env)
```

**Clean up when done:** `git worktree remove ../tinboker-<task>`; delete the branch once its PR
merges; run `git worktree prune` periodically (stale worktrees accumulate).

**What this does — and does NOT — fix:**
- ✅ Isolates working trees — no more clobbering another agent's uncommitted changes.
- ⚠️ Worktrees **share** one `.git` — `git fetch`, branch create/delete, and stashes are global;
  another agent's merges can land on `origin/develop` mid-task (re-check HEAD before commit/rebase).
- ❌ Does **not** prevent git **merge conflicts** when two branches edit the same lines — keep PRs
  small and integrate often.

**Sub-agents:** prefer built-in isolation over rolling your own — the Agent tool's
`isolation: "worktree"` and the background-task chip already spin up isolated worktrees.
