# Editorial Template — Public Teaser vs Paid Full Edition

_Issue #425. Related: #407 (newsletter web edition), #423 (subscription CTA blocks), #424 (Substack funnel)._

TinBoker runs a **hybrid content model**:

- **Public web edition** on `tinboker.com` — a free teaser/excerpt that stands on its own but stops short of the actionable, maintained layer.
- **Paid full edition** on Substack — the complete analysis, plus the parts a reader would actually trade or track against.

This doc is the convention for structuring an article so the free page has a clear conversion story instead of reading like a generic blog post. **No new CMS is required** — everything below is authored in the existing `/admin/articles` editor.

---

## The content contract

Three optional fields carry the free-vs-paid split. Leave them blank and the article renders as a plain public post — nothing changes.

| Field | Where to set it | Purpose |
|-------|-----------------|---------|
| `premium_pitch` | 完整版（付費）設定 → 一句話賣點 | One sentence promising what the paid edition adds. Renders as the lead line of the **完整版收錄** module. |
| `premium_includes` | 完整版（付費）設定 → 收錄項目（每行一個） | Bullet list of concrete deliverables the subscriber gets. Renders as a checklist. |
| `subscribe_url` | 完整版（付費）設定 → 訂閱連結 | Per-article paid destination. Blank → falls back to the site-wide `VITE_SUBSTACK_URL`. |

These drive three UI surfaces on `/article/:slug`:

1. **完整版收錄 (`PremiumEditionCard`)** — states what the subscriber gets (acceptance criterion #2).
2. **接下來 (`NextBestActions`)** — related articles + related tickers/topics + subscribe CTA (acceptance criterion #3).
3. **含完整版 badge** on `/articles` cards when `premium_pitch` is set.

---

## Writing the public teaser

Aim for a piece that is **genuinely useful but deliberately open-ended**. The reader should finish it understanding the thesis, but wanting the watchlist / levels / follow-through.

Recommended shape:

1. **Hook + thesis** — the claim, stated plainly, in the first two paragraphs.
2. **The reasoning** — the framework and evidence. This is the real value of the free edition; do not gut it.
3. **What this implies** — point at the actionable layer without handing it over ("this sets up a specific entry zone and an invalidation level — both in the full edition").
4. Tag mentioned stocks with `[公司名稱](#ticker:SYMBOL)` and topics with `[主題名稱](#tag:topic-slug)` so the **接下來** module and stock cross-links populate automatically.

Do **not** paywall or truncate the body. The kill criterion on #425 is explicit: this is editorial structure + funnel clarity, **not** gated-content infrastructure.

---

## Writing the paid promise

Keep `premium_pitch` to one sentence. Make `premium_includes` concrete and repeatable across articles so subscribers learn what "full edition" reliably means. Good building blocks:

- **觀察名單** — watchlist with entry/exit zones
- **風險地圖** — risk map: what breaks the thesis
- **失效條件** — invalidation level(s)
- **後續追蹤更新** — follow-up updates as the situation develops

Example:

```
premium_pitch:  完整版把這篇的觀點變成可執行的部位：進出場區間、失效價位，以及事件後的追蹤更新。
premium_includes:
  觀察名單與建議進出場區間
  風險地圖：什麼情況會讓這個論點失效
  關鍵價位與失效條件
  事件後續追蹤更新（訂閱者專屬）
```

---

## Publishing checklist (manual, for Willy)

- [ ] Body reads as a complete, useful teaser — thesis + reasoning intact.
- [ ] Mentioned tickers/tags marked up inline so cross-links populate.
- [ ] `premium_pitch` set (one sentence).
- [ ] `premium_includes` — 3–5 concrete deliverables.
- [ ] `subscribe_url` set only if this article points to a specific paid series; otherwise leave blank.
- [ ] Preview the 完整版收錄 card at the bottom of the editor preview before publishing.
