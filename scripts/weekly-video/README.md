# Weekly video + Threads post

One 1080×1350 video and one Threads thread per ISO week, both built from
`GET /api/weekly/{week}`. Nothing here posts anything — publishing is the existing
admin promo flow, by hand.

## Why this is a local script and not a service

Rendering needs headless Chrome and ffmpeg. Neither is on the VPS, and installing both
so a container can make one video a week is a worse trade than running four commands on
a laptop. If the weekly ever goes daily, revisit.

## 1. Video

```bash
node build.mjs 2026-W36                  # → out/tinboker-weekly-2026-W36.mp4 (22s, silent)
./add_audio.sh out/tinboker-weekly-2026-W36.mp4          # synthesised bed
./add_audio.sh out/tinboker-weekly-2026-W36.mp4 track.mp3   # or your own licensed track
```

`API` (default `https://dev-api.tinboker.com`), `FPS` (20), `OUT_DIR` are env overrides.

- `weekly.html` — the five scenes. `LEN` is the one place scene timing lives; every
  animation cue derives from it.
- `synth.py` — the BGM. 120 BPM, one bar = 2s, so every scene cut lands on a downbeat.
  It asserts its drum hits against `weekly.html`'s `LEN` and fails if the two drift.
- `build.mjs` — fetches the rollup, drives Chrome frame-by-frame over CDP, calls ffmpeg.

**`flips` comes from the backend** (`routers/weekly.py:flip_rows`), never from this
script. The Threads copy reads the same field, so the video and the post always name the
same tickers. A backend without that field makes `build.mjs` fail loudly rather than
quietly disagree with the post.

## 2. Copy

```bash
cd ../../pipelines
uv run --package tinboker-podcast python -m podcast.weekly_copy 2026-W36
```

Needs `OPENROUTER_API_KEY` + `PIPELINE_LLM_MODEL`. Prints
`{post, comments: [...]}`; the last comment is always the site link. Voice rules live in
`content_builder/prompts/weekly_copy_writer.yaml` and mirror the `threads-writer` skill —
keep the two in sync.

Read it before publishing. The prompt forbids inventing numbers, but "forbids" is not
"cannot": every figure in the draft should be findable in the rollup.

## 3. Publish

No new endpoint — the promo flow already does this:

1. Admin → 社群 → PromoComposer (dev or staging; admin routes are not mounted in prod).
2. Upload the mp4 (`POST /api/admin/promo/media`, ≤200 MB — ours is ~1.5 MB).
3. Paste the post text and the comments, 預覽 first (`dry_run` defaults to true).
4. 發佈, or set a datetime and 排程發佈.

Idempotency: **there is none on the promo path**. `social_posts` (the ledger that stops
an episode being posted twice) is only wired into the episode publishers. Publishing the
same week twice will publish it twice — check 已發佈 before you press it.
