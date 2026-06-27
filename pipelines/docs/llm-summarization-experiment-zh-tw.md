# LLM Podcast 摘要模型評估與實驗報告

## 1. 執行摘要 (Executive Summary)
本報告記錄了針對 Podcast 數據 Pipeline 的 Ingestion 與摘要階段進行的大語言模型（LLM）評估與調查。此實驗是因為生產環境中出現了大量的摘要生成失敗、導致系統回退至「預留占位（Placeholder）」報告的異常狀況而啟動。

調查發現，先前預設的模型配置（`openrouter:xiaomi/mimo-v2.5`）是一門推理模型，在處理超長節目時，其隱藏的思考過程（Reasoning chains）耗盡了 `max_tokens`（4096）的輸出額度，導致 JSON 格式截斷。經模型選型測試，`deepseek-v4-pro` 在摘要緊湊度、標籤詞彙表符合度以及個股標的（Ticker）連結精準度上，均顯著優於對照組的 `gemini-2.5-flash`。目前已正式更新預設模型、在結構化 JSON 端點上關閉了推理思考過程，並完成了歷史失敗數據的修復與重新生成。

---

## 2. 背景與問題陳述 (Background and Problem Statement)
先前 Ingestion Pipeline 頻繁在摘要生成階段遭遇異常，導致系統產生不完整的預留內容（如含有 "placeholder content" 或 "real summary generation pending" 的英文垃圾文案）。

調查後定位到兩個核心系統漏洞：
1. **預設模型缺陷**：硬編碼的預設模型 `openrouter:xiaomi/mimo-v2.5` 在推理時思考過程過長。對長文本逐字稿進行摘要時，思考過程會吃滿 4096 的輸出 token 空間，導致 JSON 輸出截斷（`Unterminated string` 錯誤），從而回退至預留占位符。
2. **環境配置分歧**：在生產環境的 nightly crontab 任務（`run_nightly.sh`）中，模型被手動環境變數覆蓋為 `gemini-2.5-flash-lite`（提取）和 `gemini-2.5-flash`（撰寫），因此 nightly 能正常產出。然而，在 nightly shell 以外觸發的所有 Pipeline（如手動 `run_pipeline` 測試、後台 `EpisodeWatcher` 監聽、管理面板 Trial run 等）都因沒有載入覆蓋變數而直接使用代碼預設的 `mimo-v2.5`，導致默默退化成占位內容。

---

## 3. 實驗設計與設定 (Methodology & Setup)
為了評估系統在全新「章節合併與長度對齊（`consolidate_chapters`）」節點下的效能，我們選擇了兩組不同時長的真實 Podcast 逐字稿進行測試：
- **短節目 ("母子基金")**：音訊時長約 21 分鐘。
- **長節目 ("Gooaye EP672")**：音訊時長約 53 分鐘。

### 參選模型 (Finalists)
1. **`deepseek-v4-pro`** (經由 OpenRouter 呼叫 DeepSeek V4 Pro)
2. **`gemini-2.5-flash`** (經由 OpenRouter 呼叫 Gemini 2.5 Flash)

---

## 4. 定量數據結果 (Quantitative Results)
以下為兩組模型在全新 `consolidate_chapters` 流程下產出的數據對比：

| 指標 (Metric) | 短節目 (母子基金 - 21 min) | 長節目 (Gooaye EP672 - 53 min) |
| :--- | :---: | :---: |
| **細粒度事件數 (Fine Events)** | 40 | 39 |
| **政策過濾後事件數 (Kept Events)** | 30 | 22 |
| **合併後的章節數 (Consolidated Chapters)** | 4 | 9 |
| **撰寫報告段落數 (Writer Sections)** | 4 | 9 |
| **是否觸發預留退回 (Placeholder Fallback)** | 無 (None) | 無 (None) |
| **簡體字洩漏數 (Simplified Glyphs)** | 0 | 0 |
| **個股/標籤標記連結數 (Ticker / Tag Links - Gemini)** | 0 / 28 | 12 / 131 |

---

## 5. 定性評估與模型表現對比 (Qualitative Evaluation)
我們針對 Gooaye EP672 長節目（主題為半導體元件與IDM供應鏈）對兩組模型的摘要品質進行了對比：

### A. `deepseek-v4-pro` (勝出)
*   **摘要篇幅與結構**：緊湊且具備社群編輯感（產出 5 個大章節）。成功將 tangental（偏離主題）的 Q&A 閒聊（如生技股、軟體工程師職涯、社會成本）過濾，緊扣核心的功率半導體與 IDM 投資主線。
*   **標籤符合度**：標籤數量合理，高度符合專案中「封閉標籤詞彙表」約束，避免標籤發散與重複。
*   **個股代號連結**：標的識別與情緒連結極為精準（精確連結了 `TXN`, `STM`, `ON`, `IFX`, `6963`, `2330`, `TSLA` 等標的）。
*   **繁體中文忠實度**：產出 100% 正確的現代繁體中文。先前檢測回報的簡體洩漏證實均為「誤判」：例如 `疲` 屬繁簡同形字，而 `台`、`群`、`才` 均為台灣標準繁體，但被嚴苛的 OpenCC 轉換檢驗標記。

### B. `gemini-2.5-flash`
*   **摘要篇幅與結構**：篇幅冗長、全面但密度較低（產出 9 個大章節）。完整保留了節目後半段所有職涯、社會成本等閒聊對談。
*   **標籤符合度**：出現嚴重的標籤通膨（高達 131 個標籤），且發明了大量非詞彙表約定的無效標籤（如 `#tag:InvestmentOpportunities` 等英文隨機標籤），在寫入階段會被直接剔除。
*   **繁體中文忠實度**：語意流暢且符合台灣閱讀習慣。

---

## 6. 漏洞修復與工程實踐 (Resolutions & Engineering Actions)
為了從根本上提高 Ingestion 的穩定性，在 PR #286 中（已合併至 `develop` 分支）實施了以下架構變更：

1. **對齊預設模型**：將代碼中所有節點角色（提取、撰寫、總編等）的預設模型更新為 `openrouter:deepseek/deepseek-v4-pro`，徹底廢棄 mimo 模型。
2. **關閉推理思考過程**：在 OpenRouter 調用參數中顯式加入 `extra_body={"reasoning": {"enabled": False}}`。這防止了推理模型的隱藏思考過程佔用 token，確保長節目摘要時 JSON 回傳不被截斷。
3. **標準化環境變數**：移成了 nightly 腳本中的環境變數 overrides 以及對 `GOOGLE_API_KEY`/Gemini 的依賴。現在當 Watcher 監聽器和 Trial Run 自動觸發時，將與生產 nightly 調用完全相同的 DeepSeek 配置，確保測試與運行的一致性。
4. **歷史數據修復 (Backfill)**：經驗證，修復腳本 `backfill_regen_from_gcs.py` 能成功從 GCS 載入已有的逐字稿快照，直接進行 DeepSeek-V4-Pro Pipeline 重新摘要，並安全寫入 Firestore、刷新快取與 Cloudflare Edge。測試案例證實，先前 failed 的 placeholder 節目重跑後成功產出了含有 47 個個股連結、31 個標籤的 4 章節真實摘要。
