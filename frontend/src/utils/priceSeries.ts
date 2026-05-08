// time can be string (YYYY-MM-DD for daily) or number (Unix timestamp in seconds for minute-level)
export interface PricePoint {
  time: string | number;
  value: number;
}
