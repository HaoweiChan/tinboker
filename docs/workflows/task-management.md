# Task Management — TODO.md workflow

> Migrated 2026-07-04 from the root `AGENTS.md` (which is now a symlink to `CLAUDE.md`) as
> part of reconciling that file — see `docs/ai-ops/50-lessons.md` 2026-07-04 entry. This is
> real, active process: git history shows `TKB-001` shipped through exactly this flow.

## Source of truth

`TODO.md` is the single source of truth for product and engineering tasks.

GitHub Issues and GitHub Projects are derived mirrors only — do not treat them as
authoritative planning sources. If task status, priority, scope, or acceptance criteria
differ between GitHub and `TODO.md`, follow `TODO.md`.

## Standard workflow

When starting work:

1. Read `TODO.md`.
2. Pick only one task marked `status: ready`, unless the user explicitly selects a task.
3. Change the selected task to `status: in_progress`.
4. Implement only that task's acceptance criteria.
5. Avoid opportunistic refactors unless required for the task.
6. Add or update tests.
7. Run the relevant checks.
8. Update the task notes in `TODO.md`.
9. Add the PR link to the task metadata if available.
10. Change the task to `status: review` when ready.
11. Run the sync script if GitHub mirrors should be updated:
    ```bash
    python scripts/sync_todo_to_github.py
    ```
    Do not manually edit GitHub Project fields unless the sync script fails.

## Task metadata format

Tasks in `TODO.md` must include a YAML metadata block like this:

```yaml
id: TKB-001
status: ready
priority: P0
area:
  - pipelines
  - backend
  - frontend
type: feature
effort: L
risk: medium
github_issue: null
github_project_item: null
pr: null
```

Valid `status`: `idea`, `ready`, `in_progress`, `blocked`, `review`, `done`, `wont_do`.
Valid `priority`: `P0`, `P1`, `P2`, `icebox`.
Valid `area`: `frontend`, `backend`, `pipelines`, `infra`, `seo`, `product`, `scripts`, `docs`.
Valid `type`: `feature`, `bug`, `refactor`, `experiment`, `content`, `infra`, `docs`.

## GitHub sync rule

The sync script may create or update GitHub Issues and add them to GitHub Projects.
Agents should not create duplicate issues manually — before creating GitHub items, check
whether `github_issue` and `github_project_item` already exist in the task metadata.

## Commit and PR guidance

Prefer small, focused PRs.

PR title format: `[TKB-001] Add podcast ticker mention tracking foundation`

PR description should include:

```md
## Summary

## Task

TKB-001

## Changes

## Tests

## Notes
```

If a task is not complete, say so clearly.

## When blocked

If blocked:

1. Set task status to `blocked`.
2. Add a short blocked reason under the task.
3. Do not invent credentials or access.
4. Do not change unrelated code to bypass the blocker.

Example:

```md
### Blocked reason

FinMind API key is not available in local environment.
```

## `scripts/` boundary

`scripts/` is for local developer automation, GitHub sync utilities (e.g.
`sync_todo_to_github.py`), and one-off maintenance scripts. Do not put production
pipeline logic here — that belongs in `pipelines/`.

## Task-workflow Do Nots

- Treat GitHub Project as the source of truth.
- Rewrite the roadmap without explicit instruction.
- Implement more than one roadmap task at once.
