<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="public/brand/tinboker-square-dark-512.png">
  <img src="public/brand/tinboker-square-light-512.png" alt="TinBoker logo" width="120" height="120">
</picture>

# TinBoker Web UI

**Listen to the market, see the trend.**

React 19 + TypeScript + Vite single-page app for the [TinBoker](../README.md) platform —
a Traditional-Chinese financial intelligence site pairing TW/US stock data with
AI-summarized financial podcasts.

[![React](https://img.shields.io/badge/React-19-149ECA?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vite.dev)
[![Cloudflare Pages](https://img.shields.io/badge/Cloudflare-Pages-F38020?style=flat-square&logo=cloudflare&logoColor=white)](https://pages.cloudflare.com)

**Live:** [tinboker.com](https://tinboker.com)

</div>

---

## Pages at a glance

| Page | Route | What it is |
|------|-------|-----------|
| **Home** | `/` | Latest podcast summaries, top market movers, active channels |
| **Episode / News detail** | `/episode/:id`, `/news/:id` | AI summary with clickable in-text tickers and tag navigation |
| **Stock** | `/stock/:ticker` | Live price + chart, key stats, and every episode that mentioned the ticker |
| **Channel** | `/podcaster/:id` | A creator's episode archive and pick performance |
| **Tag / Topic** | `/tag/:tag` | All content for a theme (e.g. `#AI伺服器`, `#半導體`) across channels |
| **Picks** | `/picks` | Podcast-pick performance scoreboard |
| **Story / Graph gallery** | `/story` | Interactive concept/supply-chain relationship graphs |

<div align="center">
  <img src="public/screenshots/home-dark.png" alt="Home dashboard" width="48%">
  <img src="public/screenshots/stock-dark.png" alt="Stock dashboard" width="48%">
</div>

---

## Features

- **Podcast intelligence** — AI episode summaries with interactive tickers that surface live
  price + chart on hover, plus channel and tag filtering.
- **Stock dashboards** — TradingView charts, real-time quotes over WebSocket, and the related
  episode feed for each ticker (TW + US markets).
- **Relationship graphs** — force-directed company/sector/concept graphs (React Flow + D3).
- **Search** — full-text search with autocomplete and trending tickers/tags.
- **PWA** — installable, offline-aware, with light/dark theming and an SVG icon system (no emoji).
- **i18n** — Traditional-Chinese (`zh-TW`) UI throughout.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 19, TypeScript 5.9 |
| Build | Vite 7 |
| Styling | Tailwind CSS 4, Shadcn UI |
| Charts | TradingView Lightweight Charts, D3.js, Nivo |
| Graph viz | React Flow 11, Dagre, ELK |
| State / routing | Zustand 5, React Router 7 |
| Validation | Zod 4 (every API response is schema-validated) |
| Markdown | React Markdown |

---

## Getting Started

**Prerequisites:** Node 20+, npm. A running backend (see [`../backend/`](../backend/)) or point at
a deployed API.

```bash
npm install
cp .env.example .env.local      # set VITE_API_BASE_URL
npm run dev                     # → http://localhost:5173
```

### Environment

`.env.local` (git-ignored) overrides per-developer settings:

```bash
VITE_API_BASE_URL=http://localhost:5174   # or https://api.tinboker.com
VITE_STAGE=DEV|STAGING|PRODUCTION
VITE_GOOGLE_CLIENT_ID=...
```

### Scripts

| Command | What it does |
|---------|--------------|
| `npm run dev` | Vite dev server (mode `dev`) on `:5173` |
| `npm run build` | `tsc -b` type-check + Vite production build |
| `npm run lint` | ESLint |
| `npm run preview` | Serve the production build locally |
| `npm run generate-pwa-icons` / `generate-screenshots` / `generate-sitemap` | Asset/SEO generators |

---

## Project Structure

```
src/
├── pages/          Route-level views (42 pages)
├── components/     Reusable UI — charts/ stock/ graph/ home/ industry/ podcast/ player/ ui/ …
├── services/       API client (axios) + WebSocket price feed
│   └── api/        Per-domain backend endpoint wrappers
├── store/          Zustand global state
├── schemas/ validation/   Zod schemas for API response validation
├── hooks/ lib/ utils/     Hooks and helpers
├── types/          TypeScript type definitions
└── assets/         SVG icon system (no emoji icons)
```

Conventions (no `any`, Zod-validated responses, DEV-gated console output, the icon system) are in
[`AGENTS.md`](AGENTS.md).

---

## Deployment

The app deploys to **Cloudflare Pages** via GitHub Actions — never deploy by hand:

| Branch / ref | Environment | URL |
|--------------|-------------|-----|
| merge to `develop` | Dev | [dev.tinboker.com](https://dev.tinboker.com) |
| merge to `main` | Staging | [staging.tinboker.com](https://staging.tinboker.com) |
| `v*` tag on `main` | Production | [tinboker.com](https://tinboker.com) |

The `frontend-ci.yml` (type-check + lint) and `frontend-deploy.yml` (Pages deploy + CDN purge)
workflows handle this. See the root [`README.md`](../README.md) and
[`docs/workflows/deploy-flow.md`](../docs/workflows/deploy-flow.md).

---

## Contributing

Branch from `develop` (`feat/<name>` or `fix/<name>`), open a PR targeting `develop`, and make sure
CI is green. See [`CLAUDE.md`](../CLAUDE.md) for the full branching and review flow.
