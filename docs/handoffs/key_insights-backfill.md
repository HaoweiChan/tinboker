# Handoff prompt — populate `key_insights` on every episode (tinboker-agents)

> Paste everything below the line into the LLM/agent working in the **tinboker-agents**
> repo. It is self-contained. Origin: tinboker-platform, 2026-06-05.

---

## Task

Populate the `key_insights` field on **every** `episodes/{episode_id}` document in
Firestore — for all existing episodes (backfill) and going forward in the ingest
pipeline. The field is defined in the cross-repo data contract but is currently
**~0% populated** (0 of 40 recent episodes have it), which leaves the platform UI
degraded. Your job is to generate high-quality key insights and write them to the
field, safely.

## Why this matters (platform context — do not change platform code)

The TinBoker platform reads `episodes/{episode_id}.key_insights` in two places:

1. **Episode detail page** (`關鍵洞察` card) — rendered as the highlight bullets.
2. **Every episode card** across browsing pages (home feed, podcaster, tag, stock,
   watchlist, profile). These list views deliberately do **not** hydrate the full
   `summary_content` from GCS (perf — transcripts are large), so `key_insights` is
   the **only** insight source the cards have. When it's empty, cards fall back to a
   plain teaser (or show nothing). This is why populating it matters across the app,
   not just on the detail page.

The platform half is already shipped and ready; it will light up automatically the
moment these documents carry `key_insights`. **You only do the Firestore write side.**

## Field spec (the contract)

| Property | Value |
|---|---|
| Path | `episodes/{episode_id}.key_insights` |
| Type | `string[]` (JSON array of strings) |
| Count | **3–8** items |
| Order | **Most important first** — cards display only the first 3 |
| Language | **Traditional Chinese (zh-TW)**, matching the episode content |
| Format | **Plain text only** (see hard rules below) |
| Ownership | **agents-owned** — safe for you to write |

### Hard formatting rules (the platform renders these strings verbatim)

Each string MUST be plain text. Do **NOT** include any of:

- Markdown headers (`#`, `##`), list markers (`-`, `*`, `1.`), emphasis (`**`, `_`, `` ` ``), blockquotes (`>`).
- Inline link markers used elsewhere in summaries: `[label](#ticker:SYMBOL)`,
  `[label](#tag:ID)`, `[label](url)` — write the plain label only (e.g. `台積電`, not `[台積電](#ticker:2330)`).
- Timestamp markers: `(#time:123456)`.
- Leading/trailing whitespace, surrounding quotes, or a trailing bullet glyph.

A good item is a single self-contained takeaway, roughly **15–40 characters**, one line.

## What makes a good key insight

These are the **substantive conclusions / theses / takeaways** of the episode — what a
listener should remember — not a table of contents.

- ✅ Specific claims, theses, recommendations, risks, or numbers actually discussed.
- ✅ Each item stands alone and is distinct from the others (no redundancy).
- ✅ Lead with the most important point; the first 3 carry the card.
- ✅ Domain is Taiwanese/US markets & investing — be concrete (tickers as plain names,
  sectors, events like 法說會 / 降息 / 財報).
- ❌ Not generic section titles ("市場分析", "投資策略"), filler, or clickbait.
- ❌ Not a paraphrase of the episode title.

### Example (for an episode about 2026 TW market outlook)

```json
"key_insights": [
  "國安基金退場，台股回歸市場自主動能",
  "主動式ETF（如00994A）成為資產配置新選擇",
  "外資資金輪動轉向傳產與金屬概念股",
  "聯準會降息時點與台積電法說會是關鍵變數",
  "市場急漲後勿追高，拉回為分批佈局良機"
]
```

## How to generate

Derive the insights from the material the pipeline already has for each episode —
the generated `summary_content` (markdown) is the best source; the transcript is the
fallback. Reuse whatever summarization/LLM step the pipeline already runs; this is one
additional structured output alongside `summary_content`, not a new model.

If your pipeline already emits a structured summary object, add `key_insights` to it.

## Backfill (existing episodes)

Iterate over the full `episodes` collection and set `key_insights` wherever it is
missing or empty. Process in batches; this is a one-time job over the whole collection.
Skip episodes that have no usable `summary_content`/transcript and log them.

## Firestore write safety (critical)

- Write with **`merge=True`** (Firestore `set(..., merge=True)` or an `update`) so you
  only touch `key_insights`.
- **Never** write these platform-owned fields — they belong to TinBoker's editor flow
  and must be preserved across any agents write: `modified_summary_url`,
  `modified_summary_content`, `modified_by`, `modified_at`.
- **Never** mutate `created_time` — it is immutable; the platform's notification
  fan-out uses it to detect new episodes, and changing it **re-fires notifications**.
- Idempotent: re-running must not duplicate or corrupt data.

## Acceptance criteria

1. `GET https://api.tinboker.com/api/episodes/recent?limit=40&include_content=true`
   returns non-empty `key_insights` (3–8 plain-text items) for ~all episodes.
2. No item contains markdown, `#ticker:` / `#tag:` / `#time:` markers, or surrounding quotes.
3. `modified_*` fields and `created_time` are unchanged on every touched doc.
4. Spot-check 5 episodes in the UI: the home-feed cards show the insight bullets, and
   the detail-page `關鍵洞察` card shows the same bullets.

## References

- Data contract: `docs/firestore-contract.md` (§2, the `key_insights` row — updated to
  mark this field required and consumed by all card views).
- Cross-repo change process: `docs/workflows/firestore-data-change.md`.
