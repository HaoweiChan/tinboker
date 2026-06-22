# Graph & visuals domain

Tool-neutral reference for any agent working on the knowledge graph, visual graph generation, gallery, design system / UI conventions, or PWA visuals. For code style, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

Two adjacent concerns:

1. **Knowledge graph & visuals** — the entity-relationship graph (companies, people, topics) plus the visual gallery and topic cloud.
2. **Cross-cutting design system** — modern-SaaS aesthetic conventions, episode card visual standards, responsive layout rules, PWA manifest and service worker.

The design-system half applies everywhere in the frontend, not just to graph pages. Other domain docs cite this one for visual rules.

## Key files

### Backend

| Concern | File |
|---|---|
| Knowledge graph API | [`backend/src/routers/graph.py`](../../backend/src/routers/graph.py), [`backend/src/services/graph.py`](../../backend/src/services/graph.py) |
| Visual graph (rendered images) | [`backend/src/routers/visual_graph.py`](../../backend/src/routers/visual_graph.py), [`backend/src/services/visual_graph.py`](../../backend/src/services/visual_graph.py) |

### Frontend

| Concern | File |
|---|---|
| Graph gallery (`/story`) | [`frontend/src/pages/GraphGallery.tsx`](../../frontend/src/pages/GraphGallery.tsx) |
| Topics cloud | [`frontend/src/pages/TopicsCloud.tsx`](../../frontend/src/pages/TopicsCloud.tsx) |
| Design preview page | [`frontend/src/pages/DesignPreview.tsx`](../../frontend/src/pages/DesignPreview.tsx) |
| Graph components | [`frontend/src/components/graph/`](../../frontend/src/components/graph/) |
| Generic UI primitives | [`frontend/src/components/ui/`](../../frontend/src/components/ui/) |
| In-progress redesign components | [`frontend/src/components/redesign/`](../../frontend/src/components/redesign/) |
| Layout (header, sidebar, main) | [`frontend/src/components/layout/`](../../frontend/src/components/layout/), [`frontend/src/components/sidebar/`](../../frontend/src/components/sidebar/) |
| Icons (SVG components — required, no emoji) | [`frontend/src/components/ui/Icons.tsx`](../../frontend/src/components/ui/Icons.tsx), [`frontend/src/components/icons/`](../../frontend/src/components/icons/) |
| Zod validation schemas | [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts) |
| API clients | [`frontend/src/services/api/graphs.ts`](../../frontend/src/services/api/graphs.ts), `visuals.ts` |

## Conventions

### Visual design (modern SaaS aesthetic)

- **Cards** use `rounded-xl` corners, `shadow-sm` at rest, `shadow-md` on hover.
- **Episode card visual contract** (consumed by HomeFeed, TagPage, PodcasterPage, StockDashboard — all surfaces use the same component):
  - **Light mode:** `bg-white`, `border-slate-200`, text `slate-900`.
  - **Dark mode:** `bg-slate-900`, no white border, text `slate-50` or `slate-200`, no shining/gradient hover.
  - Hover: elevate with shadow; the "Read Full Summary" link becomes more prominent.
  - Title section: "關鍵洞察" with a green lightbulb icon, then bulleted `key_insights`.
  - Action layout: Play (disabled), Share icon; tags at bottom-left; CTA bottom-right.
- **Sticky nav on news/episode pages** carries only essential actions (Back, Bookmark when authed). No redundant duplicates.
- **Stock chips are interactive.** Clicking a ticker chip filters the main content to episodes mentioning that ticker.
- **Mobile tag truncation.** Episode cards show up to 4 tags on viewports < 768px with a `+N more` indicator; desktop shows all.
- **Mobile action toolbar (NewsPage, < 640px).** Hide social-share buttons (LINE, Facebook) from the main bar; expose them inside a Share dropdown. Primary actions (Play, Source) stay visible; utility buttons go icon-only.

### Icons

- **Never use emoji** in JSX, strings, error messages, or empty states (see [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)).
- Use SVG components from [`frontend/src/components/ui/Icons.tsx`](../../frontend/src/components/ui/Icons.tsx) or `IconRenderer` for dynamic icons.

### PWA

- **Manifest** at `/manifest.json`: name + short_name in Traditional Chinese; `theme_color: #f59e0b` (brand amber); `display: standalone`; icons 192x192 and 512x512 (plus 180x180 apple-touch-icon).
- **Service worker** registers in production only — NOT in `import.meta.env.DEV`.
- **Caching strategy:** static assets cache-first; API responses network-first with cache fallback for offline.
- **Update notification:** when a new SW is waiting, show a non-intrusive UI; require user action to activate.

## Common pitfalls

- **BUG-2 (critical):** [`frontend/src/services/mocks/sectorData.ts`](../../frontend/src/services/mocks/sectorData.ts) `getTreeMapData()` returns `[]` — that's why the S&P 500 industry heatmap renders blank. Either populate with real sector data or hide the tab. (Industry heatmap is rendered by [`frontend/src/pages/IndustryAnalysis.tsx`](../../frontend/src/pages/IndustryAnalysis.tsx) — itself sitting in the stock-data domain, but the data layer lives here.)
- **BUG-5 (critical):** [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts) `GraphNodeDataSchema` requires `marketCapTier: z.enum(['large', 'medium', 'small'])` and `ticker`, but graph nodes from the API don't always have them. Console shows `Schema validation failed: data.nodes.0.data.marketCapTier`. Make the fields optional OR fix the API producer — don't add a silent fallback that masks the validation.
- **Dark-mode Marp slides become unreadable.** The slides have transparent backgrounds and black text. Force a light background on the slide container regardless of theme.
- **`EpisodeCard` must not have surface-specific variants.** Same look across HomeFeed, TagPage, PodcasterPage, StockDashboard. If a page needs a tweak, change the design tokens, not the component.

## External integrations

- None directly. The graph data comes from Firestore via the backend graph service.

## Cross-references

- Episode card content (data fields rendered): [`../firestore-contract.md`](../firestore-contract.md) §2.2 (Per-surface field consumption table)
- Frontend conventions (zh-TW, no emoji): [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
