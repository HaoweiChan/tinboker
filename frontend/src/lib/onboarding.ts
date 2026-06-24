// Onboarding + "what's new" gating — entirely client-side via localStorage.
// ponytail: backend has no new-user flag, so "seen" is tracked per-user in
// localStorage. Anyone who hasn't seen the tutorial gets it once; logging in
// (new user id) re-shows it, which is exactly the "newly registered" case.

// Browser-wide (not per-user) so the tutorial shows at most ONCE per browser.
// Switching login state — anon → register, logout, or a different account on the
// same browser — never re-triggers it. (Cross-device would need a server-side
// flag; deliberately not done — localStorage is enough for launch.)
const SEEN_KEY = 'tb_onboarding_seen';
const VERSION_KEY = 'tb_last_seen_changelog';

export function hasSeenOnboarding(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return true; // storage blocked (private mode) → don't nag
  }
}

export function markOnboardingSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, '1');
  } catch {
    /* ignore */
  }
}

export interface ChangelogEntry {
  version: string;
  date: string;
  items: string[];
}

// Newest first. To announce a release: prepend an entry. Returning users whose
// last-seen version differs from CHANGELOG[0] see it once on next load.
// HOW TO WRITE AN ENTRY (user-friendly, no engineering wording) + when to do it:
//   docs/workflows/deploy-flow.md § "In-app changelog (What's new)".
export const CHANGELOG: ChangelogEntry[] = [
  {
    version: '0.4.7',
    date: '2026-06',
    items: [
      '新增新手導覽，帶你快速認識 TinBoker',
      '個股、話題、集數與文章頁面改為登入後檢視',
      '發佈新版本時會顯示更新內容',
    ],
  },
];

/** The changelog entry to surface now, or null if nothing new to show. */
export function unseenChangelog(): ChangelogEntry | null {
  const latest = CHANGELOG[0];
  if (!latest) return null;
  let last: string | null;
  try {
    last = localStorage.getItem(VERSION_KEY);
  } catch {
    return null;
  }
  if (last === latest.version) return null;
  // First-ever visit: adopt current silently (they get the tutorial instead).
  if (last === null) {
    markChangelogSeen();
    return null;
  }
  return latest;
}

export function markChangelogSeen(): void {
  try {
    const latest = CHANGELOG[0];
    if (latest) localStorage.setItem(VERSION_KEY, latest.version);
  } catch {
    /* ignore */
  }
}
