---
name: article-authoring
description: Use when the user wants to write, draft, edit, or publish a TinBoker article. Guides the full workflow — topic → body → ticker citations → tags → create draft → preview → publish — using the article-authoring MCP tools.
---

You are helping the user write and publish a TinBoker article end-to-end.
Read `docs/articles-platform-plan.md` for the full platform spec before starting.

## Workflow

### 1. Clarify scope (if not already clear)
Ask for: topic/angle, target tickers to cite, rough length, whether to publish immediately or save as draft.

### 2. Research tickers
For every company you plan to mention, call `search_tickers` or `cite_ticker` to resolve the canonical symbol and get the display name. Never hardcode a ticker marker without confirming it resolves correctly.

### 3. Draft the body
Write in **Markdown**. Follow these rules:

- **Ticker citations:** use `cite_ticker(query)` — it returns the ready-to-paste `[display](#ticker:SYMBOL)` marker. Never write a raw `#ticker:` marker by hand.
- **Tag citations:** use `add_tag(name)` — it returns `[name](#tag:slug)`. Call `suggest_tags(text)` on a section of the body first to surface existing tags you should reuse.
- **Images:** use `image_markdown(source_url, alt, title?)` for any external image URLs. Do not embed raw HTML `<img>` tags.
- **Charts/graphs:** `insert_chart` / `insert_graph` return Phase-3 directive placeholders — include them if relevant but note they are not yet rendered in the frontend.
- **Language:** article body should be in zh-TW unless the user explicitly requests otherwise.
- **No emoji, no raw HTML.**

### 4. Compose metadata
- `title` — clear, zh-TW
- `subtitle` — optional one-liner deck
- `key_points` — 3–5 plain-text bullet takeaways (think `episodes.key_insights`)
- `tags` — list of tag slugs (from step 3 `add_tag` calls, or `suggest_tags` results)
- `tickers` — list of symbols (the backend also extracts these from body markers, but pass them explicitly for completeness)
- `cover_image_url` — optional; must be a public URL

### 5. Create the draft
Call `create_draft(title, body_markdown, ...)`. It returns an `article_id` and an admin preview URL — share the preview URL with the user.

### 6. Iterate
If the user wants changes, call `update_draft(article_id, ...)` with only the fields that changed. Call `get_article(article_id=...)` to read back the current state if needed.

### 7. Publish
Only call `publish(article_id)` when the user explicitly confirms they are ready. This flips `status → published` and makes the article live at `/article/{slug}` on the frontend. After publishing, remind the user to manually purge the CF edge cache if the article list is stale:
```bash
# See CLAUDE.md "Post-deploy: Cloudflare CDN cache" for full purge instructions
# Articles are under the same CDN hosts as the rest of the frontend
```

## Constraints
- Write tools require `TINBOKER_ARTICLE_TOKEN` to be set in the MCP server env. If a write call fails with auth error, tell the user to set the token.
- Image upload is **not yet available** (Phase 0 CDN wiring pending). External image URLs work via `image_markdown`; hosted uploads are deferred.
- Stock chart (`:::chart`) and graph (`:::graph`) embeds are **Phase 3** — they emit valid directive syntax but are not yet rendered by the frontend.
- Never add new Firestore-direct reads. Articles live in Postgres/SQLite only.
- Do not reuse `tinboker_write_token` or the dev-bypass token for article auth — the article token (`TINBOKER_ARTICLE_TOKEN`) is scoped separately.
