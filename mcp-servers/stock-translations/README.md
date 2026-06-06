# stock-translations MCP server

Read-only MCP server that exposes TinBoker's stock translation table (English name,
Traditional Chinese `zh-TW` name, brand color) to agents — the tinboker-agents summary
writer, or Claude Code.

It is a thin wrapper over the platform's public HTTP API
(`/api/stocks/translations/search` and `/batch`). It holds **no database credentials**;
the platform backend remains the single source of truth.

## Tools

**Read-only (always available):**

| Tool | Use it when… |
|------|--------------|
| `search_stocks(query, market?, limit?)` | You have a company **name** or partial ticker ("Nvidia", "輝達", "台積電") and need the canonical symbol + names + color. |
| `get_stock(ticker, market?)` | You know the exact **symbol** and want one row. |
| `get_stocks_batch(tickers, market?)` | You have a symbol-only list (e.g. an episode's `related_tickers`) to localize in one call. |

**Privileged (registered only when `TINBOKER_WRITE_TOKEN` is set):**

| Tool | Use it when… |
|------|--------------|
| `list_pending_translations(limit?, market?)` | Pull the backfill work queue — tickers discovered in episodes with no names yet. |
| `propose_translations(items)` | Write resolved translations back (status defaults to `auto`). |

The privileged tools power the **translation backfill agent** — see
[BACKFILL_AGENT.md](./BACKFILL_AGENT.md). Deploy the server **without** the token for
the read-only summary-writer / frontend; **with** the token for the backfill agent.

Every result row carries:

- `ticker`, `market`, `name_en`, `name_zh_tw`, `brand_color`, `translation_status`
- **`has_zh_name`** — `true` only when `name_zh_tw` is a real Chinese (CJK) name, never
  when it's an English value parked in the zh column.
- **`display_name`** — the label to render: `name_zh_tw` when `has_zh_name`, else the
  English name (or ticker). **zh-TW is intentionally optional** — English-preferred US
  stocks (Palantir, Arm, …) return `has_zh_name=false`; render `display_name` as-is.

## Configuration

| Env var | Default | Notes |
|---------|---------|-------|
| `TINBOKER_API_BASE_URL` | `https://api.tinboker.com` | Use `https://dev-api.tinboker.com` against dev. |
| `TINBOKER_API_TIMEOUT` | `10` | Per-request timeout (seconds). |
| `TINBOKER_WRITE_TOKEN` | _(unset)_ | Service token; the backend API reads the same `TINBOKER_WRITE_TOKEN`. When set, registers the privileged backfill tools. See [BACKFILL_AGENT.md](./BACKFILL_AGENT.md). |

## Running

```bash
# From this directory, via uv (no install step):
uvx --from . tinboker-stock-translations-mcp

# Or install then run:
pip install -e .
tinboker-stock-translations-mcp
```

The server speaks MCP over **stdio**.

## Register with Claude Code

```bash
claude mcp add stock-translations -- uvx --from /abs/path/to/mcp-servers/stock-translations tinboker-stock-translations-mcp
```

or in `.mcp.json`:

```json
{
  "mcpServers": {
    "stock-translations": {
      "command": "uvx",
      "args": ["--from", "/abs/path/to/mcp-servers/stock-translations", "tinboker-stock-translations-mcp"],
      "env": { "TINBOKER_API_BASE_URL": "https://dev-api.tinboker.com" }
    }
  }
}
```

## Register with the tinboker-agents pipeline

Point the pipeline's MCP client at the same command. While writing a summary the agent
should: resolve each mentioned company with `search_stocks`/`get_stock`, then emit a
stable **ticker marker** in the markdown (the agreed `[display](#ticker:SYMBOL)` form,
mirroring the existing `#tag:` convention) rather than baking the localized name into the
prose. The platform renders the current `display_name` + brand chip at read time, so a
later name fix in the table propagates to every existing summary. See
`docs/firestore-contract.md` for the marker contract.
