# Translation backfill agent — runbook

An agentic pipeline that fills in missing stock translations (zh-TW name + brand
color) for tickers discovered from podcast episodes, using this MCP server.

## Lifecycle

```
related_tickers (written by the agents pipeline)
      │
      ▼
[DISCOVERY]  backend on-ingest hook (GET /api/episodes/recent)
   → inserts PENDING stub rows (symbol + inferred market, no name)
      │
      ▼
[RESOLUTION] this backfill agent (status: pending → auto)
   list_pending_translations → search_stocks (dedupe) → research → propose_translations
      │
      ▼
[REVIEW]  human promotes auto → approved in the admin portal
      │
      ▼
cards render display_name + brand chip (auto rows show immediately)
```

Discovery is automatic and read-freeze-safe: it reuses episodes already fetched and
inserts stubs in a throttled background task. The agent never has to crawl episodes.

## Tools used (require `TINBOKER_WRITE_TOKEN`)

- `list_pending_translations(limit, market?)` — the work queue (status=pending stubs).
- `search_stocks(query, market?)` — dedupe / find an existing variant before researching.
- `propose_translations(items)` — write results back as `status=auto`.

## Setup

The backfill agent authenticates with a **non-expiring service token**, not a JWT. It's
scoped to the translation list + bulk-write endpoints only — it does **not** unlock other
admin routes.

1. **Generate** the token: `openssl rand -hex 32`.
2. **Backend:** set it as `TRANSLATION_WRITE_TOKEN` (env / GSM secret) on the API. Unset =
   the token path is disabled (admin-JWT-only).
3. **Agent:** set the same value as `TINBOKER_WRITE_TOKEN` in the MCP env. When present,
   the privileged tools are registered and sent as `Authorization: Bearer <token>`.

The admin UI continues to use Google-OAuth JWTs (the endpoints accept either). Rotate the
token by regenerating and updating both sides.

```jsonc
// .mcp.json — read-write deployment for the backfill agent
{
  "mcpServers": {
    "stock_translations": {
      "command": "uvx",
      "args": ["--from", "/abs/path/to/mcp-servers/stock-translations", "tinboker-stock-translations-mcp"],
      "env": {
        "TINBOKER_API_BASE_URL": "https://dev-api.tinboker.com",
        "TINBOKER_WRITE_TOKEN": "<same value as backend TRANSLATION_WRITE_TOKEN>"
      }
    }
  }
}
```

## Agent prompt (paste as the task)

> You maintain the TinBoker stock-translation table via the `stock_translations` MCP.
>
> 1. Call `list_pending_translations` to get the queue of unresolved tickers.
> 2. For each ticker, FIRST call `search_stocks` on the symbol and the likely company
>    name to check for an existing variant (e.g. `2330` vs `TSM`) — if a good match
>    already exists, skip it (don't duplicate).
> 3. For the rest, determine:
>    - `name_en`: the official company name, cleaned (no "Inc.", "Corp.", "Ltd.").
>    - `name_zh_tw`: the common Traditional-Chinese name used in Taiwan, **or `null`**
>      if the company is universally referred to by its English/Latin name (e.g.
>      Palantir, Arm, Roku). Never copy the English name into this field.
>    - `brand_color`: the company's primary brand hex color (e.g. NVIDIA `#76B900`).
> 4. Submit a batch with `propose_translations` (status defaults to `auto`).
> 5. Report what you wrote and which you skipped, and flag any low-confidence guesses
>    so a human can review them in the admin portal.
>
> Be conservative: a `null` zh-TW name is better than a wrong transliteration.

## Review

Agent output lands as `status=auto` and renders on cards immediately. A human verifies
in `/admin/translations` (filter `status=auto`) and promotes good rows to `approved`;
the startup reconciler and future backfills never overwrite `approved` rows.
