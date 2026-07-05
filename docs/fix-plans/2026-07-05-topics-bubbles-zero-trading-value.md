# Price-data access — /topics bubble fix + market-data architecture

> Part 1: the /topics bubble outage (root cause CONFIRMED on VPS 2026-07-05, read-only
> probes; no fixes applied). Part 2: the price-data architecture decision it exposed —
> FinMind vs yfinance vs official sources, and the fetcher→Postgres→self-hosted-API
> design. §2.5 records Willy's decisions (2026-07-05). Implementer: follow
> `docs/ai-ops/` rules — verify with the acceptance checks, never self-verify.
> file:line refs verified on `develop` @ `6263428`.

---

# Part 1 — /topics 泡泡圖空白（trading_value 全零）

## Symptom

https://dev.tinboker.com/topics shows「尚無題材熱度資料」.

**Verified:** `GET /api/sectors/performance` (dev) returns 139 exposures with healthy
`heat`/`return_pct`/`members`, but `trading_value_windows_twd` all-zero for ALL 139,
`market_cap_twd` all null, institutional windows all zero — the entire FinMind leg is
dead. Frontend `SectorPerformance.tsx:159-162` drops every bubble with radius ≤ 0 →
empty state (`TopicsCloud.tsx:296-305` fallback also forces `r=0` when perf is empty).
Prod/staging 404 on this endpoint (dev-only feature) — no known-good env exists.

## Root cause — three confirmed links

**(1) The recompute self-exhausts the FinMind hourly budget.**
`exposures_performance()` (`backend/src/services/podcast.py:1533`) fans out per-ticker
FinMind calls for trading value + institutional net (+1 bulk market-cap call)
(`finmind_service.py:668/:776/:598`). Live board = **580 unique member tickers** →
~1,160 per-ticker calls + retries vs a 1,500/hr local cap. VPS evidence: budget counter
`finmind:budget:finmind:2026070512` = 1529; dev logs "budget exhausted (4073/1500)".
The budget key is global (no env prefix, `finmind_budget.py`) on the shared
`tinboker-redis`; cross-env contention is secondary — one recompute alone blows the cap.
(Our Backer-tier upstream cap is **1600/hr** — dashboard-confirmed 2026-07-05 — so the
local 1500 is a sane 100-call headroom setting; the ~1,740-call storm exceeds both.)

**(2) The Yahoo fallback is structurally dead: `yfinance` is not installed.**
Budget-exhausted calls return `None` cleanly and fall to `list_yahoo_tw_daily_range`
(`finmind_service.py:48`), which does `try: import yfinance / except ImportError:
return []` — and `docker exec tinboker-backend-dev python -c "import yfinance"` →
**ModuleNotFoundError** (confirmed live). Every fallback silently returns `[]`.
Separately, a raised `FinMindAPIError` is swallowed at debug level at `:686-688`
*before* the fallback — a second silent path (not the live one today).

**(3) Empty results are truthy and get cached for a day.**
On total failure the fetchers return `{"1":{},"7":{},"30":{},"90":{}}` — truthy — so
`if vals:` passes in `_tw_trading_value_windows_cached` (`podcast.py:1628-1650`) and
siblings (`:1511`, `:1652`): cached in a per-process memory cache AND Redis for
`CACHE_TTL["stock_ohlcv"]` = 1 day (`cache_config.py:20`). (Forensic note: at probe time
Redis had NO `*trading_value*` keys under any prefix and 0 "Cache set error" logs — the
fast all-zero responses came from budget-exhausted fast-fail and/or the memory cache;
F3 guards both.)

**Ruled out (verified):** missing `FINMIND_API_KEY` (GSM bootstrap, 0 "not configured"
logs in 48h); ticker format mismatch (bare `"3491"` codes both sides,
`finmind_service.py:714` / `podcast.py:1571`); empty members; frontend color map;
window-key str/int mismatch.

**Cap note:** live local cap 1500 vs `config.py:42` default 280; upstream Backer cap is
1600/hr (dashboard, 2026-07-05) — so 1500 is deliberate headroom, not a bug. Remaining
task (M5): find where 1500 is injected (`finmind_budget.py:39` prefers
`FINMIND_HOURLY_CAP` but container env shows it unset — likely `secrets_bootstrap`/GSM)
and document it there.

**Not the cause:** PR #418 (regen/backfill sector verifier — still OPEN) concerns
episode `sector_exposures` quality; bubbles render from board + market data.

## The fix (ordered; F2 superseded by the Part 2 architecture — read both)

- **F1 — install `yfinance` in the backend image** (requirements + rebuild). Restores
  the designed fallback as a *short-term crutch only* — Part 2 research downgrades
  yfinance to emergency-backfill status (no unique TW data, real 429/ToS risk).
- **F2 — kill the per-request call storm.** Superseded by Part 2 §3: daily TWSE/TPEx
  whole-market fetch (2 calls/day) into Postgres; `/topics` computed from the DB. See
  migration steps M1–M3.
- **F3 — never cache empty results:** guard all three cached wrappers
  (`podcast.py:1628`, `:1511`, `:1652`) with a real-content check
  (`any(v for v in vals.values())`) for BOTH the memory cache and `cache_set`; or cache
  empties ≤10 min. This alone turns any future outage from 24h into minutes.
- **F4 — un-silence failures:** catch `FinMindAPIError` inside the `fetch_ticker`
  closures so the fallback still runs on raise, and replace per-ticker `logger.debug`
  (`finmind_service.py:686-688`) with one `logger.warning` summary per batch.
- **F5 — ops:** no Redis purge needed (no poisoned keys found; memory cache dies on
  deploy restart). Verify recovery in a FRESH UTC hour (counter resets hourly).
- **F6 — optional frontend degrade (product call):** if perf data exists but all radii
  ≤ 0, size bubbles by `heat` with a min radius instead of the empty state.

## Acceptance criteria (fresh verifier, per docs/ai-ops rubric R2)

1. `docker exec tinboker-backend-dev python -c "import yfinance"` → no error (F1).
2. Fresh UTC hour: `curl -s https://dev-api.tinboker.com/api/sectors/performance | jq
   '[.exposures[] | select(((.trading_value_windows_twd // {}) | [to_entries[].value] |
   add // 0) <= 0)] | length'` → from **139** to ≲ 10; `market_cap_twd` non-null for most.
3. Budget counter after one recompute stays under cap (post-M2: recompute adds ~0).
4. https://dev.tinboker.com/topics renders bubble nodes (>0).
5. Unit checks: (a) fetcher falls back when `_make_request` raises; (b) all-empty
   results are NOT cached at the 1-day TTL.

---

# Part 2 — 價格資料存取架構（FinMind / yfinance / 官方源）

Research + codebase audit 2026-07-05. Question: every stock page needs a price chart,
episode pages need mentioned-ticker prices, /topics needs sector money-flow — all
hitting FinMind per-request is quota-inefficient. Build a dedicated fetcher→Postgres→
self-hosted price API? And what does FinMind uniquely provide vs yfinance?

## 2.0 Current consumption (codebase audit, VERIFIED)

| Feature | Endpoint → source | FinMind dataset | Mitigation today |
|---|---|---|---|
| Stock page chart | `/api/stocks/{t}/history` (`stock.py:627`) → `data_collection_service.py:31` | `TaiwanStockPrice` (daily), `TaiwanStockKBar` (1H — **Sponsor-only dataset, we are Backer**: likely already failing silently; verify, see §2.5 D2) | Redis 1h (`stock:{t}:info:*:v3`) |
| Stock page metadata / P/E | `data_collection_service.py:87,131` | `TaiwanStockInfo`, `TaiwanStockPER` | Redis 1h |
| Live snapshot | `data_collection_service.py:105` | `taiwan_stock_tick_snapshot` | Redis 30min |
| Episode mentioned tickers | `POST /api/stocks/batch-prices-since` (`stock.py:210`) | `TaiwanStockPrice` only on double-miss | **Postgres-first** (`stock_daily_closes`) + Redis 1d + 5-min negative cache — already the right pattern |
| /topics bubbles | `podcast.py:1646/1670/1527` | `TaiwanStockPrice` ×580, `TaiwanStockInstitutionalInvestorsBuySell` ×580, `TaiwanStockMarketValue` ×1 | 1-day cache, but one miss = ~1,160 calls (Part 1) |
| Daily close warmer | `stock_close_refresh.py` (`main.py:190`) | `TaiwanStockPrice` ≤400/run, 4 runs/day, skip-if-recent | writes `stock_daily_closes` |
| US leg + WebSocket live | Massive (`massive_service.py`, `stock_publisher.py`) | — | separate quota |

**Dead code:** `get_tw_trading_values` (`finmind_service.py:625`) and
`get_tw_latest_closes` (`:723`) have zero callers — delete.
**Orphaned infra:** Postgres table `stock_daily_ohlc` (`database/models.py:204`) has
**no writer and no reader** (docstring says "filled by the warmer from yfinance" — never
scheduled). The fetcher below is its intended purpose; schema is free to change.

## 2.1 Source comparison (research 2026-07-05; TWSE/TPEx verified by direct fetch)

| Source | Uniquely good for | Cost / limits | Risk / caveats |
|---|---|---|---|
| **TWSE OpenAPI** ([openapi.twse.com.tw](https://openapi.twse.com.tw), 143 endpoints, swagger verified) | `STOCK_DAY_ALL`: whole listed market's daily OHLC+volume+成交金額 in ONE free call; `BWIBBU_ALL` (all-market P/E·P/B·殖利率) | Free, no key; rate limit unpublished | Gov Open Data License v1, commercial OK ([data.gov.tw/dataset/11549](https://data.gov.tw/dataset/11549)). **No per-stock 三大法人 in OpenAPI** (only market-level BFI/QFII aggregates; legacy www.twse.com.tw/T86 is NOT covered by the open-data exemption) |
| **TPEx OpenAPI** — **VERIFIED 2026-07-05** (swagger 200, **225 endpoints**; requires a browser User-Agent header, plain curl gets 403) | `/tpex_mainboard_daily_close_quotes` (all-OTC daily OHLC+成交量+成交金額, one call — live-tested); also official `/tpex_3insti_daily_trading` (**per-stock 三大法人 for OTC!**), `/tpex_daily_market_value` | Free, no key | Dates in **ROC format** (`1150703` = 2026-07-03) — convert. Send browser UA |
| **FinMind** — tiers **Free / Backer / Sponsor** (+Sponsor Pro parquet bulk), per [llms-full.txt](https://finmind.github.io/llms-full.txt) | 台股獨有資料（§2.2）; Backer unlocks bulk "all stocks by date" mode for most datasets | 300/hr no token, 600/hr registered (VERIFIED); **our Backer account: 1600/hr** (dashboard-confirmed 2026-07-05) | Official Terms of Use have **no non-commercial clause** (liability disclaimer only); stricter wording exists only in the informal README — see §2.5 D1 |
| **yfinance** | Nothing unique for TW | Free, unofficial | High: recurring 429 waves through 2025 (issues #2125/#2411/#2422/#2480/#2614); ToS risk; zero TW-institutional data. Backfill/emergency only |
| mis.twse.com.tw | Realtime intraday quotes | Free, undocumented | Unofficial, ban risk — do not use in prod |
| Fugle / Shioaji | Broker-grade TW realtime (REST/WS) | Free tier with brokerage account (KYC) | The sanctioned path for §2.5 D5 realtime — needs evaluation task |

## 2.2 FinMind 究竟有什麼不可替代的資料？(tier labels from llms-full.txt, verified)

**Free tier, per-ticker (no free substitute for LISTED stocks):**
三大法人買賣超 (`TaiwanStockInstitutionalInvestorsBuySell`; OTC 上櫃 has an official
TPEx alternative, see §2.1) · 融資融券 · 月營收 · 財報三表 · 股利 · 外資持股 · 借券 ·
還原股價 (`TaiwanStockPriceAdj`).

**Backer tier (us):** bulk "all stocks by date" mode (`不帶 data_id`) for most datasets —
e.g. 三大法人 all-market in ~1 call/day · `TaiwanStockPriceTick` · 股權分散
(`TaiwanStockHoldingSharesPer`). Note: commit `317233f` found a bulk request
rate-limited/empty — that predates understanding of the local budget; retest bulk mode
in a fresh budget window during M3.

**Sponsor-only (we do NOT have):** `TaiwanStockKBar` (分K — **currently called by our 1H
chart path**, `data_collection_service.py:273`; probably failing silently) · 分點
(`TaiwanStockTradingDailyReport`) · tick realtime snapshot bulk · Sponsor Pro parquet.

**NOT worth FinMind quota:** plain daily OHLCV/成交金額 and all-market P/E — TWSE/TPEx
OpenAPI do it in 1–2 free calls.

## 2.3 Recommended architecture（fetcher 提案具體化；Willy 已拍板 fetcher 放 backend）

**Principle: the request path never calls an external market API. Scheduled fetchers
land external data in Postgres; the backend serves only from Postgres+Redis.**

Daily fetcher = backend background task alongside `stock_close_refresh` (§2.5 D4):

1. **~15:00 Taipei daily:** TWSE `STOCK_DAY_ALL` + TPEx `tpex_mainboard_daily_close_quotes`
   (2 calls, browser UA, ROC-date conversion) → upsert whole market into
   `stock_daily_ohlc` (repurpose orphan table; add `volume`, `trading_value`, `source`).
2. **三大法人 daily:** try FinMind **bulk mode** (Backer-entitled, ~1 call/day) into a new
   `stock_institutional_daily` table; fallback to per-ticker spread (~580/day) if bulk
   proves unreliable; OTC leg can use TPEx `/tpex_3insti_daily_trading` (official).
3. **Market caps:** keep the 1/day bulk `TaiwanStockMarketValue` call
   (`finmind_service.py:598`) or TPEx `/tpex_daily_market_value` + TWSE equivalent.
4. **Request path repointing:** `/topics` windows (trading value, institutional, market
   cap) computed from Postgres; stock-chart daily granularity reads `stock_daily_ohlc`
   first; `batch-prices-since` already Postgres-first (keep).
5. **Stays external on-demand (low volume, cached):** live snapshot
   (`taiwan_stock_tick_snapshot` — confirm Backer covers it), `TaiwanStockInfo`/
   `TaiwanStockPER` metadata. **1H intraday (`TaiwanStockKBar`) is Sponsor-only — decide:
   drop 1H granularity, upgrade tier, or defer to the D5 realtime evaluation.**
6. **Historical backfill (one-off):** 90d OHLCV via FinMind per-ticker spread over hours,
   or TWSE/TPEx per-month endpoints.

**Consolidation note:** `stock_daily_closes` (close-only) becomes redundant once
`stock_daily_ohlc` is populated — migrate readers (`stock.py:88,139,196,411`,
`podcast.py:67`) then drop, in a later pass, NOT in the same PR as M1.

## 2.4 Migration order (each step independently shippable)

- **M0** = Part 1 F1+F3+F4 (stop the bleeding).
- **M1**: TWSE/TPEx daily fetcher → `stock_daily_ohlc` + 90d backfill.
- **M2**: `/topics` trading-value windows + market cap from Postgres → storm gone.
- **M3**: institutional ingest (bulk-mode first, §2.3-2) → `/topics` money-flow from DB.
- **M4**: stock-chart daily granularity Postgres-first; shrink `stock_close_refresh`;
  delete dead `get_tw_trading_values`/`get_tw_latest_closes`; resolve the KBar/1H
  question (§2.3-5).
- **M5**: cap is already sane (local 1500 vs upstream 1600) — just find where 1500 is
  injected (env unset in containers — check `secrets_bootstrap`/GSM) and add a comment
  linking it to the 1600 upstream figure; decide yfinance fallback's fate.

## 2.5 Decisions (Willy, 2026-07-05) & remaining opens

- **D1 商用授權 — risk downgraded 2026-07-05, written confirmation still recommended.**
  The **official Terms of Use** ([finmind.github.io/PrivacyPolicy](https://finmind.github.io/PrivacyPolicy/),
  self-described as the binding agreement) contain **NO non-commercial clause** — the
  operative sentence is a liability disclaimer:「本公司提供之所有內容均供教育與參考用途。
  使用者依本資料交易所生之交易損失需自行負責…」, plus「軟體授權條款請參閱 LICENSE」
  (Apache-2.0). The stricter「教育、非商業用途」wording exists ONLY in the GitHub README
  (informal). Assessment: displaying data in our own product without reselling raw data
  is not prohibited by the binding terms; residual ambiguity is the purpose-framing
  ("教育與參考") and the README discrepancy. For belt-and-suspenders, email
  **finmind.tw@gmail.com** (address confirmed in the terms page):
  > 您好，我們是 FinMind 的 Backer 贊助者（帳號 hwchan42），經營台股 podcast 資訊平台
  > （tinboker.com），將 API 的行情與法人資料呈現在自家網頁（不轉售、不重新散布原始
  > 資料）。想確認此類使用符合貴服務使用條款。感謝！
- **D2 帳號層級 = Backer, 上限 1600/hr**（dashboard-confirmed 2026-07-05; usage at
  check time: 90/1600). Consequences: (a) `TaiwanStockKBar` (1H chart) is Sponsor-only →
  verify whether `/api/stocks/{t}/history` 1H granularity currently returns data at all;
  (b) bulk all-stocks-by-date mode IS available to us; (c) local cap 1500 = sane 100-call
  headroom under 1600 — keep, just document (M5).
- **D3 TPEx — RESOLVED.** Verified live 2026-07-05: 225 endpoints, whole-OTC daily
  quotes + official per-stock 三大法人. Caveats: browser UA required, ROC dates.
- **D4 Fetcher location = backend background task.** (Willy)
- **D5 台股盤中即時 = wanted (future).** Path: evaluate Fugle vs Shioaji (brokerage
  account + KYC required for both); do NOT use mis.twse. Suggest a separate research/
  design task when prioritized; may also resolve the 1H-chart question (D2a) better
  than a Sponsor upgrade.
