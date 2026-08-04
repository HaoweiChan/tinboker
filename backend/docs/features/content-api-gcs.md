# Content API (supply-chain articles)

> Filename kept for link stability — GCS is gone. This was the tutorial for the
> original GCS-backed implementation; since the decommission
> (docs/firestore-contract.md § 11.7) the router serves the copied article tree
> from local disk.

`backend/src/routers/content.py` exposes the supply-chain articles (Markdown + SVG)
that were copied out of the `graphfolio-articles` bucket into
`{MEDIA_STORAGE_ROOT}/graphfolio-articles/` (both bucket-era layouts survive:
`blog/md/…` + `blog/svg/…`, and `articles/{ticker}/…`).

- `GET /api/content/index` — globs the tree for `*_supply_chain*` files and returns
  `{"tickers": [...]}`.
- `GET /api/content/{ticker}` — returns `{ticker, svg_url, article_url, ttl_seconds}`.
  URLs are stable public media URLs (`MEDIA_PUBLIC_BASE`, served by Caddy);
  `ttl_seconds` is pinned to 0 (nothing expires) and kept only for response-shape
  compatibility.

Env: only the media-store pair `MEDIA_STORAGE_ROOT` / `MEDIA_PUBLIC_BASE`
(defaults in `backend/src/services/gcs_content.py`). The old `CONTENT_BUCKET`,
`CONTENT_PREFIX`, and `CONTENT_URL_TTL` vars are gone.

Tests: `backend/tests/unit/test_content_router.py`.
