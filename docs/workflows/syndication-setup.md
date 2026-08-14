# Syndication setup — 方格子 (vocus) and Substack

Episode summaries are republished to two platforms. The code lives in
`backend/src/services/{vocus,substack}_publisher.py` and
`backend/src/routers/social.py`; this file records the **account-side settings and the
platform behaviours that are not visible from the code** — the things that cost a
round-trip to rediscover.

For the publishing contracts themselves (payload shapes, field names, traps), read the
module docstrings. They are the source of truth and are kept current with what the live
APIs actually accept.

---

## Publishing, in one action

`POST /api/admin/threads/episodes/{id}/syndicate?platforms=vocus,substack` — builds the
shared fields **once** and hands the same values to both publishers. Admin page: the
「兩邊建草稿」 button.

Drafts on both by default. `publish=true` affects **vocus only**; Substack is never
published from here.

| | vocus | Substack |
|---|---|---|
| Draft URL | `vocus.cc/publish-v2/{id}` | `{sub}.substack.com/publish/post/{id}` |
| Publishing | `publish=true`, or the wizard | **Human clicks Publish** |
| Emails on publish | no such thing | only if `should_send_email` — we always send `false` |

### Substack: drafts and published posts are separate records

Editing a draft does **not** change the live post. Every field — body, cover, og tags —
stays at whatever it was when Publish was last clicked. After changing anything on an
already-published post, someone has to hit Update in the editor or the change is invisible
to readers. This has caught us twice: once for `og:image`, once for the body image.

Consequence: get the post right **before** first publish. Nothing after it is automatic.

### From the pipeline, automatically

`pipelines/services/podcast/src/pipeline/steps/syndicate.py` (Step 5f) fires the same
endpoint after a fresh ingest, so a new summary reaches both platforms without anyone
opening the admin page.

| Env var | Effect |
|---|---|
| `SYNDICATE_AUTOPUBLISH` | **Required.** Unset = the step is a no-op and prints where to do it by hand. |
| `SYNDICATE_VOCUS_PUBLISH` | vocus goes public instead of staying a draft. |
| `TINBOKER_PLATFORM_API_URL` + `TINBOKER_SOCIAL_TOKEN` | already needed by the Threads trigger |

**There is no switch that auto-publishes to Substack**, deliberately: publishing there
emails every subscriber and cannot be undone, so it stays a human's click.

The step never fires on reruns or backfills. Unlike the Threads trigger, the platform does
NOT dedupe this — every call creates fresh drafts — so re-processing an old episode would
republish it.

---

## Covers

`GET /api/og/episode/{id}.png` (public, no auth) draws the cover — see
`services/og_image.py`. `.svg` still exists because an early published vocus article
references it.

- **On vocus** the cover is `thumbnailUrl` plus `coverSource: "custom"`.
- **On Substack the first body image IS the cover.** A reference post's `og:image` and its
  first body image are the same asset. So the publisher uploads the PNG via
  `POST /api/v1/image` and prepends it as a `captionedImage` node. Uploading also means a
  published post stops depending on `api.tinboker.com` for its images.

The cover deliberately uses **our own layout with the show's artwork as an illustration**,
never the show's artwork alone — a summary wearing only 股癌's logo reads as 股癌's own
post.

---

## Account settings

Recorded because they are invisible from the repo and easy to get wrong.

### vocus salon — `vocus.cc/salon/tinboker`

| Field | Value | Note |
|---|---|---|
| 名稱 | 聽播客 TinBoker \| AI 財經懶人包 | shown on tag-page cards — the keywords help discovery |
| 自訂網址 | `tinboker` | **cannot be changed once set** |
| 頭像 | `frontend/public/brand/tinboker-square-dark-1080.png` | 1:1, ≥300px |
| 標誌 | 1500×300, transparent, dark ink | the navbar is light; a dark-background logo becomes a black box |
| 封面照片 | 1004×200 | keep everything inside the middle 480px |
| 社群分享圖 | 1200×630 | |
| 分類 | 投資理財 (`5a978e00fd897800016874cc`) | required by the publish wizard; sent by the publisher |

The **salon**, not the personal profile, is what appears on tag pages and above every
article. Every other 股癌-summary writer uses the salon as their publication.

### Substack — `tinboker.substack.com`

| Field | Value | Note |
|---|---|---|
| Publication name | 聽播客 TinBoker | strip the auto-appended `'s Substack` |
| Handle | `@tinboker` | |
| Header image | the same 1500×300 transparent logo | Substack puts it on a **white plate** in both light and dark mode, so dark ink is correct |
| Accent colour | `#9e6c16` | see below |
| Background | None (light) | Substack's emails are always light; a dark site would not match them |

**Accent colour.** Substack uses it for links and buttons, so it must be readable on
white. Brand amber `#fbac23` is **1.90:1** — unusable for text. `#9e6c16` keeps the
brand's hue (38°) and saturation, dropping only lightness, and reaches **4.55:1** (WCAG AA).
Substack's own default `#FF6719` is 2.91:1 and also fails.

---

## Credentials

Both live in GCP Secret Manager (project `gen-lang-client-0901363254`), per
[`../infra-runbook.md`](../infra-runbook.md).

| Secret | Life | Rotation |
|---|---|---|
| `VOCUS_ID_TOKEN` | **7 days** | automatic — the `vocus-token-rotate` scheduled task copies the browser's token daily. vocus silently re-mints while the Google session holds, so this needs no human unless that session lapses. |
| `SUBSTACK_SID` | months | **by hand.** It is httpOnly, so nothing can read it out of the page. |

Taking `SUBSTACK_SID`: DevTools → Application → Cookies → `https://tinboker.substack.com`
→ the row named exactly `substack.sid` on the `.substack.com` domain. A correct value is
~80 characters and begins `s%3A`. **A value beginning `g.` is Google's `SID` cookie**,
which sits a few rows away in the same list and yields a 403 "Not authorized".

`VOCUS_USER_ID`, `VOCUS_SALON_ID`, `SUBSTACK_SUBDOMAIN` and `SUBSTACK_USER_ID` are public
identifiers, not secrets, but live in GSM with the rest for one place to look.
