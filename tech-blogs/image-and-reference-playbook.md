# Image And Reference Playbook

This note defines how to make the technical blog posts feel more genuine, visual, and human
without exposing private project details.

## Editorial Principle

Images should explain a decision, not decorate the page. A good visual should help the reader
understand one of these things faster:

- Why the architecture exists.
- Where failure happens.
- How data moves.
- How deployment risk is reduced.
- What tradeoff the design is making.

Avoid generic laptop/server stock photos. Prefer diagrams, annotated screenshots with all private
details removed, hand-drawn-style architecture sketches, and simple charts.

## Image Types To Use

### 1. Architecture Diagram

Use for articles about pipeline, cache, deployment, and data migration.

Good placement:

- After the introduction.
- Before the methodology breakdown.

Format:

- Mermaid for draft.
- Recreate in Excalidraw, Figma, tldraw, or a generated image before publishing.

Human effect:

- Makes the post feel like it came from real system design work.
- Gives readers a shareable artifact.

### 2. Failure Mode Map

Use when the article discusses production lessons.

Examples:

- Pipeline stage failed after transcription.
- Cache returned stale schema.
- Staging used a different secret or callback URL.
- Worker concurrency caused retry storm.

Human effect:

- Shows battle scars without revealing private incidents.
- Makes the article less like a polished tutorial and more like engineering memory.

### 3. Checklist Image

Use for environment, release, QA, and migration articles.

Examples:

- Release readiness checklist.
- Data migration cutover checklist.
- Cache invalidation checklist.
- Agentic pipeline reliability checklist.

Human effect:

- Readers can save it.
- It turns the article into a practical artifact.

### 4. Before / After Chart

Use when explaining a methodology shift.

Examples:

- Linear LLM script vs recoverable data pipeline.
- Single production deploy vs staged promotion path.
- Direct database reads vs cached read model.
- Document-store-first schema vs relational serving model.

Human effect:

- Gives the article a clear narrative arc.

## Reference Strategy

References should be public, credible, and connected to a specific point.

Good reference types:

- Official docs for core technologies.
- Architecture pattern guides.
- Engineering blogs from infrastructure companies.
- Standards or protocol docs when relevant.

Avoid:

- Random SEO tutorials.
- Vendor pages that are only marketing.
- Links that do not support a concrete point in the article.

Recommended reference pattern:

1. Cite the official docs when introducing a tool or concept.
2. Cite one architecture guide when naming a pattern.
3. Cite one operational reference when discussing production concerns.

## How To Add Images To Each Article

For every article, add a `圖表與配圖建議` section with 2-4 entries:

- **Purpose**: what the image teaches.
- **Placement**: where it goes.
- **Caption**: the public caption.
- **Prompt**: optional image generation or designer brief.

When publishing, replace the prompt with the final asset using a normal Markdown image link.
Keep filenames generic and de-identified, for example
`recoverable-ingestion-pipeline.png`.

## Suggested First Image Assets

### Article 01: Agentic Ingestion Pipeline

1. `linear-vs-recoverable-pipeline.png`
   - Split-screen comparison of a linear LLM script and a recoverable pipeline with checkpoints.

2. `pipeline-state-machine.png`
   - State diagram showing discovered, fetched, transcribed, summarized, extracted, validated,
     persisted, failed, retry scheduled, and review required.

3. `concurrency-budget-dashboard.png`
   - Dashboard-style visual showing worker budgets by stage.

### Article 02: Dev / Staging / Production

1. `promotion-path-transit-map.png`
   - Transit-map style flow from feature branch to production.

2. `environment-responsibility-matrix.png`
   - Three-column comparison of dev, staging, and production.

3. `release-readiness-checklist.png`
   - Checklist-style visual for build, tests, migration, health check, cache policy, secrets, and
     rollback target.

## De-Identification QA For Images

Before publishing an image, check:

- No product or project names.
- No real hostnames, domains, database names, bucket names, or secret names.
- No real user emails, admin names, or internal issue IDs.
- No original business-domain examples.
- No screenshots showing private data.
- No API keys, tokens, request IDs, or logs.
