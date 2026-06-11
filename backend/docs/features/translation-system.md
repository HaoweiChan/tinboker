# Stock Translation System - Implementation Summary

## Overview

This document provides a complete summary of the stock translation management system implementation. The system allows managing Chinese Traditional (ZH-TW) translations for stock tickers across multiple markets (US, TW, JP, etc.) with a web-based admin interface.

## Architecture

```
Frontend (WebUI)                Backend (FastAPI)                  Database (Cloud SQL)
┌────────────────┐             ┌────────────────────┐            ┌───────────────────┐
│ News Page      │────────────▶│ GET /api/stocks/   │───────────▶│ stock_translations│
│ (Show ZH names)│             │     translations   │            │                   │
└────────────────┘             └────────────────────┘            │ - ticker          │
                                                                  │ - market          │
┌────────────────┐             ┌────────────────────┐            │ - name_en         │
│ Admin Page     │◀───────────▶│ GET/PUT/POST       │◀──────────▶│ - name_zh_tw      │
│ /admin/trans   │             │ /api/admin/        │            │ - status          │
│                │             │   translations     │            │ - updated_by      │
│ - List/Edit    │             │                    │            │ - updated_at      │
│ - Search       │             │ Auth: Password     │            └───────────────────┘
│ - Bulk Import  │             └────────────────────┘
└────────────────┘
```

## Database Schema

### Table: `stock_translations`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| ticker | VARCHAR(20) | Stock ticker (e.g., "NVDA", "2330") |
| market | VARCHAR(10) | Market code ("US", "TW", "JP") |
| name_en | TEXT | English name from API |
| name_zh_tw | TEXT | Chinese Traditional translation |
| translation_status | VARCHAR(20) | "pending", "approved", "auto" |
| last_updated_by | VARCHAR(100) | Email/username of last editor |
| last_updated_at | TIMESTAMP | Last modification time |
| created_at | TIMESTAMP | Creation time |

**Constraints:**
- `UNIQUE (ticker, market)` - One translation per ticker per market
- `INDEX (ticker, market)` - Fast lookups
- `INDEX (market)` - Filter by market
- `INDEX (translation_status)` - Filter by status

## Backend Implementation

### File Structure

```
tinboker/backend/
├── src/
│   ├── database/
│   │   ├── postgres.py              [NEW] PostgreSQL connection & session
│   │   ├── models.py                [NEW] SQLAlchemy ORM models
│   │   └── migrations/
│   │       └── init_postgres.py     [NEW] Initial migration script
│   ├── services/
│   │   └── translation_service.py   [NEW] Translation business logic
│   ├── routers/
│   │   ├── translations.py          [NEW] Public translation API
│   │   └── admin_translations.py    [NEW] Admin translation management
│   ├── schemas/
│   │   └── translation.py           [NEW] Pydantic models
│   └── auth/
│       └── admin_auth.py            [NEW] Simple password auth
├── data/
│   ├── seed_data.py                 TRANSLATIONS (curated TW + core)
│   └── us_stocks.py                 US_STOCK_TRANSLATIONS
├── scripts/
│   └── ops/cleanup_translations.py  Data-quality maintenance sweep
└── docs/
    ├── GCP_CLOUD_SQL_SETUP.md       [CREATED] Cloud SQL setup guide
    └── TRANSLATION_SYSTEM.md         [THIS FILE]
```

### API Endpoints

#### Public API (No Auth Required)

```
GET /api/stocks/translations/{ticker}?market={market}
Response: {"ticker": "NVDA", "market": "US", "name_en": "NVIDIA CORP", "name_zh_tw": "輝達"}
```

#### Admin API (Password Protected)

```
# Authentication
POST /api/admin/auth/login
Body: {"password": "admin_password"}
Response: {"access_token": "..."}

# List translations
GET /api/admin/translations?market=US&status=approved&page=1&limit=50
Response: {
  "total": 1500,
  "page": 1,
  "items": [...]
}

# Update translation
PUT /api/admin/translations/{id}
Body: {"name_zh_tw": "輝達", "translation_status": "approved"}
Response: {"success": true}

# Bulk import
POST /api/admin/translations/bulk-import
Body: CSV or JSON array
Response: {"imported": 150, "updated": 20}

# Get missing translations
GET /api/admin/translations/missing?market=US
Response: {items: [{ticker: "PLTR", name_en: "..."}]}
```

### Authentication

Simple password-based auth using JWT:
- Password stored in `.env` as `ADMIN_PASSWORD`
- Login returns JWT token
- Token required in `Authorization: Bearer {token}` header
- Token expires after 24 hours

## Frontend Implementation

### File Structure

```
tinboker/frontend/
├── src/
│   ├── pages/
│   │   ├── AdminTranslationsPage.tsx    [NEW] Admin UI for translations
│   │   └── NewsPage.tsx                  [MODIFIED] Use ZH-TW translations
│   ├── services/
│   │   └── api/
│   │       └── translations.ts           [NEW] Translation API client
│   ├── components/
│   │   ├── admin/
│   │   │   ├── TranslationTable.tsx      [NEW] Editable table
│   │   │   ├── TranslationFilters.tsx    [NEW] Search & filters
│   │   │   └── BulkImportDialog.tsx      [NEW] CSV import UI
│   │   └── auth/
│   │       └── AdminLogin.tsx            [NEW] Login form
│   └── types/
│       └── translation.ts                [NEW] TypeScript types
```

### Admin UI Features

1. **Translation Table**
   - Inline editing of Chinese names
   - Search by ticker or name
   - Filter by market, status
   - Pagination (50 per page)
   - Auto-save on blur

2. **Bulk Import**
   - Upload CSV file
   - Format: `ticker,market,name_en,name_zh_tw`
   - Preview before import
   - Shows import results

3. **Missing Translations View**
   - List stocks without ZH-TW translation
   - Sorted by view count (most popular first)
   - Quick "Add Translation" action

4. **Authentication**
   - Simple password login page
   - Token stored in localStorage
   - Auto-redirect on auth failure

### Display Format

**News Page - Related Assets:**

When translation exists:
```
NVDA 輝達
AAPL 蘋果
2330 台積電
```

When translation missing:
```
PLTR Palantir Technologies Inc.
CVNA CARVANA CO.
```

Implementation in `NewsPage.tsx`:
```typescript
name: stock.name_zh_tw 
  ? `${stock.ticker.split('.')[0]} ${stock.name_zh_tw}`
  : `${stock.ticker.split('.')[0]} ${stock.name}`,
```

## Seeding & Data Maintenance

Seeding is **automatic** — there is no seed script to run. On every startup the app
reconciles `stock_translations` from the data modules (`src/main.py` lifespan →
`TranslationService.backfill_translations`):

- `src/data/seed_data.py` — `TRANSLATIONS` (curated TW + core stocks)
- `src/data/us_stocks.py` — `US_STOCK_TRANSLATIONS`

Brand colors are **not** seeded from code. `stock_translations.brand_color` is the
source of truth and is maintained through the admin portal or bulk JSON import.

The reconciler is **insert / fill-stub only**: it adds missing rows and fills empty
auto-created stubs, but **never overwrites an `approved` row**. The maintenance model:

1. **Bulk / new tickers** → add to the data module above; they land on next boot.
2. **Edits & promotions** (`auto`/`pending` → `approved`, fixing a zh-TW name or color)
   → admin portal (`/admin/translations`) or `POST /api/admin/translations/bulk-json`.
   These own existing rows — editing the data module will not overwrite them.
3. **Data-quality sweeps** → `python scripts/ops/cleanup_translations.py --dry-run`.

> The old one-off scripts (`migrate_ticker_json.py`, `seed_translations.py`,
> `enrich_us_stocks.py`) were removed once the startup reconciler subsumed them.

## Environment Variables

Add to `.env`:

```bash
# PostgreSQL (Cloud SQL)
USE_POSTGRES=true
POSTGRES_HOST=<CLOUD_SQL_IP>
POSTGRES_PORT=5432
POSTGRES_DB=podcast_db
POSTGRES_USER=podcast_user
POSTGRES_PASSWORD=<password>

# Admin authentication
ADMIN_PASSWORD=choose_a_secure_password

# Optional: Admin token secret (auto-generated if not set)
ADMIN_JWT_SECRET=random_secret_key_here
```

## Docker Configuration

Update `Dockerfile`:

```dockerfile
# No changes needed - already includes PostgreSQL support
# psycopg2-binary is in requirements.txt
```

Update `docker-compose.yml` (if using):

```yaml
services:
  backend:
    environment:
      - USE_POSTGRES=true
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
```

## Deployment Steps

### 1. Set Up Cloud SQL

Follow `docs/GCP_CLOUD_SQL_SETUP.md`

### 2. Update Environment

```bash
# On Netcup VPS
cd /path/to/tinboker
nano .env  # Add PostgreSQL settings
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Migrations

```bash
# Create tables
python -m src.database.migrations.init_postgres

# Translations seed automatically on app startup (see "Seeding & Data Maintenance").
# Optionally run a data-quality pass afterwards:
python scripts/ops/cleanup_translations.py --dry-run
```

### 5. Deploy

```bash
# If using Docker
docker-compose up -d --build

# If using systemd
systemctl restart tinboker-backend
```

### 6. Access Admin UI

Navigate to: `https://dev.tinboker.com/admin/translations`

Login with password from `.env`

## Testing Checklist

- [ ] Cloud SQL connection works
- [ ] Tables created successfully
- [ ] Migration scripts run without errors
- [ ] API endpoints return translations
- [ ] Admin login works
- [ ] Admin UI loads and displays translations
- [ ] Inline editing saves correctly
- [ ] Bulk import works
- [ ] News page shows "TICKER 中文名" format
- [ ] Fallback to English when no translation

## Maintenance

### Adding New Translations

1. **Via Admin UI:**
   - Go to /admin/translations
   - Click "Add" or edit existing row
   - Enter Chinese name
   - Save

2. **Via Bulk Import:**
   - Prepare CSV file
   - Upload via admin UI
   - Review and confirm

3. **Programmatically:**
   ```python
   from src.services.translation_service import TranslationService
   service = TranslationService()
   service.create_or_update("PLTR", "US", "Palantir Technologies Inc.", "帕蘭提爾")
   ```

### Finding Missing Translations

```bash
# Via API
curl https://api.tinboker.com/api/admin/translations/missing?market=US

# Or use admin UI "Missing Translations" tab
```

### Backup & Restore

```bash
# Backup translations table
pg_dump -h <CLOUD_SQL_IP> -U podcast_user -t stock_translations podcast_db > translations_backup.sql

# Restore
psql -h <CLOUD_SQL_IP> -U podcast_user podcast_db < translations_backup.sql
```

## Performance Considerations

1. **Database Indexes:** Already created on `(ticker, market)` for fast lookups
2. **Caching:** Consider adding Redis cache for frequently accessed translations
3. **Pagination:** Admin UI uses server-side pagination (50 items/page)
4. **Connection Pooling:** SQLAlchemy configured with pool_size=10

## Security

1. **Admin Password:** Strong password required, stored in env var
2. **JWT Tokens:** 24-hour expiration
3. **HTTPS:** Ensure dev.tinboker.com uses SSL
4. **Database:** Cloud SQL with authorized networks only
5. **No SQL Injection:** SQLAlchemy ORM prevents injection

## Future Enhancements

- [ ] Add more languages (Japanese, Korean)
- [ ] Auto-translation suggestions via API
- [] Translation quality voting
- [ ] Audit log for all changes
- [ ] Export to CSV functionality
- [ ] Search with fuzzy matching
- [ ] Real-time collaboration (WebSocket)

---

**Next Steps:** Proceed with implementation as outlined in this document.
