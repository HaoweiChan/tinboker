// Runnable check: node src/lib/insightPaywall.check.ts
import { readFileSync } from 'node:fs'
import { isPaywalledInsight, splitByPaywall, INSIGHT_PAYWALL_DAYS } from './insightPaywall.ts'

const NOW = Date.parse('2026-09-21T12:00:00Z')
const daysAgo = (d: number) => new Date(NOW - d * 86_400_000).toISOString()
const eq = (got: unknown, want: unknown, label: string) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    throw new Error(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
  }
}

eq(INSIGHT_PAYWALL_DAYS, 7, 'window is one week')
eq(isPaywalledInsight(daysAgo(0), NOW), true, 'today is gated')
eq(isPaywalledInsight(daysAgo(6.9), NOW), true, 'just inside the window')
eq(isPaywalledInsight(daysAgo(7.1), NOW), false, 'just outside the window')
eq(isPaywalledInsight(daysAgo(90), NOW), false, 'the archive is free')
// A mention we can't date is free — hiding it would drop it from the crawler body too.
eq(isPaywalledInsight(undefined, NOW), false, 'missing timestamp is free')
eq(isPaywalledInsight('not a date', NOW), false, 'unparseable timestamp is free')

const rows = [
  { id: 'today', podcast_launch_time: daysAgo(0) },
  { id: 'week-old', podcast_launch_time: daysAgo(30) },
  { id: 'edge', podcast_launch_time: daysAgo(7.5) },
  { id: 'undated', podcast_launch_time: null },
]
const { free, gated } = splitByPaywall(rows, NOW)
eq(free.map((r) => r.id), ['week-old', 'edge', 'undated'], 'free side')
eq(gated.map((r) => r.id), ['today'], 'gated side')
eq(free.length + gated.length, rows.length, 'nothing is dropped')
// The Cloudflare function can't import this module (separate bundle, plain JS), so
// it keeps its own copy of the window. Pin them together — a silent drift here means
// the crawler body and the page disagree, which is cloaking in one direction or lost
// indexable text in the other.
const mw = readFileSync(new URL('../../functions/_middleware.js', import.meta.url), 'utf8')
const mwDays = Number(mw.match(/const INSIGHT_PAYWALL_DAYS = (\d+);/)?.[1])
eq(mwDays, INSIGHT_PAYWALL_DAYS, 'functions/_middleware.js window matches')

console.log('insightPaywall: ok')
