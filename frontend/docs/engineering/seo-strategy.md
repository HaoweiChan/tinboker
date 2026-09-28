# TrendBrief SEO Strategy and Optimization Guide

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

This document records the SEO (Search Engine Optimization) strategy for the TrendBrief website, aiming to increase website traffic and search rankings.

## 1. Technical SEO

### 1.1 Dynamic Meta Tags (Implemented)
*   **Tool**: `react-helmet-async`
*   **Function**: Generate unique `<title>` and `<meta name="description">` for each page.
*   **Goal**: Allow search engines to accurately understand the content of each page.

### 1.2 Structured Data (JSON-LD) (Implemented)
*   **Standard**: Schema.org
*   **Types**: 
    *   `NewsArticle`: For news/summary pages.
    *   `PodcastEpisode`: For podcast episodes.
    *   `WebSite`: For the landing page (with Sitelinks Search Box).
    *   `ProfilePage`/`Organization`: For podcaster pages and stock dashboards.
    *   `BreadcrumbList`: For breadcrumb navigation.
*   **Goal**: Achieve "Rich Snippets" in search results, such as star ratings, publication dates, and author information.

### 1.3 Sitemap & Robots.txt (Implemented)
*   **Robots.txt**: Guide crawler behavior.
*   **Sitemap.xml**: List all important page links to accelerate indexing.

### 1.4 Canonical URLs (Implemented)
*   Ensure all pages have `<link rel="canonical" ... />` to avoid duplicate content issues caused by parameters (e.g. `?ref=fb`).

## 2. On-Page SEO

### 2.1 Title and Description
*   **Title**: Should contain keywords (e.g., "AI Supply Chain", "TSMC").
*   **Description**: Concise summary (about 150 characters) to attract clicks.

### 2.2 Image SEO (Implemented)
*   **Alt Text**: All images must have alt text describing the image content.
*   **Filename**: Use meaningful filenames (e.g., `tsmc-stock-chart.png` instead of `img123.png`).

## 3. Social Signals

### 3.1 Open Graph (OG) Tags
*   Optimize preview images and titles when shared on FB, Twitter, Line.
*   **Dynamic OG Image**: Generate dedicated cover images for each episode.

## 4. Performance and Experience (Core Web Vitals)

*   **LCP (Largest Contentful Paint)**: Optimize loading speed.
    *   (Implemented) Enable `loading="lazy"` for off-screen images.
*   **CLS (Cumulative Layout Shift)**: Avoid layout shifts.
    *   (Implemented) Ensure images have explicit `width` and `height` attributes or defined aspect ratios.
    *   (Implemented) Use lazy loading for markdown images with containment styles.

## 5. Site Architecture & Accessibility

### 5.1 Internal Linking (Implemented)
*   **Internal Linking**: Ensure navigation elements use proper `<a>` tags (or `<Link>` components) instead of `onClick` handlers to allow crawlers to discover pages.

### 5.2 Semantic HTML (Implemented)
*   **Semantic HTML**: Use semantic tags (`<main>`, `<article>`, `<nav>`, `<section>`, `<aside>`, etc.) to help search engines understand page structure.

### 5.3 Breadcrumbs (Implemented)
*   **Breadcrumbs**: Implement `BreadcrumbList` schema and visual navigation for better user experience and structure understanding.
