# Subscription Funnel (TinBoker → Substack)

Issue: #424. Related: #407 (newsletter web edition), #423 (reusable CTA blocks).

TinBoker treats the newsletter (Substack today) as the near-term monetization layer and
TinBoker articles as the public discovery layer. This feature is the **measurable outbound
funnel** that connects the two: a stable, TinBoker-owned entry point + source attribution +
first-party analytics, so we can tell which surfaces actually drive subscription intent.

**Scope guard (kill criteria):** this is *outbound funnel plumbing only*. No email capture,
no ESP, no account linkage, no billing. The actual signup happens on the external host.

---

## Flow

```
CTA slot (e.g. article end)
  → /subscribe?source=<slot>        (frontend landing, records a VIEW)
    → GET /api/subscribe?source=<slot>   (backend records a CLICK, 302)
      → NEWSLETTER_SUBSCRIBE_URL          (Substack subscribe page)
```

- **Landing** (`/subscribe`, frontend route): reads `?source=`, posts a view beacon, shows a
  short value prop + a "前往訂閱" button. `SubscribeCTA` blocks elsewhere link here.
- **Outbound** (`GET /api/subscribe`, backend, public, all envs): records the click
  server-side (reliable — no beacon/navigation race) and 302-redirects to the config-driven
  destination.

Anchors that target `GET /api/subscribe` directly (skipping the landing page) still record a
click and redirect — useful for tight inline slots. Use the frontend helper
`subscribeOutboundUrl(source)` to build that URL.

---

## Contract — event names & query params

Keep these stable so future CTA surfaces stay comparable.

| Thing | Value | Notes |
|-------|-------|-------|
| Query param | `source` | The CTA slot. `^[a-z0-9_]{1,64}$`; anything else → `unknown`. |
| View event | ZSET `analytics:subscribe:view` | member = `source`, score = count |
| Click event | ZSET `analytics:subscribe:click` | member = `source`, score = count |
| Landing route | `/subscribe?source=<slot>` | frontend SPA route |
| Outbound route | `GET /api/subscribe?source=<slot>` | backend 302 redirect |
| View beacon | `POST /api/subscribe/view` `{ "source": "<slot>" }` | fire-and-forget, 202 |

### Source slot naming

`snake_case`, describing **where** the click came from — page + position. Registry of slots
in use (extend this list, don't invent ad-hoc names elsewhere):

| Slot | Where | Status |
|------|-------|--------|
| `article_detail_end` | end of an article detail page | wired |
| `subscribe_page` | direct visit to `/subscribe` (no `source`) | fallback |
| `articles_hero` | article list hero | reserved (issue #423) |
| `ticker_page` | stock/ticker page | reserved (issue #423) |

Unrecognized or malformed slots are counted under `unknown` rather than dropped, so a
mis-wired CTA is visible instead of silently lost.

---

## Inspecting sources

Admin analytics surface (dev/staging — prod mounts no `/api/admin/*`):

- **UI:** Admin → Analytics → *Subscription Funnel* card (top sources for views & clicks,
  view→click rate).
- **API:** `GET /api/admin/analytics/subscribe?top=20` (admin Bearer). Returns
  `{ destination, total_views, total_clicks, top_view_sources[], top_click_sources[] }` from
  live Redis counters (no cache).
- **Logs:** every outbound click logs `subscribe outbound click source=<slot> -> <dest>`.

---

## Configuration

`NEWSLETTER_SUBSCRIBE_URL` (backend env / GCP Secret Manager) — the outbound destination.
Defaults to `https://tinboker.substack.com/subscribe`. Config-driven so the destination can
move off Substack later without a code change; the redirect and every CTA read this one value.

---

## Privacy

No PII is collected. Only an anonymous per-`source` counter is incremented — no user id, IP,
email, or cookie is stored by the funnel. Subscriber identity lives entirely on the external
newsletter host.

---

## Adding a new CTA surface

1. Pick a `snake_case` slot and add it to the registry table above.
2. Drop a `<SubscribeCTA source="<slot>" />` (card or `variant="inline"`), **or** link an
   anchor to `subscribeOutboundUrl("<slot>")` for a direct outbound click.
3. That's it — views/clicks show up in the admin funnel card automatically.
