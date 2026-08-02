# Technical Blog Roadmap

This is a local-only planning note for personal website articles. Keep public-facing drafts
de-identified: describe reusable architecture patterns and avoid project names, original business
domain specifics, internal URLs, secrets, repository paths, and provider-specific details.

## Series Frame

**從單體產品到可演進的 AI-Native 系統：我如何設計一個全端內容與知識平台**

Public positioning:

- Use **market ticker data** instead of domain-specific market examples.
- Use **unstructured media streams** instead of original content-source details.
- Use **domain knowledge graph** instead of domain-specific knowledge graph language.
- Focus on methodology, tradeoffs, production constraints, and reusable design patterns.

## Recommended Publishing Order

1. **如何用 Async Python 打造 Agentic Ingestion Pipeline**
   - Core angle: ingestion is not "call LLM and save result"; it is a reliability system.
   - Cover: uv workspace, async task orchestration, transcription, summarization, entity extraction,
     retries, idempotency keys, partial failure recovery.

2. **Dev / Staging / Production：小團隊也需要的環境分層策略**
   - Core angle: environment separation is a product velocity tool, not DevOps ceremony.
   - Cover: branch-to-env mapping, preview deploys, health checks, secrets per env, gated production
     releases, rollback/tag strategy.

3. **FastAPI + Redis：高讀取量 API 的快取分層設計**
   - Core angle: not all endpoints deserve the same TTL.
   - Cover: Redis TTL by freshness requirement, CDN `s-maxage`, browser cache, cache stampede
     prevention, stale data tradeoffs.

4. **從 Firestore 到 PostgreSQL：混合資料層的遷移方法論**
   - Core angle: document databases are great for velocity; relational databases become necessary
     when query shape stabilizes.
   - Cover: dual-read/dual-write, canonical contracts, backfill, schema ownership, migration
     checkpoints.

5. **React 19 + Zustand + Zod：前端資料邊界怎麼設計才不會崩**
   - Core angle: frontend robustness starts at the API boundary.
   - Cover: response validation, typed stores, loading/error states, stale data, API client layering,
     feature flags per environment.

6. **Domain Knowledge Graph：如何把非結構化內容變成可查詢的知識庫**
   - Core angle: summaries are not enough; durable knowledge needs entities, relationships,
     provenance, and incremental updates.
   - Cover: entity extraction, graph schema, source attribution, deduplication, query API design.

7. **用 Caddy + Docker + VPS 建立低成本但可維運的後端部署架構**
   - Core angle: you do not always need Kubernetes to build a serious production system.
   - Cover: reverse proxy, HTTPS, containers, health checks, logs, Redis, deployment constraints.

8. **OAuth-Gated App 的 E2E 測試：如何設計安全的非正式環境登入捷徑**
   - Core angle: automated QA cannot depend on real OAuth flows.
   - Cover: non-production-only bypass, secret token, JWT issuance, browser automation, hard
     production guardrails.

## Redaction Checklist For Every Draft

- No project/product names.
- No original business-domain specifics.
- No region-specific market examples or providers.
- No internal hostnames, secret names, repository paths, bucket names, or database names.
- Code examples use neutral names such as `MarketTicker`, `MediaIngestionJob`, `KnowledgeNode`,
  `PipelineTask`, and `DomainEntity`.
- Metrics are synthetic, rounded, or framed as illustrative ranges unless already safe and public.
