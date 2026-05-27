// Curated 12-color palette optimized for dark mode with good contrast against white text
const AVATAR_COLORS = [
  '#2563EB', // blue-600
  '#059669', // emerald-600
  '#4F46E5', // indigo-600
  '#7C3AED', // violet-600
  '#E11D48', // rose-600
  '#D97706', // amber-600
  '#0891B2', // cyan-600
  '#C026D3', // fuchsia-600
  '#DC2626', // red-600
  '#16A34A', // green-600
  '#EA580C', // orange-600
  '#0284C7', // sky-600
];

/**
 * Deterministic hex background color for a ticker/name string.
 * The same input always returns the same color.
 */
export function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash += name.charCodeAt(i);
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

