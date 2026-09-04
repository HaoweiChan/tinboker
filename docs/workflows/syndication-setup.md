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

Drafts on both by default. `publish` covers vocus and `publish_substack` covers Substack —
separate switches, so turning one on never quietly turns the other on.

| | vocus | Substack |
|---|---|---|
| Draft URL | `vocus.cc/publish-v2/{id}` | `{sub}.substack.com/publish/post/{id}` |
| Publishing | `publish=true`, or the wizard | `publish_substack=true`, or the editor |
| Emails on publish | no such thing | **never from here** — `send_email` is hard-wired `false` |

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
| `SYNDICATE_SUBSTACK_PUBLISH` | Substack goes public **on the web**. Cannot email — see below. |
| `SYNDICATE_MAX_AGE_DAYS` | Only syndicate episodes published within this many days. Default **7**; `0` disables the gate for a deliberate backfill. |
| `TINBOKER_PLATFORM_API_URL` + `TINBOKER_SOCIAL_TOKEN` | already needed by the Threads trigger |
| `TINBOKER_ADMIN_API_URL` | Where `/api/admin/*` calls go. **Must not be production** — see below. |

**Production mounts no admin routers.** `backend/src/main.py` guards every `/api/admin/*`
router with `if not settings.is_production`, so `api.tinboker.com` answers 404 for all of
them on purpose — the admin surface is not exposed on the public host. Any pipeline
trigger aimed there fails, which is why `TINBOKER_ADMIN_API_URL` points at the staging
backend. It points at staging's **direct origin** (`http://127.0.0.1:8002`, same host),
not `staging-api.tinboker.com`: Cloudflare's 100s edge timeout 524'd the Threads
catch-up publish while the origin kept posting, so the run log reported failures for
publishes that actually went live. All environments share one database, so staging does
exactly the same work to the same data. The pinned value lives in the systemd units.

**Two guards, and they answer different questions.**

*Has this episode already gone out?* — the shared `social_posts` ledger
(`services/social_ledger.py`), the same one Threads and Facebook use. Every syndication
call claims `(platform, episode_id)` before publishing and records the article id after,
so a re-ingest, an overlapping trigger, or a *different environment* is refused. That
last one is not hypothetical: dev, staging and production share this Postgres **and** the
vocus/Substack credentials, and the three duplicate vocus articles from Aug 2026 differ
only in whether the cover URL says `api.` or `staging-api.` — two environments published
the same episode minutes apart.

*Is it new enough to be worth sending?* — `SYNDICATE_MAX_AGE_DAYS`. The ledger cannot
help here, because the back catalogue is all first-time syndications: ingest pulls the
last 10 episodes per show and walks backwards, so ~50 of the ~60 episodes it touches
each day are years old. Unchecked that is ~44 posts a day. (Threads has had the same
recency guard from the start — `settings.threads_max_age_days`, 4 days.)

An episode with **no** resolvable publish time is skipped, not published: a wrong skip
costs one article the admin page can still stage by hand, a wrong publish is public.

**Nothing here can email subscribers.** `SubstackClient.publish_draft` sends
`send_email: false` and takes no parameter that could change it, so no combination of
flags or query params sends a newsletter. That is deliberate: a web-only post can be
taken down, a newsletter cannot be recalled, so enabling email should require a code
change and a review rather than an env var someone typo'd.

Verified live before shipping: publishing a throwaway draft this way returned
`is_published: true` with `email_sent_at: null`.

The ingest itself runs on `tinboker-podcast-ingest.timer` (four times a day,
`services/podcast/deploy/`), so a new episode goes feed → summary → both platforms with
nobody involved. The runner passes `--fill-limit`, which is what keeps a tick that finds
nothing from re-transcribing episodes already done — an expensive way to do nothing.

The step never fires on reruns or backfills. Unlike the Threads trigger, the platform does
NOT dedupe this — every call creates fresh drafts — so re-processing an old episode would
republish it.

---

## Reading stats

Both platforms are read back as well as written to, so syndication is no longer
write-only. `backend/src/services/{vocus,substack}_insights_service.py` read the
counters, two admin endpoints serve them, and the Analytics page renders a panel each.

| Endpoint | Returns |
|---|---|
| `GET /api/admin/vocus/insights?posts=10` | lifetime reads/likes/bookmarks + article count, and the newest articles with their own counters |
| `GET /api/admin/substack/insights?posts=10` | lifetime views/reactions/comments + post count, and the newest posts |

Both reuse the publishers' clients, so the vocus 7-day token and the `substack.sid`
cookie are maintained in exactly one place. Both always return 200 and report
`available: false` with a `detail` when a credential is missing or expired.

**The counts are lifetime, not windowed.** Neither platform exposes history — each
article carries a running counter — so "reads this week" is not answerable from one
call. That is what the daily snapshot is for: `POST /api/admin/analytics/snapshot`
(the `Snapshot Social Metrics` workflow, 04:00 UTC) now also records `vocus_reads`,
`vocus_articles`, `substack_reads` and `substack_posts`, and the growth chart draws
them. **A day's reading is the difference between two rows.**

### The field names are ranked guesses, and the code says so

Neither API documents which key holds the read count, and neither could be captured
while this was written. So each count is resolved against a ranked candidate list
(`READ_KEYS` / `VIEW_KEYS`, plus `LIST_ENDPOINTS` for Substack's published-post list),
and **the resolution is reported with the number**:

- Working: the response carries `field_map` (`{"reads": "readCount"}`) and, for
  Substack, the `source` endpoint that answered. Both show up in the Analytics page's
  Tracking Configuration list.
- Not working: articles were found but no candidate key matched → `available: false`
  plus `sample_keys`, the field names the platform actually sent, rendered under the
  panel.

That distinction is the point. A read counter that silently reports **0** is worse than
none — it reads as "nobody opened it" and invites the conclusion that syndication is
not working — so a mapping miss is never allowed to render as a zero, in the panel or
in a snapshot row (the snapshot writes only when `available` is true).

**First run against live credentials is a verification step, not a smoke test.** Open
`/admin/analytics`: if both panels show numbers, note the `field_map` values and pin
them at the head of each candidate list. If a panel shows `Fields returned: …`, the
right key is in that list — move it to the front of `READ_KEYS`/`VIEW_KEYS` and delete
the guesses. Paging (`page` on vocus, `offset` on Substack) is unverified too, so both
readers dedupe by id across pages: an ignored paging parameter stops the walk instead
of multiplying the total.

Scope caps: 200 articles/posts per read (`MAX_ARTICLES` / `MAX_POSTS`), reported as
`truncated: true` rather than a quietly low number.

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
