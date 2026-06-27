# LLM Podcast Summarization Experiment Report

## 1. Executive Summary
This report documents the benchmarking and investigation of LLM models for the podcast ingestion and summarization pipeline. The experiment was initiated due to a high rate of episodes failing to generate real summaries, resulting in fallback "placeholder" documents in production. 

The investigation revealed that the default model configuration (`openrouter:xiaomi/mimo-v2.5`) was a reasoning-capable model that exhausted its completion token budget on hidden reasoning chains, causing JSON output truncations. Benchmarking identified `deepseek-v4-pro` as the superior model for conciseness, tag vocabulary compliance, and ticker linking accuracy over `gemini-2.5-flash`. The default model has been updated, reasoning has been disabled for structured JSON endpoints, and a backfill has been executed to heal affected historical episodes.

---

## 2. Background and Problem Statement
Historically, the ingestion pipeline frequently encountered failures during the summarization stage. In these cases, the pipeline fell back to generating generic placeholder summaries (e.g., containing indicators like "placeholder content" or "real summary generation pending").

The investigation identified two core issues:
1. **Broken Default Model**: The hardcoded default model was `openrouter:xiaomi/mimo-v2.5`. Because it is a reasoning model, its hidden reasoning chains consumed the bulk of the `max_tokens` (4096) output budget. For long transcripts, this led to JSON completion truncations (e.g., `Unterminated string` errors) and triggered the placeholder fallback.
2. **Environment Divergence**: In production, nightly cron runs (`run_nightly.sh`) avoided this by overriding environment variables (`EXTRACTOR_MODEL=gemini-2.5-flash-lite`, `WRITER_MODEL=gemini-2.5-flash`). However, any runs triggered outside the nightly shell—such as direct `run_pipeline` invocations, local testing, the admin panel "trial run", or the 10-minute automated `EpisodeWatcher`—fallback-routed to the broken `mimo-v2.5` model, producing silent placeholder failures.

---

## 3. Methodology & Setup
To verify the performance of the pipeline under the new chapter-consolidation workflow (`consolidate_chapters`), the pipeline was executed on two transcripts representing different episode lengths:
- **Short Episode ("母子基金")**: ~21 minutes in duration.
- **Long Episode ("Gooaye EP672")**: ~53 minutes in duration.

### Evaluated Models (Finalists)
1. **`deepseek-v4-pro`** (DeepSeek V4 Pro via OpenRouter)
2. **`gemini-2.5-flash`** (Gemini 2.5 Flash via OpenRouter)

---

## 4. Quantitative Results
The pipeline was run end-to-end on both test episodes. The following table summarizes the quantitative metrics observed:

| Metric | Short Episode (母子基金 - 21 min) | Long Episode (Gooaye EP672 - 53 min) |
| :--- | :---: | :---: |
| **Fine Events (Granular)** | 40 | 39 |
| **Kept Events (Policy Filtered)** | 30 | 22 |
| **Consolidated Chapters** | 4 | 9 |
| **Writer Sections** | 4 | 9 |
| **Placeholder/Fallback Triggered** | None | None |
| **Simplified-Glyph Leak Rate** | 0 | 0 |
| **Ticker / Tag Links (Gemini)** | 0 / 28 | 12 / 131 |

---

## 5. Qualitative Evaluation
The qualitative characteristics of both finalist models were evaluated on the long market episode (Gooaye EP672):

### A. `deepseek-v4-pro` (Winner)
*   **Conciseness & Focus**: Tight and editorial. Generated 5 concise sections. It successfully filtered out conversational, tangential Q&A tails (e.g., career discussions, social costs, biotech chatter) to keep the focus strictly on the core investment thesis.
*   **Tag Quality**: Moderate number of tags that strictly complied with the pipeline's closed tag vocabulary, avoiding cluster fragmentation.
*   **Ticker Linking**: Highly accurate ticker identification and linking (e.g., matching Texas Instruments `TXN`, STMicroelectronics `STM`, ON Semiconductor `ON`, Infineon `IFX`, Rohm `6963`, TSMC `2330`, and Tesla `TSLA`).
*   **Traditional Chinese Fidelity**: 100% correct Traditional Chinese. Initial detectors flagged minor issues, but these were confirmed to be false positives (e.g., `疲` which is identical in both simplified/traditional scripts, and common Taiwanese variants like `台` instead of `臺`, `群` instead of `羣`, and `才` instead of `纔`).

### B. `gemini-2.5-flash`
*   **Conciseness & Focus**: Verbose and overly comprehensive. Generated 9 sections, retaining the full conversational tails (e.g., AI's impact on software careers and social cost dynamics).
*   **Tag Quality**: Significant tag inflation (131 tags). It invented custom, unregistered tag slugs (e.g., `#tag:InvestmentOpportunities`, `#tag:CapitalFlow`) that violated the pipeline's closed tag vocabulary and caused errors during ingestion.
*   **Traditional Chinese Fidelity**: Clean and native Traditional Chinese output.

---

## 6. Root Cause Resolutions & Engineering Actions
To secure the pipeline and resolve the observed issues, the following modifications were implemented in Pull Request #286 (merged to `develop` branch):

1. **Default Model Alignment**: Set `openrouter:deepseek/deepseek-v4-pro` as the pipeline's default model across all roles, eliminating the broken `xiaomi/mimo-v2.5` model.
2. **Reasoning Token Workaround**: Enabled `extra_body={"reasoning": {"enabled": False}}` on OpenRouter calls. Disabling hidden reasoning prevents reasoning tokens from consuming the `max_tokens` budget, ensuring complete, structured JSON payloads are returned without truncation.
3. **Environment Standardization**: Cleaned up the `run_nightly.sh` overrides and removed the redundant `GOOGLE_API_KEY`/Gemini configuration. Standardizing on OpenRouter-based defaults ensures watcher daemons and manual admin trial runs behave identically to the production nightly run.
4. **Historical Healing (Backfill)**: Validated a cost-scoped backfill script (`backfill_regen_from_gcs.py`). The script successfully re-ran recent placeholder failures, retrieving the transcript from GCS, executing the new `deepseek-v4-pro` pipeline, updating Firestore docs, and purging edge CDN/Redis caches. One test run resolved a previously failed placeholder episode into a fully formatted 4-chapter summary with 47 ticker links and 31 tags.
