// Checks the saved-episode bookmark repair rules — which stored ids get rewritten to the
// episode's current id, which get dropped, and which must be left strictly alone. The
// destructive half of that ("otherwise remove them") has no UI to catch a mistake, so the
// decision table is pinned here.
//
//   npm run validate:bookmarks
//
import {
  bookmarkIdToToggleArgs,
  episodeIdCandidates,
  planBookmarkRepair,
  type BookmarkResolution,
  type BookmarkTarget,
} from '../src/lib/bookmarkRepair';

let failures = 0;
function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  const ok = a === e;
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
  if (!ok) console.log(`      expected ${e}\n      actual   ${a}`);
}

const ep = (podcast_name: string, id: string): BookmarkTarget => ({ podcast_name, id });
const ok = (e: BookmarkTarget): BookmarkResolution => ({ kind: 'ok', episode: e });
const missing = (): BookmarkResolution => ({ kind: 'missing' });
const failed = (): BookmarkResolution => ({ kind: 'failed' });

// --- candidate derivation ------------------------------------------------------
check('CJK show: doc id is last two segments',
  episodeIdCandidates('財女珍妮_547e2c56_03966ac0edb46ccc')[0], '547e2c56_03966ac0edb46ccc');
check('ASCII-prefixed show',
  episodeIdCandidates('Gooaye 股癌_Gooaye_859cc52dc1eaf2f0')[0], 'Gooaye_859cc52dc1eaf2f0');
check('legacy bare doc id is its own first candidate',
  episodeIdCandidates('547e2c56_03966ac0edb46ccc')[0], '547e2c56_03966ac0edb46ccc');
check('show name containing an underscore',
  episodeIdCandidates('My_Show_MyShow_abc123def4567890')[0], 'MyShow_abc123def4567890');
check('episode-number id shape',
  episodeIdCandidates('財女珍妮_547e2c56_ep924')[0], '547e2c56_ep924');
check('underscored episode prefix falls to the second candidate',
  episodeIdCandidates('Show_A_B_abc123def4567890')[1], 'A_B_abc123def4567890');

// --- toggle-endpoint round trip ------------------------------------------------
for (const id of [
  '財女珍妮_547e2c56_03966ac0edb46ccc',
  'Gooaye 股癌_Gooaye_859cc52dc1eaf2f0',
  '547e2c56_03966ac0edb46ccc',
]) {
  const args = bookmarkIdToToggleArgs(id)!;
  check(`toggle args rebuild "${id}" exactly`, `${args.podcastName}_${args.episodeId}`, id);
}
check('an id with no interior underscore is not expressible', bookmarkIdToToggleArgs('nounderscore'), null);
check('a leading underscore is not expressible', bookmarkIdToToggleArgs('_abc'), null);

// --- repair planning -----------------------------------------------------------
const renamed = ep('財女珍妮', '547e2c56_03966ac0edb46ccc');
check('renamed show: rewrite to the current id',
  planBookmarkRepair(['財女 Jenny_547e2c56_03966ac0edb46ccc'], new Map([['財女 Jenny_547e2c56_03966ac0edb46ccc', ok(renamed)]])),
  { migrate: [{ from: '財女 Jenny_547e2c56_03966ac0edb46ccc', to: '財女珍妮_547e2c56_03966ac0edb46ccc' }], gone: [], duplicate: [] });

check('already canonical: nothing to do',
  planBookmarkRepair(['財女珍妮_547e2c56_03966ac0edb46ccc'], new Map([['財女珍妮_547e2c56_03966ac0edb46ccc', ok(renamed)]])),
  { migrate: [], gone: [], duplicate: [] });

check('confirmed 404: drop it',
  planBookmarkRepair(['財女珍妮_deadbeef_0000000000000000'], new Map([['財女珍妮_deadbeef_0000000000000000', missing()]])),
  { migrate: [], gone: ['財女珍妮_deadbeef_0000000000000000'], duplicate: [] });

check('fetch failure: leave it completely alone',
  planBookmarkRepair(['財女珍妮_deadbeef_0000000000000000'], new Map([['財女珍妮_deadbeef_0000000000000000', failed()]])),
  { migrate: [], gone: [], duplicate: [] });

check('unresolved id (no entry) is left alone',
  planBookmarkRepair(['財女珍妮_deadbeef_0000000000000000'], new Map()),
  { migrate: [], gone: [], duplicate: [] });

check('stale id whose canonical is already saved: de-duplicate, do not migrate',
  planBookmarkRepair(
    ['財女 Jenny_547e2c56_03966ac0edb46ccc', '財女珍妮_547e2c56_03966ac0edb46ccc'],
    new Map([
      ['財女 Jenny_547e2c56_03966ac0edb46ccc', ok(renamed)],
      ['財女珍妮_547e2c56_03966ac0edb46ccc', ok(renamed)],
    ]),
  ),
  { migrate: [], gone: [], duplicate: ['財女 Jenny_547e2c56_03966ac0edb46ccc'] });

check('two stale ids for one episode: migrate once, drop the other',
  planBookmarkRepair(
    ['A_547e2c56_03966ac0edb46ccc', 'B_547e2c56_03966ac0edb46ccc'],
    new Map([
      ['A_547e2c56_03966ac0edb46ccc', ok(renamed)],
      ['B_547e2c56_03966ac0edb46ccc', ok(renamed)],
    ]),
  ),
  { migrate: [{ from: 'A_547e2c56_03966ac0edb46ccc', to: '財女珍妮_547e2c56_03966ac0edb46ccc' }], gone: [], duplicate: ['B_547e2c56_03966ac0edb46ccc'] });

check('already-repaired ids are skipped',
  planBookmarkRepair(['x_1_2'], new Map([['x_1_2', missing()]]), new Set(['x_1_2'])),
  { migrate: [], gone: [], duplicate: [] });

const mixed = ['ok_547e2c56_aaaaaaaaaaaaaaaa', 'stale_547e2c56_03966ac0edb46ccc', 'dead_547e2c56_bbbbbbbbbbbbbbbb', 'flaky_547e2c56_cccccccccccccccc'];
check('mixed list: each id judged on its own',
  planBookmarkRepair(mixed, new Map<string, BookmarkResolution>([
    ['ok_547e2c56_aaaaaaaaaaaaaaaa', ok(ep('ok', '547e2c56_aaaaaaaaaaaaaaaa'))],
    ['stale_547e2c56_03966ac0edb46ccc', ok(renamed)],
    ['dead_547e2c56_bbbbbbbbbbbbbbbb', missing()],
    ['flaky_547e2c56_cccccccccccccccc', failed()],
  ])),
  { migrate: [{ from: 'stale_547e2c56_03966ac0edb46ccc', to: '財女珍妮_547e2c56_03966ac0edb46ccc' }], gone: ['dead_547e2c56_bbbbbbbbbbbbbbbb'], duplicate: [] });

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
