# Tinboker Agent Instructions

This file defines how AI coding agents should work in the Tinboker repository.

Tinboker is a Taiwanese stock and podcast intelligence platform.

## Repository Structure

Expected structure:

```text
frontend/   React 19, TypeScript, Vite, Zustand, Cloudflare Pages
backend/    FastAPI, Python 3.12, Docker, Caddy reverse proxy on Netcup VPS
pipelines/  Python uv workspace for ingestion, transcription, summarization, entity extraction, and knowledge graph jobs
scripts/    Developer automation scripts
```

Core infrastructure and data:

```text
PostgreSQL / Cloud SQL
Firestore
Redis 7-alpine
Google OAuth
Cloudflare Pages
Netcup Debian VPS
```

External integrations:

```text
Massive API for US stocks
FinMind for TW stocks
Spotify
Tavily
Threads / Meta APIs where available
```

## Task Source of Truth

`TODO.md` is the single source of truth for product and engineering tasks.

GitHub Issues and GitHub Projects are derived mirrors only.

Agents must not treat GitHub Issues or GitHub Projects as authoritative planning sources.

If task status, priority, scope, or acceptance criteria differ between GitHub and `TODO.md`, follow `TODO.md`.

## Standard Workflow

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
11. Run the sync script if GitHub mirrors should be updated.

Sync command:

```bash
python scripts/sync_todo_to_github.py
```

Do not manually edit GitHub Project fields unless the sync script fails.

## Task Metadata Format

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

Valid status values:

```text
idea
ready
in_progress
blocked
review
done
wont_do
```

Valid priority values:

```text
P0
P1
P2
icebox
```

Valid area values:

```text
frontend
backend
pipelines
infra
seo
product
scripts
docs
```

Valid type values:

```text
feature
bug
refactor
experiment
content
infra
docs
```

## Implementation Boundaries

Respect the repo boundaries.

### frontend/

Use for:

- UI
- React components
- pages
- routing
- client-side state
- SEO metadata rendering
- structured data
- admin surfaces

Do not place ingestion jobs or API logic in `frontend/`.

### backend/

Use for:

- FastAPI endpoints
- authentication
- database models
- API schemas
- admin APIs
- service orchestration
- cache access
- permission checks

Do not place long-running ingestion pipelines in request handlers.

### pipelines/

Use for:

- podcast ingestion
- transcription
- summarization
- ticker / sector extraction
- scheduled jobs
- wiki / knowledge graph generation
- market data batch jobs
- LLM batch generation

Do not put frontend UI or synchronous API request logic here.

### scripts/

Use for:

- local developer automation
- GitHub sync utilities
- one-off maintenance scripts
- repo automation

Do not put production pipeline logic here.

## Stability Rules

Prioritize stability over cleverness.

For backend and pipelines:

- Add timeouts for external API calls.
- Add retries with backoff where appropriate.
- Avoid unbounded concurrency.
- Avoid large in-memory batch processing.
- Use Redis caching for repeated external API or expensive computed results.
- Make jobs idempotent where possible.
- Log enough context to debug failures.
- Do not swallow exceptions silently.
- Avoid changing production database schema without migrations.

For frontend:

- Avoid layout shifts.
- Keep route-level bundles small.
- Use semantic HTML where possible.
- Add useful loading and error states.
- Avoid blocking rendering with unnecessary client-side requests.

## External API Rules

For Massive, FinMind, Spotify, Tavily, Threads, and other external services:

- Add explicit timeout.
- Handle rate limits.
- Cache stable responses.
- Log provider errors with provider name and endpoint context.
- Avoid leaking API keys to frontend.
- Avoid doing provider calls directly from React.
- Prefer backend or pipelines as integration layer.

## Financial Content Rules

Tinboker can provide market intelligence and source-grounded summaries.

Avoid creating output that sounds like direct investment advice.

Use language such as:

- "mentioned by podcasts"
- "historical performance after mention"
- "possible bull case"
- "possible bear case"
- "risk factors"
- "not investment advice"

Avoid first-version output such as:

- "buy"
- "sell"
- "target price"
- "guaranteed"
- "must enter"
- "sure win"

## SEO Rules

Tinboker should generate indexable, source-grounded pages.

Important surfaces:

- ticker pages
- sector pages
- podcast show pages
- episode pages
- newsletter pages
- topic pages

For frontend work:

- Add title and description metadata.
- Add canonical URL where appropriate.
- Add Open Graph metadata.
- Prefer semantic HTML.
- Use JSON-LD where useful.
- Avoid hiding all important content behind client-only rendering if SEO is important.

Potential structured data:

- PodcastSeries
- PodcastEpisode
- Article
- BreadcrumbList
- Organization
- WebPage

## GitHub Sync Rule

`TODO.md` is authoritative.

The sync script may create or update GitHub Issues and add them to GitHub Projects.

Agents should not create duplicate issues manually.

Before creating GitHub items, check whether `github_issue` and `github_project_item` already exist in the task metadata.

## Commit and PR Guidance

Prefer small, focused PRs.

PR title format:

```text
[TKB-001] Add podcast ticker mention tracking foundation
```

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

## When Blocked

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

## Do Not Do

Do not:

- Treat GitHub Project as the source of truth.
- Rewrite the roadmap without explicit instruction.
- Implement more than one roadmap task at once.
- Add large dependencies without justification.
- Put secrets in code.
- Add scraping logic that violates platform terms without explicit review.
- Generate investment recommendations as direct advice.
- Break the develop -> dev, main -> staging, tags -> prod deployment flow.
