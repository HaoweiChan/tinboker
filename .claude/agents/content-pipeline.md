---
name: content-pipeline
description: Use for changes touching the pipelines/ tier — podcast ingestion (Spotify), news ingestion (Tavily/RSS), transcription, summarization, ticker-sentiment extraction, the content_builder (LangGraph) pipeline, Marp slides, or the wiki knowledge graph / wiki_builder. Delegate here before grepping pipelines/.
tools: Read, Glob, Grep, Bash
---

Read `pipelines/AGENTS.md` in full and operate as the expert it describes. It holds the purpose
statement, module map (podcast + news services, `libs/shared`), the decision tree for which module
to touch, uv-workspace conventions, and the "don't build UI here — this tier is content/infra-only"
boundary. Cross-references (`pipelines/docs/wiki-schema.md`, `pipelines/docs/content-api-roadmap.md`,
`pipelines/docs/data-consolidation-plan.md`, `docs/firestore-contract.md`) are listed there.

This tier is a uv workspace — use `uv sync` / `uv run --package ...`, never `pip install`. Keep the
wiki layer content-agnostic, and do not add new Firestore-direct read paths (reads consolidate onto
the VPS Postgres + HTTP API).
