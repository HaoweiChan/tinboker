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
  /** Gating key only — bump it (vs the previous entry) to make returning users see
   *  this entry once. It is NOT shown to users: the popup badge displays the live
   *  build version (VITE_RELEASE_VERSION, the git tag), so it can't drift from the
   *  deployed release. Just keep it unique + newer than the last entry. */
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
    version: '0.6.3',
    date: '2026-06',
    items: [
      '「題材探索」氣泡圖全新改版：支援 1/7/30/90 天時間區間切換與互動提示，並以最新熱度指標排序，尋找熱門題材更直覺。',
      '新增收錄熱門 Podcast 節目「兆華與股惑仔」與「韭菜畢業班」，並修復部分節目的 Spotify 連結與封面顯示。',
      '優化社群分享字卡：封面新增單集標題副標題，並修復了字卡生成與文字重疊問題。',
    ],
  },
  {
    version: '0.6.0',
    date: '2026-06',
    items: [
      '有新集數或新聞時主動通知你，不錯過任何更新',
      '個人檔案改版：追蹤的話題分成「產業」與「標籤」，自選股顯示提及次數與看多／看空情緒',
      '收藏的集數依最新時間排序，也能編輯顯示名稱與大頭貼',
      '播放器標出可略過的片段（贊助、閒聊），直接聽重點',
      '歡迎畫面就能設定顯示偏好，第一次使用更順手',
    ],
  },
  {
    version: '0.5.5',
    date: '2026-06',
    items: [
      '新增新手導覽，第一次使用也能快速上手',
      '個股、話題、集數與文章頁面登入後即可檢視，並能追蹤自選與訂閱',
      '返回首頁時內容立即顯示，不再閃爍重新載入',
      '集數摘要在電腦版的字級與排版更好讀',
      '改版後會用更新公告告訴你有哪些新功能',
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
