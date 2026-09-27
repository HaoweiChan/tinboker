# UI Improvement Proposals

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

This document outlines proposed design directions to enhance the visual appeal and user experience of TrendBrief.

## 1. "Glass & Glow" (Modern & Tech) - **SELECTED**

This style emphasizes depth, transparency, and lighting effects to create a futuristic, high-tech feel suitable for AI/Data visualizations.

**Key Features:**
*   **Glassmorphism**: Use `backdrop-blur` and semi-transparent backgrounds (`bg-white/5` or `bg-slate-900/80`) for cards, headers, and panels.
*   **Glow Effects**: Add subtle outer glows (`box-shadow`) or inner gradients to interactive elements (cards on hover, active buttons).
*   **Ambient Background**: Use a dark background with subtle, moving radial gradients ("aurora" effects) to add richness without distraction.
*   **Typography**: Clean sans-serif (Plus Jakarta Sans/Roboto) with high contrast headings and muted body text.

**Implementation Plan:**
*   Add radial gradient blobs to the `Landing` page background.
*   Update `EpisodeCard` and `DashboardWidgets` to use glass styles.
*   Enhance hover states with amber glows.

---

## 2. "Clean & Grid" (Financial & Professional)

This style focuses on density, precision, and information hierarchy, mimicking professional trading terminals.

**Key Features:**
*   **High Contrast Borders**: Use distinct 1px borders (`border-slate-800`) to separate content clearly.
*   **Monospace Numbers**: Use `Roboto Mono` for all financial data (prices, percentages) for alignment.
*   **Dense Layout**: Reduce padding to show more data per screen.
*   **Color Coding**: Strictly reserve colors (Green/Red/Amber) for data; keep UI chrome monochrome.

---

## 3. "Motion & Interactive" (Engaging)

This style focuses on the "feel" of the application through movement and feedback.

**Key Features:**
*   **Entrance Animations**: Content staggers in (slides up/fades in) on load.
*   **Micro-interactions**: Buttons scale down on click; cards lift on hover.
*   **Live Data**: Animated counters for numbers that change.
*   **Particle Backgrounds**: Canvas-based moving nodes/edges in the background.

