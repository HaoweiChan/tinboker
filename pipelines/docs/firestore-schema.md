# Firestore data contract

The canonical contract between the tinboker-agents pipeline (writer) and the
tinboker-platform backend (reader) lives in the **wiki Postgres**, served via
the existing wiki API:

- JSON: `https://api.tinboker.com/api/wiki/pages/contract/firestore-schema`
- Markdown: `https://api.tinboker.com/api/wiki/pages/contract/firestore-schema.md`

This makes both repos depend on a single live URL instead of duplicating the
schema in each repo's markdown.

**Authoring copy** (draft, edited via PR, then published to the wiki):
[docs/spec-from-platform.md](spec-from-platform.md). The platform team owns
this document because they're the reader; agents implement against it.

**Publish workflow** — after merging changes to `spec-from-platform.md`:
```bash
uv run python services/podcast/scripts/publish_contract.py \
  --slug firestore-schema \
  --file docs/spec-from-platform.md \
  --title "Firestore data contract (schema_version 2)" \
  --source docs/spec-from-platform.md
```

## Agent-side fulfillment status (schema_version 2)

| Spec section | Status | Code |
|--------------|--------|------|
| § 2 `episodes/{episode_id}` core fields | ✓ matches | [models/podcast_models.py](../services/podcast/src/models/podcast_models.py) |
| § 2 Spotify metadata | ✓ matches; backfill blocked on Spotify 403 (see [plan](../../../.claude/plans/here-s-the-verdict-from-recursive-frost.md)) | [pipeline/steps/download.py](../services/podcast/src/pipeline/steps/download.py) |
| § 2.3 #1 `released_at_ms` | ✓ written on new episodes | [models/podcast_models.py:_compute_released_at_ms](../services/podcast/src/models/podcast_models.py) |
| § 2.3 #3 `modified_*` preservation | ✓ writes use `merge=True`; no overwrite | [service/upload_to_firebase.py](../services/podcast/src/service/upload_to_firebase.py) |
| § 2.3 #5 `spotify_release_date` as string | ✓ normalized on write | same |
| § 2 `key_insights` (3–8 plain-text zh-TW) | ✓ generated in pipeline + written on new episodes; backfill script for existing | [content_builder/nodes/key_insights_extractor.py](../services/podcast/src/podcast/content_builder/nodes/key_insights_extractor.py), [models/podcast_models.py](../services/podcast/src/models/podcast_models.py), [scripts/backfill_key_insights.py](../services/podcast/scripts/backfill_key_insights.py) |
| § 3 `tickers/{ticker}/episodes/*` index | ✓ existing | [service/upload_to_firebase.py](../services/podcast/src/service/upload_to_firebase.py) |
| § 3 `tags/{tag}/episodes/*` index | ✓ existing | same |
| § 4 `ticker_insights/{episode_id}/tickers/{ticker}` | ✓ new (B1) | [exporters/ticker_insights.py](../services/podcast/src/podcast/exporters/ticker_insights.py) |
| § 4.2 5-tier sentiment label | ✓ derived from score at write | same |
| § 4.5 / § 4.6 backend & frontend rename | platform-side | n/a |
| § 5 `trending_tickers/{ticker}` | ✓ new (A1); nightly script | [exporters/trending_tickers.py](../services/podcast/src/podcast/exporters/trending_tickers.py), [scripts/refresh_trending_tickers.py](../services/podcast/scripts/refresh_trending_tickers.py) |
| § 6 platform-owned paths | not ours | n/a |
| § 7 backfill (Phase B2) | ✓ script ready | [scripts/backfill_ticker_insights.py](../services/podcast/scripts/backfill_ticker_insights.py) |
| § 10 Q3 backfill scope | confirmed via dry-run; ~13 docs / 2 sample episodes | same |

## Open items needing platform-team input

- **Spec § 10 Q1 — `trending_tickers` cadence.** Default is nightly. Hourly is
  doable; the existing `refresh_trending_tickers.py` is idempotent so the
  cadence is just a cron line.
- **Spec § 10 Q5 — soft-delete signal.** No mechanism today. We can add a
  `retracted_at` field on episode docs whenever the platform team specifies
  the semantics they want.
- **Spec § 10 Q8 — sentiment confidence band.** The extractor today emits a
  single score; would need a prompt + state.py update if confidence is
  required.

## Independent blocker

Spotify API returns 403 for every show on Client Credentials flow as of
2026-05-14. The spec's Spotify metadata fields can't be backfilled until the
upstream auth issue is resolved. This is documented separately in the
session plan; the `--rerun-from spotify-metadata` mode is correct and will
work once the API access is restored.

## Local-edit workflow

When you need to revise the contract:
1. Edit [docs/spec-from-platform.md](spec-from-platform.md) in a PR.
2. After merge to `main`, the publish script above writes the new body into
   `wiki_pages WHERE kind='contract' AND slug='firestore-schema'`.
3. Both repos refetch on next deploy — no version pinning needed.

To inspect the currently-published contract:
```bash
curl https://api.tinboker.com/api/wiki/pages/contract/firestore-schema.md
```
