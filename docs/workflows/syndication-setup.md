# Syndication setup — 方格子 (vocus)

Episode summaries are republished to 方格子. (Substack was dropped in October 2026:
the account was closed after the views stayed negligible, and its code was removed.)
The code lives in `backend/src/services/vocus_publisher.py` and
`backend/src/routers/social.py`; this file records the **account-side settings and the
platform behaviours that are not visible from the code** — the things that cost a
round-trip to rediscover.

For the publishing contracts themselves (payload shapes, field names, traps), read the
module docstrings. They are the source of truth and are kept current with what the live
APIs actually accept.

---

## Publishing, in one action

`POST /api/admin/threads/episodes/{id}/syndicate?platforms=vocus` — builds the shared
fields and hands them to the vocus publisher. A draft by default; `publish=true` makes
it public. The admin Social page's 「發佈到方格子」 button calls the vocus publisher
directly.

### From the pipeline, automatically

`pipelines/services/podcast/src/pipeline/steps/syndicate.py` (Step 5f) fires the same
endpoint after a fresh ingest, so a new summary reaches vocus without anyone
opening the admin page.

| Env var | Effect |
|---|---|
| `SYNDICATE_AUTOPUBLISH` | **Required.** Unset = the step is a no-op and prints where to do it by hand. |
| `SYNDICATE_VOCUS_PUBLISH` | vocus goes public instead of staying a draft. |
| `SYNDICATE_MAX_AGE_DAYS` | Only syndicate episodes published within this many days. Default **7**; `0` disables the gate for a deliberate backfill. |

> **Since 2026-09-13 the backend refuses per-episode syndication by default.** The pipeline
> still fires Step 5f, but `POST /api/admin/threads/episodes/{id}/syndicate` answers
> `episode_syndication_disabled` for every platform not listed in the backend's
> `EPISODE_SYNDICATION_PLATFORMS` (default empty). What goes to vocus instead is the nightly
> **每日一集** (`backend/src/services/daily_pick.py`): at most `DAILY_PICK_LIMIT` (1) episode
> summary a day, chosen by show priority (`DAILY_PICK_SHOWS`, first wins) and then by how
> many ticker observations the episode produced. It runs from the backend where
> `DAILY_PICK_AUTOPUBLISH=true` (staging) at 20:40 Asia/Taipei through the same per-episode
> ledger; see tonight's choice with `GET /api/admin/daily-pick/{day}` and re-run with
> `POST /api/admin/daily-pick/{day}/publish-vocus`.
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
vocus credentials, and the three duplicate vocus articles from Aug 2026 differ
only in whether the cover URL says `api.` or `staging-api.` — two environments published
the same episode minutes apart.

*Is it new enough to be worth sending?* — `SYNDICATE_MAX_AGE_DAYS`. The ledger cannot
help here, because the back catalogue is all first-time syndications: ingest pulls the
last 10 episodes per show and walks backwards, so ~50 of the ~60 episodes it touches
each day are years old. Unchecked that is ~44 posts a day. (Threads has had the same
recency guard from the start — `settings.threads_max_age_days`, 4 days.)

An episode with **no** resolvable publish time is skipped, not published: a wrong skip
costs one article the admin page can still stage by hand, a wrong publish is public.

The ingest itself runs on `tinboker-podcast-ingest.timer` (four times a day,
`services/podcast/deploy/`), so a new episode goes feed → summary → vocus with
nobody involved. The runner passes `--fill-limit`, which is what keeps a tick that finds
nothing from re-transcribing episodes already done — an expensive way to do nothing.

The step never fires on reruns or backfills. Unlike the Threads trigger, the platform does
NOT dedupe this — every call creates fresh drafts — so re-processing an old episode would
republish it.

---

## The paid weekly (salon members only)

`GET /api/admin/weekly/{week}/paid` renders the member issue from data the site
already computes — the public weekly rollup, the four-week-old mentions whose 20-day
forward return has resolved (per-show hit rate, best/worst calls), and the anomaly
screener's top ten cross-referenced with this week's episode mentions
(`services/paid_weekly.py`). `POST /api/admin/weekly/{week}/publish-vocus` sends it
through `vocus_publisher.publish_markdown(..., paid=True)`; `dry_run=true` and
`as_draft=true` are the defaults, so the first real run is a draft you open in the
wizard. The ledger key is `weekly:{week}` — one article per week, ever, across
environments.

Two things the code cannot do for you:

- **The salon needs a paid plan first.** `setIsPay` only puts an article behind a wall
  that exists; configure 付費方案 in the vocus salon dashboard before the first publish.
- **`paid_verified` in the result is the read-back, not the request.** `None` means vocus
  did not echo the flag under any key in `vocus_publisher.PAID_KEYS`; the response then
  carries `paid_readback_keys` — pin the right one at the head of the list, same
  discipline as `READ_KEYS` below. `False` means the article went out free: fix the
  salon plan, then delete and republish (the ledger row must be released by hand).

## Reading stats

vocus is read back as well as written to, so syndication is not write-only.
`backend/src/services/vocus_insights_service.py` reads the counters, an admin endpoint
serves them, and the Analytics page renders a panel.

| Endpoint | Returns |
|---|---|
| `GET /api/admin/vocus/insights?posts=10` | lifetime reads/likes/bookmarks + article count, and the newest articles with their own counters |

The vocus reader is **unauthenticated**: published articles are public, and the list
endpoint answers with no `Authorization` header (verified 2026-09-11; only writes need
the 7-day token). It needs `VOCUS_USER_ID` and a browser User-Agent, nothing else, so an
expired token no longer blanks the reading panel — that gating is what left
`analytics_snapshots.vocus_reads` NULL for weeks. It always returns 200 and reports
`available: false` with a `detail` when it cannot read.

**The counts are lifetime, not windowed.** vocus exposes no history — each
article carries a running counter — so "reads this week" is not answerable from one
call. That is what the daily snapshot is for: `POST /api/admin/analytics/snapshot`
(the `Snapshot Social Metrics` workflow, 04:00 UTC) now also records `vocus_reads`
and `vocus_articles`, and the growth chart draws them. (The `substack_reads` /
`substack_posts` columns still exist on `analytics_snapshots` with their history, but
nothing writes or reads them.) **A day's reading is the difference between two rows.**

### The field names are ranked guesses, and the code says so

vocus does not document which key holds the read count. Its published list was
captured live 2026-09-11: each article carries `pageview` (what vocus shows as 瀏覽 —
this is `reads`), `readCount` (the deeper "read" metric, carried as `read_count`),
`likeCount`, `collectCount`. Each count is resolved against
a ranked candidate list (`READ_KEYS`), and **the resolution is reported with the number**:

- Working: the response carries `field_map` (`{"reads": "pageview"}`), which shows up
  in the Analytics page's Tracking Configuration list.
- Not working: articles were found but no candidate key matched → `available: false`
  plus `sample_keys`, the field names the platform actually sent, rendered under the
  panel.

That distinction is the point. A read counter that silently reports **0** is worse than
none — it reads as "nobody opened it" and invites the conclusion that syndication is
not working — so a mapping miss is never allowed to render as a zero, in the panel or
in a snapshot row (the snapshot writes only when `available` is true).

**First run against live credentials is a verification step, not a smoke test.** Open
`/admin/analytics`: if the panel shows numbers, note the `field_map` values and pin
them at the head of the candidate list. If the panel shows `Fields returned: …`, the
right key is in that list — move it to the front of `READ_KEYS` and delete
the guesses. Paging (`page`) is unverified too, so the
reader dedupes by id across pages: an ignored paging parameter stops the walk instead
of multiplying the total.

Scope cap: 200 articles per read (`MAX_ARTICLES`), reported as
`truncated: true` rather than a quietly low number.

---

## Covers

`GET /api/og/episode/{id}.png` (public, no auth) draws the cover — see
`services/og_image.py`. `.svg` still exists because an early published vocus article
references it.

The cover is vocus's `thumbnailUrl` plus `coverSource: "custom"`.
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

---

## Credentials

The token lives in GCP Secret Manager (project `gen-lang-client-0901363254`), per
[`../infra-runbook.md`](../infra-runbook.md).

| Secret | Life | Rotation |
|---|---|---|
| `VOCUS_ID_TOKEN` | **7 days** | automatic — the `vocus-token-rotate` scheduled task copies the browser's token daily. vocus silently re-mints while the Google session holds, so this needs no human unless that session lapses. |

`VOCUS_USER_ID` and `VOCUS_SALON_ID` are public identifiers, not secrets, but live in GSM with the rest for one place to look.
