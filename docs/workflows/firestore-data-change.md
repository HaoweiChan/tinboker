# Firestore data change workflow

Procedure for adding, modifying, or reading Firestore data, or for changing the cross-repo data contract with the `tinboker-agents` pipeline.

## Hard rule: no new Firestore-direct read paths

The platform is consolidating Firestore reads behind the VPS Postgres + the upcoming HTTP API (Phase A/B in [`../firestore-contract.md`](../firestore-contract.md) §7). Existing direct reads stay; **new** ones do not.

If you're tempted to add a new Firestore-direct read path, stop and do one of these instead:

1. Use an existing endpoint in [`backend/src/routers/`](../../backend/src/routers/) that already reads the data.
2. Add the read to the planned HTTP API surface (coordinate with the agents team).
3. If neither is possible and it's genuinely urgent, write a Phase A/B-style stop-gap AND mark it as such in code + open a tracking issue.

Do NOT silently introduce a fourth read path — the data contract is the bottleneck, not the code.

## Before any Firestore schema or write change

1. **Read [`../firestore-contract.md`](../firestore-contract.md) §1 (ownership matrix)** to confirm whether the field/collection is platform-owned or agents-owned.
2. If it's agents-owned (most episode/ticker/insight fields):
   - This change requires coordination with the `tinboker-agents` team.
   - Update [`../firestore-contract.md`](../firestore-contract.md) with the proposed change before writing any code.
   - Bump `schema_version` in the section affected.
3. If it's platform-owned (`users/*`, `users/*/notifications/*`, the `modified_*` fields on episodes):
   - The platform team can change it unilaterally.
   - Still update [`../firestore-contract.md`](../firestore-contract.md) so the contract stays accurate.

## Adding a field to `episodes`

1. Add the field to [`backend/src/models/podcast.py`](../../backend/src/models/podcast.py) (Pydantic v2 style — see [`backend/AGENTS.md`](../../backend/AGENTS.md#pydantic-models)).
2. Update [`backend/src/services/episode_transformer.py`](../../backend/src/services/episode_transformer.py) to normalize the raw Firestore doc into the new shape.
3. Add the field to the frontend type in [`frontend/src/services/types.ts`](../../frontend/src/services/types.ts) (and to any Zod schema in [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts) that validates it).
4. Update the "Per-surface field consumption" table in [`../firestore-contract.md`](../firestore-contract.md) §2.2 if any UI starts consuming it.
5. If the field is agents-fulfilled, list it in §2.1 with type and fulfillment expectation (`always` / `usually` / `sometimes` / `never`).

## Modifying `created_time` — DON'T

`created_time` is immutable after first write. The notification fan-out service uses it to detect new episodes; mutating it re-fires `new_episode` notifications. See [`../firestore-contract.md`](../firestore-contract.md) §6.3.

If you genuinely need a new timestamp, follow the §2.3 cleanup #1 pattern: add a NEW field (e.g. `released_at_ms`), leave `created_time` alone, migrate readers.

## Adding a new collection

1. Update [`../firestore-contract.md`](../firestore-contract.md) §1 (ownership matrix) with: writer, reader(s), lifecycle.
2. Add a new section to the contract detailing the document schema.
3. If platform-owned: add Pydantic models in `backend/src/models/`, DB access in `backend/src/database/`, service in `backend/src/services/`, router in `backend/src/routers/`.
4. If agents-owned: spec the schema first, get tinboker-agents review, only then add backend readers.

## Reading existing data

Pattern (matches what's already in use):

```python
# In backend/src/services/<thing>_service.py
from src.services.firestore_service import get_firestore_client
from src.cache.redis_client import cache_get, cache_set

async def get_thing(thing_id: str) -> Optional[Thing]:
    cache_key = f"thing:{thing_id}"
    cached = await cache_get(cache_key)
    if cached:
        return Thing(**json.loads(cached))

    db = get_firestore_client()
    doc = db.collection("things").document(thing_id).get()
    if not doc.exists:
        return None
    thing = Thing(**doc.to_dict())
    await cache_set(cache_key, thing.model_dump_json(), CACHE_TTL["thing"])
    return thing
```

This is the only acceptable pattern. Do not introduce a new Firestore client abstraction.

## Cleanup proposals (require agents-team coordination)

These are documented in [`../firestore-contract.md`](../firestore-contract.md) §2.3 but not yet executed. If a current task is blocked on one of these, propose it formally to the agents team before working around it locally:

1. Add `released_at_ms: int` (Unix ms) on episodes for timezone-safe sort.
2. Audit `*_url` / `*_public_url` pairs; drop the public-URL half where backend can sign on demand.
3. Codify `modified_*` as platform-only with `merge=True` excluding them.
4. Document `*_content` fields as cache, not source — agents must rewrite `*_content` when rewriting the GCS file in the same commit.
5. Normalize `spotify_release_date` to string `YYYY-MM-DD`.

## Phase A/B migration status

Per [`../firestore-contract.md`](../firestore-contract.md) §7:

- **Phase A** (`trending_tickers` → Firestore) — in progress. Unblocks the empty Stock Index in prod (Postgres `pool_not_initialized`).
- **Phase B** (`ticker_insights` → Firestore, replacing per-episode Postgres recs) — in progress. New router [`backend/src/routers/ticker_insights.py`](../../backend/src/routers/ticker_insights.py) and service [`backend/src/services/insight_service.py`](../../backend/src/services/insight_service.py) coexist with legacy [`backend/src/routers/recommendations.py`](../../backend/src/routers/recommendations.py).
- **Phase C** (episode-shape cleanups) — not started.

If your change touches `ticker_insights` or `trending_tickers`, treat the in-progress migration as live work — bring proposals to the contract before adding to either path.

## Cross-references

- The canonical data contract: [`../firestore-contract.md`](../firestore-contract.md)
- Podcast/episode domain reference: [`../agents/podcast-domain.md`](../agents/podcast-domain.md)
- Stock-data domain reference: [`../agents/stock-data.md`](../agents/stock-data.md)
- Backend code style (Pydantic, async, caching): [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
