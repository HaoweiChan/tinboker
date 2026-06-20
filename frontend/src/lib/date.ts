/**
 * Taiwanese date formatting — YYYY/MM/DD, the convention used across zh-TW UIs.
 * Use these everywhere a date is shown so the whole app reads consistently
 * (never the en-US M/D/YYYY that `toLocaleDateString()` defaults to).
 */

function toDate(input: string | number | Date | null | undefined): Date | null {
  if (input == null || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026/06/10" (zero-padded). Returns "" for missing/invalid input. */
export function formatDate(input: string | number | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}/${m}/${day}`;
}

/** "2026/06/10 14:30" — date + 24h time. Returns "" for missing/invalid input. */
export function formatDateTime(input: string | number | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return '';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${formatDate(d)} ${hh}:${mm}`;
}

/** "06/10" — compact month/day for dense chart axes. Returns "" for invalid input. */
export function formatMonthDay(input: string | number | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return '';
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${m}/${day}`;
}
