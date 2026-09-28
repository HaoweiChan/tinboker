# Documentation map

Start with the root [project guide](../CLAUDE.md) for architecture, hard rules, and the
read-first map. [TODO.md](../TODO.md) is the task source of truth.

## Current guides

| Need | Canonical document |
|---|---|
| VPS services, environment variables, and secrets | [Infrastructure runbook](infra-runbook.md) |
| Release and rollback | [Deploy workflow](workflows/deploy-flow.md) |
| Environment QA | [QA workflow](workflows/qa-flow.md) |
| Shared podcast/content fields | [Data contract](firestore-contract.md) and [change workflow](workflows/firestore-data-change.md) |
| Agent ownership by domain | [Agent guides](agents/) |
| Product and engineering tasks | [Task workflow](workflows/task-management.md) |
| Tag labels | [Tag vocabulary](tag-vocabulary-source-of-truth.md) |
| Social account credentials | [Social publishing tokens](social-publishing-tokens.md) |

The Firestore names in the data contract and workflow are historical. Current content
storage is VPS PostgreSQL and local media disk.

## Plans and records

`articles-platform-plan.md`, `seo-data-presentation-plan.md`, `fix-plans/`, and
`research/` record decisions and measurements made at their stated dates. Check live
code and [TODO.md](../TODO.md) before treating open items in those files as current work.
The `ai-ops/` directory contains agent working agreements and their maintenance protocol.
