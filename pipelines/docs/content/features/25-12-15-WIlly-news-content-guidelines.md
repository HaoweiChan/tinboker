# News Content Generation Guidelines

This document outlines the specifications for generating Markdown content for the News/Podcast pages in Graphfolio. The backend (or content generation service) should adhere to these guidelines to ensure correct rendering of interactive elements (stock buttons, tags) and optimal SEO performance.

## Content Focus & Language

### 1. Financial Focus Only
*   **Discard Non-Financial Content**: The generated content MUST focus strictly on financial news, market analysis, earnings reports, and economic indicators.
*   **Irrelevant Topics**: Exclude content related to celebrity gossip, political drama (unless it directly impacts markets), sports, or general lifestyle news.
*   **Conciseness**: If an original source contains a mix of topics, extract ONLY the financial/market-relevant sections.

### 2. Language: Traditional Chinese (zh-TW)
*   All generated content (titles, summaries, body text) MUST be in **Traditional Chinese (繁體中文)**.
*   Ensure professional financial terminology is used (e.g., use "多頭" instead of "牛市" where appropriate for the Taiwan market context, "營收" for revenue, etc.).

## Markdown Format Specifications

The frontend (`NewsPage.tsx`) uses a customized Markdown renderer that supports specific link formats to render interactive UI components.

### 1. Stock Buttons (Interactive Tickers)

To mention a stock and render it as an interactive hover card (showing price, chart preview, etc.), use the following link format:

```markdown
[Display Name](#ticker:SYMBOL)
```

*   **Display Name**: The text to show in the article (e.g., "TSMC", "台積電", "2330").
*   **SYMBOL**: The valid stock ticker symbol (e.g., `2330`, `AAPL`, `NVDA`). Case-insensitive, but uppercase is preferred.

**Example:**
> The market was driven by **[TSMC](#ticker:2330)** and **[NVIDIA](#ticker:NVDA)** earnings reports.

**Renders as:**
> The market was driven by <StockHoverCard symbol="2330">TSMC</StockHoverCard> and <StockHoverCard symbol="NVDA">NVIDIA</StockHoverCard> earnings reports.

### 2. Tag Buttons (Topics/Categories)

To link to a specific topic tag or category page, use the following link format:

```markdown
[Tag Name](#tag:TAG_NAME)
```

*   **Tag Name**: The text to display (e.g., "AI", "Semiconductors").
*   **TAG_NAME**: The identifier for the tag, usually matching the display name or a normalized slug.

**Example:**
> Recent developments in **[Artificial Intelligence](#tag:Artificial%20Intelligence)** have boosted the sector.

**Renders as:**
> Recent developments in <Badge>Artificial Intelligence</Badge> have boosted the sector.

## SEO & Content Structure Guidelines

To improve SEO quality (`NewsPage` includes structured data and meta tags), the generated Markdown should follow these structural best practices:

### 1. Hierarchy and Headings
*   **H1**: The article title (handled by the page header, usually not needed in the markdown body unless it's a long-form report).
*   **H2 (`##`)**: Use for main sections.
*   **H3 (`###`)**: Use for subsections.
*   *Avoid skipping heading levels.*

### 2. Paragraphs and Readability
*   Keep paragraphs concise (3-5 sentences).
*   Use **bold** (`**text**`) for key terms or emphasis, but do not overuse.
*   Use *italics* (`*text*`) for secondary emphasis or quotes.

### 3. Lists
Use bullet points or numbered lists to break down complex information:
*   Key takeaways
*   Financial highlights
*   Step-by-step analysis

### 4. Blockquotes
Use blockquotes (`> text`) for:
*   Direct quotes from earnings calls.
*   Important summaries or "TL;DR" sections.
*   Analyst comments.

### 5. Images
If images are included, standard Markdown syntax is supported. **Crucially, provide descriptive ALT text** for SEO and accessibility.

```markdown
![Chart showing TSMC revenue growth Q3 2024](https://example.com/chart.png)
```

### 6. Keywords
*   Ensure primary keywords (e.g., stock names, industry terms) appear in the first paragraph.
*   Use related semantic keywords throughout the text.

## Example Payload

When the backend sends the article object, the `content` field should contain the Markdown string:

```json
{
  "title": "市場週報：AI 浪潮持續延燒",
  "content": "本週 [半導體](#tag:Semiconductor) 產業表現強勁，由 [台積電](#ticker:2330) 領漲...\n\n## 關鍵驅動因素\n\n* AI 晶片需求強勁\n* 供應鏈韌性提升\n\n> 「我們看到前所未有的需求，」執行長表示。",
  "source": "財經日報",
  "date": "2024-10-24",
  "tickers": [
    { "symbol": "2330", "price": "1080", "change": "+2.5%", "isPositive": true }
  ]
}
```
