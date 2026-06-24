# AGENTS.md — TinBoker Frontend

Domain-specific guidelines for AI agents working in `frontend/`. For project-wide rules
(git, deployment, environments, known bugs), see the root `CLAUDE.md`.

---

## Local Preview — ALWAYS run after a UI/UX change

After any UI/UX edit, host the frontend locally against the **dev backend** so the user can
see it. Do this every time — don't just report the diff.

```bash
cd frontend
npm run dev -- --port 5173 --strictPort   # vite --mode dev → .env.dev(.local) → https://dev-api.tinboker.com
```

Log in with an admin Google account — dev-api is OAuth-gated.

**MUST be port 5173.** dev-api's CORS allowlist only includes `http://localhost:5173`. If
5173 is taken, Vite silently jumps to 5174 and the browser gets CORS-blocked → **episodes/API
come back empty with no obvious error**. So pin it with `--port 5173 --strictPort` and free
5173 first if another dev server (e.g. the primary checkout's) holds it:
`kill $(lsof -nP -iTCP:5173 -sTCP:LISTEN -t)`.

**Working in a git worktree** (no `node_modules` / no env files there)? Wire it up once
without a full reinstall — symlink deps from the primary checkout and copy the gitignored
dev env files (copying `.env*` to run is fine; never commit them):

```bash
cd frontend
ln -sfn ../../../frontend/node_modules node_modules        # adjust depth to reach primary checkout's frontend/
cp ../../../frontend/.env.dev ../../../frontend/.env.dev.local .
npm run dev
```

Env precedence (Vite, mode `dev`): `.env.dev.local` > `.env.local` > `.env.dev`. The
mode-specific `.env.dev.local` holds `VITE_API_BASE_URL=https://dev-api.tinboker.com`, so it
wins over any localhost value in `.env.local`. To point at a **local** backend instead, run
plain `npm run dev -- --mode local` only if you have the backend up on :5174.

---

## UI Conventions

### No Emoji Icons

Never use emoji characters (🤖, 📊, 💰, …) as icons in JSX, strings, error messages,
or empty states. Emoji render inconsistently across platforms and can't be styled.

- Use SVG icon components from `src/components/ui/Icons.tsx` (e.g. `RoboticsIcon`, `BrainIcon`, `GraphIcon`)
- Import an SVG as a URL: `import iconUrl from '@/components/icons/icon.svg'`
- Use `IconRenderer` for dynamic icons: `<IconRenderer icon="robotics" size={48} />`

### Traditional Chinese (zh-TW) Localization

All user-facing text must be in Traditional Chinese (zh-TW). Code, comments, variable
names, console logs, and API endpoint names stay in English.

- **Brand name:** TinBoker in English contexts; **聽播客** in Chinese contexts. Wordmark: 聽播客 ｜ TinBoker
- Translate: UI labels, headings, nav items, placeholders, error messages, tooltips, chart labels, table headers, empty/loading states
- Keep in English: code identifiers, comments, console logs, debug messages, API endpoint names, file names, CSS class names

Common term reference:

| English | 繁體中文 | English | 繁體中文 |
|---|---|---|---|
| Home | 首頁 | Price | 價格 |
| Dashboard | 儀表板 | Change | 漲跌 |
| News | 新聞 | Volume | 成交量 |
| Stocks | 股票 | Market Cap | 市值 |
| Industry | 產業 | P/E Ratio | 本益比 |
| Search | 搜尋 | Revenue | 營收 |
| Filter | 篩選 | Loading | 載入中 |
| Save / Cancel | 儲存 / 取消 | No Data | 無資料 |
| Load More | 載入更多 | Coming Soon | 即將推出 |
