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

## Tools used (require `TINBOKER_ADMIN_TOKEN`)

- `list_pending_translations(limit, market?)` — the work queue (status=pending stubs).
- `search_stocks(query, market?)` — dedupe / find an existing variant before researching.
- `propose_translations(items)` — write results back as `status=auto`.

## Setup

`TINBOKER_ADMIN_TOKEN` must be a **valid, unexpired bearer JWT for a Google account in
`ADMIN_EMAILS`** (admin access = OAuth JWT + allowlist; there is no static admin token).

- **Dev/staging:** mint one via the dev-bypass flow
  (`POST /api/auth/dev-token` with `DEV_BYPASS_TOKEN`) for an admin-allowlisted account.
- **Production:** copy a fresh JWT from an authenticated admin session.

JWTs expire — for a scheduled/long-running pipeline, refresh the token each run. (If
this becomes painful, the documented upgrade is a dedicated, bounded
`TRANSLATION_WRITE_TOKEN` auth path on the bulk-json endpoint — not built yet.)

```jsonc
// .mcp.json — read-write deployment for the backfill agent
{
  "mcpServers": {
    "stock_translations": {
      "command": "uvx",
      "args": ["--from", "/abs/path/to/mcp-servers/stock-translations", "tinboker-stock-translations-mcp"],
      "env": {
        "TINBOKER_API_BASE_URL": "https://dev-api.tinboker.com",
        "TINBOKER_ADMIN_TOKEN": "<admin-jwt>"
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
