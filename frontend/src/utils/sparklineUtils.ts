/**
 * Format percentage for display
 * @param pct - Percentage as decimal (e.g., 0.0344)
 * @returns Formatted string (e.g., "+3.44%")
 */
export const formatPercentage = (pct: number): string => {
  const sign = pct > 0 ? '+' : '';
  return `${sign}${(pct * 100).toFixed(2)}%`;
};


/**
 * Format price for display
 * @param price - Price value
 * @returns Formatted string (e.g., "$242.84")
 */
export const formatPrice = (price: number): string => {
  return `$${price.toFixed(2)}`;
};
