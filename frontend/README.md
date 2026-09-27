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
| **Home** | `/` | Recent episodes and market content |
| **Podcasts** | `/podcaster`, `/podcaster/:id`, `/episode/:id` | Channel directory, archives, and episode summaries |
| **Stocks and sectors** | `/stock`, `/stock/:ticker`, `/sector/:exposureId` | Stock directory, dashboards, and sector exposure |
| **Topics** | `/topics`, `/topics/:tag` | Topic discovery and related content (`/tag/:tag` also works) |
| **Editorial** | `/weekly`, `/weekly/:week`, `/articles`, `/article/:slug` | Weekly notes and articles |
| **Membership** | `/membership`, `/member` | Plans and the signed-in member hub |
| **Personal** | `/watchlist`, `/settings` | Signed-in watchlist and settings |

Legacy links to `/picks` redirect to `/member`; `/story` redirects to home. `/news/:id`
redirects to an episode or the home page.

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
- **Topic discovery** — browse themes and related episodes, articles, and stocks.
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
| State / routing | Zustand 5, React Router 7 |
| Validation | Zod 4 (every API response is schema-validated) |
| Markdown | React Markdown |

---

## Getting Started

**Prerequisites:** Node 20+ and npm. Local development uses the shared dev API by default.

```bash
npm install
npm run dev -- --port 5173 --strictPort
```

### Environment

The dev server runs at `http://localhost:5173` and calls `https://dev-api.tinboker.com`
when `VITE_API_BASE_URL` is unset. Use the authorized Google account for dev API access.
Port 5173 is required by the dev API's CORS allowlist.

For a local backend, set this in the gitignored `.env.local`:

```bash
VITE_API_BASE_URL=http://localhost:5174
```

`VITE_GOOGLE_CLIENT_ID` is needed for Google sign-in if it is not supplied by your
environment. See [Google login setup](docs/process/google-login-setup.md). Deployment
stage variables and secrets are documented in the [infra runbook](../docs/infra-runbook.md).

### Scripts

| Command | What it does |
|---------|--------------|
| `npm run dev -- --port 5173 --strictPort` | Vite dev server on the CORS-allowed port |
| `npm run build` | `tsc -b` type-check + Vite build (set `VITE_STAGE=PRODUCTION` to compare deployed production output) |
| `npm run lint` | ESLint |
| `npm run preview` | Serve the production build locally |
| `npm run generate-pwa-icons` / `generate-screenshots` | Asset generators |

---

## Project Structure

```
src/
├── pages/          Route-level views
├── components/     Reusable UI — charts, stock, home, podcast, player, and UI controls
├── services/       API client (axios) + WebSocket price feed
│   └── api/        Per-domain backend endpoint wrappers
├── store/          Zustand global state
├── validation/     Zod schemas for API response validation
├── hooks/ lib/ utils/     Hooks and helpers
├── types/          TypeScript type definitions
└── assets/         Static assets
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

See the root [deployment workflow](../docs/workflows/deploy-flow.md) for the CI gates,
release process, and verification.

---

## Contributing

Branch from `develop` (`feat/<name>` or `fix/<name>`), open a PR targeting `develop`, and make sure
CI is green. See the root [deployment workflow](../docs/workflows/deploy-flow.md) for
the full branching and release flow, and the [frontend docs index](docs/README.md) for
additional guidance.
