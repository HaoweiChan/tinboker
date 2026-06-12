# Tag vocabulary — single source of truth

**Status:** implemented · **Supersedes:** the hand-synced triple-copy that caused the
English-tag prod bug fixed in [#161](https://github.com/HaoweiChan/tinboker/pull/161)
and [#162](https://github.com/HaoweiChan/tinboker/pull/162).

## The problem

The English→zh-TW tag label catalogue lived in three places with three different key
conventions, kept in sync by hand:

| Copy | Location | Key form | Purpose |
|------|----------|----------|---------|
| Pipeline `TAG_DISPLAY` | `pipelines/.../content_builder/tag_vocabulary.py` | PascalCase (`SupplyChain`) | extraction vocab injected into the writer prompt |
| Backend `_CANONICAL_DISPLAY` | `backend/src/tag_registry.py` | lowercased (`supplychain`) | display labels merged into `/api/tags/registry` |
| DB `tag_registry` (seeded from `_SEED`) | Postgres / `/admin/tags` | snake_case (`supply_chain`) | the **trending gate** (`trending_slugs`) |

When a new tag was added to the pipeline vocabulary, nobody automatically updated the
backend — so the website rendered the raw English slug. `_CANONICAL_DISPLAY` was itself a
band-aid (PR #162): a *second* hand-typed copy of the pipeline dict, which is exactly the
kind of duplication that drifts.

Three key conventions for one concept (`SupplyChain` / `supply_chain` / `supplychain`)
meant the same tag could silently fail to match across extraction, storage, registry, and
the frontend.

## The constraint

`backend/` and `pipelines/services/podcast/` ship as **separate Docker images with disjoint
build contexts** (`./backend` vs `./pipelines`). Neither can import the other, and a
repo-root shared file is not inside either image. So each runtime needs its own *physical*
copy of the data — a single imported module is not achievable without risky build-context
surgery (and the data is 29 rows; not worth it).

## The design

**One hand-edited canonical data file + a generated, drift-tested mirror.**

```
pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json   ← CANONICAL (hand-edited)
backend/src/data/tag_vocabulary.json                                         ← GENERATED MIRROR (do not edit)
scripts/sync_tag_vocabulary.py                                               ← canonical → mirror
```

- **Pipeline** (`tag_vocabulary.py`) loads `TAG_DISPLAY` from the canonical JSON. The dict
  literal is gone.
- **Backend** (`tag_registry.py`) loads `_CANONICAL_DISPLAY` from the committed mirror. The
  dict literal is gone. `registry_snapshot()` and `trending_slugs()` behave identically —
  the JSON reproduces the old lowercased keys byte-for-byte, so `/api/tags/registry` is
  unchanged.
- **Sync:** edit the canonical JSON, then run `python scripts/sync_tag_vocabulary.py`. The
  mirror carries a `_comment` provenance banner (JSON has no comments) that loaders skip.
- **Drift guard:** `scripts/sync_tag_vocabulary.py --check` plus unit tests in **both** the
  backend and pipelines suites (`test_tag_vocabulary_sync.py`) fail if the two files
  disagree. CI checks out the full repo, so either side's test can compare across trees.
  The pipelines-side test is what catches the realistic path — a vocab edit that touches
  `pipelines/**` and triggers Pipelines CI.

### Why the pipeline owns the canonical

New tags are *born* in the writer prompt (the LLM is told the known slug list). The pipeline
is the de-facto author of the vocabulary, so it holds the editable copy; the backend is a
pure consumer and gets the generated mirror.

### Why not "DB as the single source"

The DB `tag_registry` is admin-editable and serves the **trending gate**, a distinct concern
in a distinct (snake_case, legacy Firestore-tag) namespace. Making the pipeline read display
labels from the DB at content-build time would add a fragile network dependency to the
extraction prompt and couple two unrelated lifecycles. We kept the gate exactly as-is and
only consolidated the *label catalogue*.

## The key convention: one `normalize_tag_slug`

A single normalization — **lowercase, then strip every non-alphanumeric char** — reconciles
all three forms to one key:

```
SupplyChain  →  supplychain
supply_chain →  supplychain
supplychain  →  supplychain
```

Implemented identically in three places (kept in sync by the comment cross-references and
the collision test):

- `pipelines/.../tag_vocabulary.py::normalize_tag_slug` — extraction-side `display_for`
- `backend/src/tag_registry.py::normalize_tag_slug` — registry baseline keys
- `frontend/src/hooks/useTagLabels.ts::normalizeTagSlug` — `tagLabelFor` + registry map build
  (and the topics-cloud page, which now reuses the shared helper instead of its own copy)

The backend baseline keys equal the previous lowercased keys (the canonical slugs have no
separators), so the `/api/tags/registry` response shape and entries are unchanged. The
normalization is *additive* on the frontend: a raw `supply_chain` tag now also resolves to
供應鏈 instead of falling through to "supply chain". `test_normalize_has_no_conflicting_collisions`
proves the collapse is lossless (no two source slugs normalize to the same key with different
labels), so keying the frontend map by the normalized slug is safe.

## Adding or changing a tag

1. Edit `pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json`.
2. Run `python scripts/sync_tag_vocabulary.py`.
3. Commit both JSON files. CI's drift test enforces step 2.

(The DB `tag_registry` / `_SEED` and the trending gate are a separate, admin-managed concern
— untouched by this flow.)
