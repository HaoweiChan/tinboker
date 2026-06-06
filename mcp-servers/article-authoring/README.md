# TinBoker Article Authoring MCP

Local stdio MCP server for drafting TinBoker articles through the public HTTP API.

## Tools

- `search_tickers`, `cite_ticker`
- `suggest_tags`, `add_tag`
- `image_markdown`
- `insert_chart`, `insert_graph`
- `create_draft`, `update_draft`, `list_my_drafts`, `get_article`, `publish`

Write tools require `TINBOKER_ARTICLE_TOKEN`. The server never receives database,
GCS, or VPS credentials.

## Environment

```bash
TINBOKER_API_BASE_URL=https://dev-api.tinboker.com
TINBOKER_WEB_BASE_URL=https://dev.tinboker.com
TINBOKER_ARTICLE_TOKEN=...
```

Optional backend byline settings for service-token drafts:

```bash
TINBOKER_ARTICLE_AUTHOR_ID=...
TINBOKER_ARTICLE_AUTHOR_NAME=...
TINBOKER_ARTICLE_AUTHOR_AVATAR=...
```

## Run

```bash
uvx --from . tinboker-article-authoring-mcp
```
