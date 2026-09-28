/** Keep missing numeric data last in either direction; zero remains a real value. */
export function compareOptionalNumbers(
  a: number | null | undefined,
  b: number | null | undefined,
  direction: 'asc' | 'desc',
): number {
  if (a == null) return b == null ? 0 : 1;
  if (b == null) return -1;
  return direction === 'asc' ? a - b : b - a;
}
