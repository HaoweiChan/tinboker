

---

## Dify Structured Output Schema

```yaml
structured_output:
  schema:
    properties:
      meta:
        properties:
          episode_id:
            description: Unique identifier for the podcast episode
            type: string
          publication_date:
            description: ISO 8601 formatted publication date
            type: string
          podcaster:
            description: Name of the podcast
            type: string
        required:
        - episode_id
        - publication_date
        - podcaster
        type: object
      ticker_recommendations:
        items:
          properties:
            ticker:
              description: Stock ticker symbol
              type: string
            exchange:
              description: Stock exchange (e.g., NASDAQ, NYSE, TAIEX)
              type: string
            sentiment:
              description: Sentiment classification (BULLISH, BEARISH, NEUTRAL)
              type: string
            sentiment_score:
              description: Sentiment score between 0.0 and 1.0
              type: number
            time_horizon:
              description: Investment time horizon (SHORT_TERM, MEDIUM_TERM, LONG_TERM)
              type: string
            price_target:
              description: Optional price target
              type: number
            bluf_thesis:
              description: Bottom line up front thesis for this ticker recommendation
              type: string
            reasons:
              items:
                properties:
                  title:
                    description: Title of the reason/key driver
                    type: string
                  description:
                    description: Detailed description of the reason
                    type: string
                  category:
                    description: Category of the reason (e.g., MACRO, MOAT, OPERATIONAL, DEMAND)
                    type: string
                  start_index:
                    description: Starting sentence index (0-based) where podcaster mentioned this reason
                    type: integer
                  end_index:
                    description: Ending sentence index (inclusive) where podcaster mentioned this reason
                    type: integer
                  start_time:
                    description: Start time in milliseconds where podcaster mentioned this reason
                    type: integer
                  end_time:
                    description: End time in milliseconds where podcaster mentioned this reason
                    type: integer
                required:
                - title
                - description
                - category
                - start_index
                - end_index
                - start_time
                - end_time
                type: object
              type: array
            risks:
              items:
                properties:
                  title:
                    description: Title of the risk
                    type: string
                  description:
                    description: Detailed description of the risk
                    type: string
                  severity:
                    description: Risk severity (LOW, MEDIUM, HIGH, CRITICAL)
                    type: string
                  start_index:
                    description: Starting sentence index (0-based) where podcaster mentioned this risk
                    type: integer
                  end_index:
                    description: Ending sentence index (inclusive) where podcaster mentioned this risk
                    type: integer
                  start_time:
                    description: Start time in milliseconds where podcaster mentioned this risk
                    type: integer
                  end_time:
                    description: End time in milliseconds where podcaster mentioned this risk
                    type: integer
                required:
                - title
                - description
                - severity
                - start_index
                - end_index
                - start_time
                - end_time
                type: object
              type: array
            financials:
              description: Optional financial data (can be null or object)
              type: object
          required:
          - ticker
          - exchange
          - sentiment
          - sentiment_score
          - time_horizon
          - bluf_thesis
          - reasons
          - risks
          type: object
        type: array
    required:
    - meta
    - ticker_recommendations
    type: object
structured_output_enabled: true
```

---

## Presentation Formats

When presenting multiple tickers with their reasons and risks, consider these formats based on your use case:

### Format 1: Hierarchical Markdown (Recommended for Articles)

Best for: Long-form articles, detailed analysis, web content

```markdown
# 本集重點股票推薦

## [NVDA](#ticker:NVDA) - NVIDIA Corporation
**交易所**: NASDAQ | **情緒**: 🟢 看多 (0.85) | **時間框架**: 長期 | **目標價**: $180

### 核心論點
儘管估值偏高，NVDA 仍然是買入標的，因為數據中心需求加速，且軟體利潤率開始顯現。

### 看多理由

#### 1. 主權 AI (#time:930000)
**類別**: 宏觀 | **位置**: 句子 45-67

各國正在購買晶片以建立國內 AI 基礎設施，創造了新的需求層。

#### 2. 軟體鎖定 (#time:1330000)
**類別**: 護城河 | **位置**: 句子 132-148

CUDA 平台保留率接近 100%，形成對競爭對手的護城河。

#### 3. 供應鏈 (#time:2145000)
**類別**: 營運 | **位置**: 句子 214-228

台積電的瓶頸正在緩解，允許第四季產量增加。

### 風險提示

#### ⚠️ 中國限制 (#time:2895000) - 高風險
**位置**: 句子 289-305

進一步的出口禁令可能削減總收入的 5-10%。

#### ⚠️ 估值 (#time:3120000) - 中等風險
**位置**: 句子 312-325

定價完美；任何收益失誤都會導致急劇拋售。

---

## [TSM](#ticker:TSM) - Taiwan Semiconductor
**交易所**: NYSE | **情緒**: 🟡 中性 (0.55) | **時間框架**: 中期

### 核心論點
台積電受益於 AI 晶片需求，但面臨供應鏈限制。

### 看多理由

#### 1. AI 需求 (#time:3500000)
**類別**: 需求 | **位置**: 句子 350-365

AI 晶片製造商的強勁需求推動產能利用率。

### 風險提示

#### ⚠️ 產能限制 (#time:3800000) - 中等風險
**位置**: 句子 380-395

有限的產能擴張可能限制增長。
```

### Format 2: Summary Table (Quick Overview)

Best for: Executive summaries, dashboards, quick comparisons

```markdown
# 股票推薦摘要

| 股票 | 交易所 | 情緒 | 評分 | 時間框架 | 理由數 | 風險數 | 核心論點 |
|------|--------|------|------|----------|--------|--------|----------|
| [NVDA](#ticker:NVDA) | NASDAQ | 🟢 看多 | 0.85 | 長期 | 3 | 2 | 數據中心需求加速，軟體利潤率顯現 |
| [TSM](#ticker:TSM) | NYSE | 🟡 中性 | 0.55 | 中期 | 1 | 1 | AI 晶片需求強勁，但供應鏈受限 |

## 詳細分析

### [NVDA](#ticker:NVDA) 詳細資訊

**看多理由**:
- **主權 AI** (#time:930000) - 宏觀 | 各國建立國內 AI 基礎設施
- **軟體鎖定** (#time:1330000) - 護城河 | CUDA 平台保留率接近 100%
- **供應鏈** (#time:2145000) - 營運 | 台積電瓶頸緩解

**風險**:
- **中國限制** (#time:2895000) - 🔴 高風險 | 可能削減 5-10% 收入
- **估值** (#time:3120000) - 🟡 中等風險 | 定價完美，容錯率低
```

### Format 3: Card-Based Format (Visual UI)

Best for: Web applications, interactive dashboards, mobile apps

```markdown
# 本集股票推薦

<div class="ticker-cards">

## 📈 [NVDA](#ticker:NVDA) - NVIDIA
<div class="ticker-card">
  <div class="ticker-header">
    <span class="sentiment bullish">🟢 看多 (0.85)</span>
    <span class="time-horizon">長期投資</span>
  </div>
  
  <div class="thesis">
    <strong>核心論點:</strong> 儘管估值偏高，NVDA 仍然是買入標的，因為數據中心需求加速，且軟體利潤率開始顯現。
  </div>
  
  <div class="reasons">
    <h4>看多理由 (3)</h4>
    <ul>
      <li><strong>主權 AI</strong> <a href="#time:930000">🔗 15:30</a> - 各國建立國內 AI 基礎設施</li>
      <li><strong>軟體鎖定</strong> <a href="#time:1330000">🔗 22:10</a> - CUDA 平台保留率接近 100%</li>
      <li><strong>供應鏈</strong> <a href="#time:2145000">🔗 35:45</a> - 台積電瓶頸緩解</li>
    </ul>
  </div>
  
  <div class="risks">
    <h4>風險提示 (2)</h4>
    <ul>
      <li><span class="severity high">🔴 高風險</span> <strong>中國限制</strong> <a href="#time:2895000">🔗 48:15</a> - 可能削減 5-10% 收入</li>
      <li><span class="severity medium">🟡 中等風險</span> <strong>估值</strong> <a href="#time:3120000">🔗 52:00</a> - 定價完美，容錯率低</li>
    </ul>
  </div>
</div>

## 📊 [TSM](#ticker:TSM) - Taiwan Semiconductor
<div class="ticker-card">
  <div class="ticker-header">
    <span class="sentiment neutral">🟡 中性 (0.55)</span>
    <span class="time-horizon">中期投資</span>
  </div>
  
  <div class="thesis">
    <strong>核心論點:</strong> 台積電受益於 AI 晶片需求，但面臨供應鏈限制。
  </div>
  
  <div class="reasons">
    <h4>看多理由 (1)</h4>
    <ul>
      <li><strong>AI 需求</strong> <a href="#time:3500000">🔗 58:20</a> - AI 晶片製造商強勁需求</li>
    </ul>
  </div>
  
  <div class="risks">
    <h4>風險提示 (1)</h4>
    <ul>
      <li><span class="severity medium">🟡 中等風險</span> <strong>產能限制</strong> <a href="#time:3800000">🔗 63:20</a> - 產能擴張受限</li>
    </ul>
  </div>
</div>

</div>
```

### Format 4: Timeline Format (Chronological)

Best for: Podcast transcripts, time-based navigation, video players

```markdown
# 本集股票討論時間軸

## 時間軸總覽

| 時間 | 股票 | 主題 | 類型 |
|------|------|------|------|
| [15:30](#time:930000) | [NVDA](#ticker:NVDA) | 主權 AI | 看多理由 |
| [22:10](#time:1330000) | [NVDA](#ticker:NVDA) | 軟體鎖定 | 看多理由 |
| [35:45](#time:2145000) | [NVDA](#ticker:NVDA) | 供應鏈 | 看多理由 |
| [48:15](#time:2895000) | [NVDA](#ticker:NVDA) | 中國限制 | ⚠️ 風險 |
| [52:00](#time:3120000) | [NVDA](#ticker:NVDA) | 估值 | ⚠️ 風險 |
| [58:20](#time:3500000) | [TSM](#ticker:TSM) | AI 需求 | 看多理由 |
| [63:20](#time:3800000) | [TSM](#ticker:TSM) | 產能限制 | ⚠️ 風險 |

## 詳細時間軸

### [15:30](#time:930000) - [NVDA](#ticker:NVDA) 主權 AI
**類別**: 看多理由 - 宏觀  
**內容**: 各國正在購買晶片以建立國內 AI 基礎設施，創造了新的需求層。

### [22:10](#time:1330000) - [NVDA](#ticker:NVDA) 軟體鎖定
**類別**: 看多理由 - 護城河  
**內容**: CUDA 平台保留率接近 100%，形成對競爭對手的護城河。

### [35:45](#time:2145000) - [NVDA](#ticker:NVDA) 供應鏈
**類別**: 看多理由 - 營運  
**內容**: 台積電的瓶頸正在緩解，允許第四季產量增加。

### [48:15](#time:2895000) - [NVDA](#ticker:NVDA) 中國限制 ⚠️
**類別**: 風險 - 🔴 高風險  
**內容**: 進一步的出口禁令可能削減總收入的 5-10%。

### [52:00](#time:3120000) - [NVDA](#ticker:NVDA) 估值 ⚠️
**類別**: 風險 - 🟡 中等風險  
**內容**: 定價完美；任何收益失誤都會導致急劇拋售。

### [58:20](#time:3500000) - [TSM](#ticker:TSM) AI 需求
**類別**: 看多理由 - 需求  
**內容**: AI 晶片製造商的強勁需求推動產能利用率。

### [63:20](#time:3800000) - [TSM](#ticker:TSM) 產能限制 ⚠️
**類別**: 風險 - 🟡 中等風險  
**內容**: 有限的產能擴張可能限制增長。
```

### Format 5: Comparison Matrix

Best for: Side-by-side comparisons, decision making

```markdown
# 股票推薦對比

## 快速對比

| 項目 | [NVDA](#ticker:NVDA) | [TSM](#ticker:TSM) |
|------|---------------------|-------------------|
| **情緒** | 🟢 看多 (0.85) | 🟡 中性 (0.55) |
| **時間框架** | 長期 | 中期 |
| **看多理由數** | 3 | 1 |
| **風險數** | 2 | 1 |
| **最高風險** | 🔴 高 (中國限制) | 🟡 中等 (產能限制) |

## 詳細對比

### 看多理由對比

| 股票 | 理由 | 類別 | 時間 |
|------|------|------|------|
| [NVDA](#ticker:NVDA) | 主權 AI | 宏觀 | [15:30](#time:930000) |
| [NVDA](#ticker:NVDA) | 軟體鎖定 | 護城河 | [22:10](#time:1330000) |
| [NVDA](#ticker:NVDA) | 供應鏈 | 營運 | [35:45](#time:2145000) |
| [TSM](#ticker:TSM) | AI 需求 | 需求 | [58:20](#time:3500000) |

### 風險對比

| 股票 | 風險 | 嚴重程度 | 時間 |
|------|------|----------|------|
| [NVDA](#ticker:NVDA) | 中國限制 | 🔴 高 | [48:15](#time:2895000) |
| [NVDA](#ticker:NVDA) | 估值 | 🟡 中等 | [52:00](#time:3120000) |
| [TSM](#ticker:TSM) | 產能限制 | 🟡 中等 | [63:20](#time:3800000) |
```

## Format Selection Guide

- **Format 1 (Hierarchical)**: Use for detailed articles, blog posts, comprehensive analysis
- **Format 2 (Summary Table)**: Use for executive summaries, email digests, quick scans
- **Format 3 (Card-Based)**: Use for web applications, interactive UIs, mobile apps
- **Format 4 (Timeline)**: Use for podcast transcripts, video players, chronological navigation
- **Format 5 (Comparison)**: Use for decision-making tools, side-by-side analysis

## Implementation Notes

1. **Ticker Links**: Use `[Display Name](#ticker:SYMBOL)` format for interactive ticker hover cards
2. **Time Links**: Use `(#time:milliseconds)` format for timestamp navigation
3. **Sentiment Icons**: 
   - 🟢 for BULLISH
   - 🟡 for NEUTRAL  
   - 🔴 for BEARISH
4. **Risk Severity Icons**:
   - 🔴 for HIGH/CRITICAL
   - 🟡 for MEDIUM
   - 🟢 for LOW
5. **Language**: All content should be in Traditional Chinese (繁體中文) for this use case