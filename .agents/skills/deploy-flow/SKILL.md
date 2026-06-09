---
name: deploy-flow
description: Use when the user wants to deploy, ship, release, cut a tag, check what env a branch reaches, or verify a deploy. Walks through the develop→dev / main→staging / tag→prod pipeline, the required pre-merge checks, and the post-deploy verification steps.
---

Read `docs/workflows/deploy-flow.md` and walk the user through the procedure step-by-step. Do not execute server commands beyond the read-only set listed in that doc and in `AGENTS.md`. For destructive operations (manual rollback, single-env restart) confirm with the user before running.
