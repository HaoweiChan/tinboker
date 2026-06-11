# backend/scripts

Operational and one-off scripts. **Run everything from the `backend/` directory** (not from
inside `scripts/`), either as a module (`python -m scripts.<group>.<name>`) or by path
(`python scripts/<group>/<name>.py`). Scripts that touch the DB respect the same
`USE_POSTGRES` / `POSTGRES_*` env vars as the app.

```
scripts/
├── seed/   one-off bootstrap loaders (run once on a fresh database)
├── ops/    operational / maintenance tools (safe to re-run)
└── dev/    local developer utilities (no production effect)
```

## seed/ — one-off bootstrap

| Script | Purpose |
|--------|---------|
| `load_graph_data.py` | Load the concept graphs (robotics / ai / energy) directly into the DB. |
| `load_graph_data_api.py` | Same graphs, loaded over HTTP against a running API (`--url`). |

```bash
python -m scripts.seed.load_graph_data
python scripts/seed/load_graph_data_api.py --url https://api.tinboker.com
```

## ops/ — maintenance

| Script | Purpose |
|--------|---------|
| `cleanup_translations.py` | Data-quality pass over `stock_translations`: de-dupes, fixes Chinese text mis-filed in `name_en`, strips legal suffixes, normalizes title case. Run with `--dry-run` first. |
| `dev_with_remote.sh` | Start the local backend pointed at a remote (Tailscale) Redis. |
| `install_remote_redis_docker.sh` | Provision a Dockerized Redis on a remote host (run *on* that host). |

```bash
python scripts/ops/cleanup_translations.py --dry-run   # preview
python scripts/ops/cleanup_translations.py             # apply
```

## dev/ — local utilities

| Script | Purpose |
|--------|---------|
| `compare_openapi_schemas.py` | Diff two OpenAPI snapshots in `src/schemas/`. |
| `test_secret_loader.py` | Smoke-test the GCP Secret Manager config loader. |

---

## Stock-translation seeding (no script needed)

Translation seeding **is not a script anymore.** The app reconciles `stock_translations`
from the data modules on every startup (`src/main.py` lifespan → `TranslationService.backfill_translations`):

- `src/data/seed_data.py` — `TRANSLATIONS` (curated TW + core stocks)
- `src/data/us_stocks.py` — `US_STOCK_TRANSLATIONS` (US stocks)
Brand colors are **not** seeded from code. `stock_translations.brand_color` is the
source of truth and is maintained through the admin portal or bulk JSON import.

The reconciler is **insert / fill-stub only**: it adds missing rows and fills empty
auto-created stubs, but never overwrites an `approved` row. So the maintenance model is:

1. **Bulk / new tickers** → add to the data module above; they land on next boot.
2. **Edits & promotions** (`auto`/`pending` → `approved`, fixing a name or color) →
   admin portal (`/admin/translations`) or `POST /api/admin/translations/bulk-json`.
   These are the source of truth for existing rows — editing the data module will *not*
   overwrite them.
3. **Data-quality sweeps** → `scripts/ops/cleanup_translations.py`.

> Removed in this refactor (superseded by the startup reconciler): `seed_translations.py`,
> `enrich_us_stocks.py`, and the one-off `migrate_ticker_json.py`.
