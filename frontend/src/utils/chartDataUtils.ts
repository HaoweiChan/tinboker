import type { ChartDataPoint, TimeframeOption } from '@/services/types';


export interface OHLCData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface LineData {
  time: number;
  value: number;
}


export function convertToOHLC(data: ChartDataPoint[]): OHLCData[] {
  if (data.length === 0) return [];

  const ohlcData: OHLCData[] = [];
  const dayMs = 24 * 60 * 60 * 1000;

  // Check if data already has OHLCV structure
  const hasOHLCV = data[0]?.open !== undefined && 
                   data[0]?.high !== undefined && 
                   data[0]?.low !== undefined && 
                   data[0]?.close !== undefined;

  if (hasOHLCV) {
    // Use existing OHLCV data directly
    for (let i = 0; i < data.length; i++) {
      const point = data[i];
      const dayStart = Math.floor(point.timestamp / dayMs) * dayMs;
      const dayStartSeconds = Math.floor(dayStart / 1000);

      if (point.open !== undefined && point.high !== undefined && 
          point.low !== undefined && point.close !== undefined) {
        // Check if we already have data for this day
        const existingIndex = ohlcData.findIndex(d => d.time === dayStartSeconds);
        
        if (existingIndex >= 0) {
          // Update existing day's data with max/min values
          const existing = ohlcData[existingIndex];
          existing.high = Math.max(existing.high, point.high);
          existing.low = Math.min(existing.low, point.low);
          existing.close = point.close; // Use latest close
        } else {
          // Add new day
          ohlcData.push({
            time: dayStartSeconds,
            open: point.open,
            high: point.high,
            low: point.low,
            close: point.close,
          });
        }
      }
    }
  } else {
    // Fallback: generate OHLC from price data (legacy behavior)
    for (let i = 0; i < data.length; i++) {
      const point = data[i];
      const dayStart = Math.floor(point.timestamp / dayMs) * dayMs;
      const dayStartSeconds = Math.floor(dayStart / 1000);

      const open = point.price;
      let high = point.price;
      let low = point.price;
      let close = point.price;

      let j = i;
      while (j < data.length) {
        const nextPoint = data[j];
        const nextDayStart = Math.floor(nextPoint.timestamp / dayMs) * dayMs;

        if (nextDayStart !== dayStart) break;

        high = Math.max(high, nextPoint.price);
        low = Math.min(low, nextPoint.price);
        close = nextPoint.price;
        j++;
      }

      if (ohlcData.length === 0 || ohlcData[ohlcData.length - 1].time !== dayStartSeconds) {
        ohlcData.push({
          time: dayStartSeconds,
          open,
          high,
          low,
          close,
        });
      } else {
        const last = ohlcData[ohlcData.length - 1];
        last.high = Math.max(last.high, high);
        last.low = Math.min(last.low, low);
        last.close = close;
      }

      i = j - 1;
    }
  }

  return ohlcData;
}


export function filterDataByTimeframe(data: ChartDataPoint[], timeframe: TimeframeOption): ChartDataPoint[] {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const hourMs = 60 * 60 * 1000;

  let startDate: number;

  switch (timeframe) {
    case '1H':
      startDate = now - hourMs;
      break;
    case '1D':
      startDate = now - dayMs;
      break;
    case '1W':
      startDate = now - (7 * dayMs);
      break;
    case '1M':
      startDate = now - (30 * dayMs);
      break;
    case '3M':
      startDate = now - (90 * dayMs);
      break;
    case '6M':
      startDate = now - (180 * dayMs);
      break;
    case '1Y':
      startDate = now - (365 * dayMs);
      break;
    case 'YTD': {
      const yearStart = new Date(new Date().getFullYear(), 0, 1);
      startDate = yearStart.getTime();
      break;
    }
    case 'ALL':
      return data;
    default:
      startDate = now - (180 * dayMs);
  }

  return data.filter(d => d.timestamp >= startDate);
}

export function convertToLineData(data: ChartDataPoint[]): LineData[] {
  if (data.length === 0) return [];

  const lineData: LineData[] = [];
  const dayMs = 24 * 60 * 60 * 1000;

  for (const point of data) {
    const dayStart = Math.floor(point.timestamp / dayMs) * dayMs;
    const dayStartSeconds = Math.floor(dayStart / 1000);

    // Use close price if available, otherwise use price
    const value = point.close !== undefined ? point.close : point.price;

    // Check if we already have data for this day
    const existingIndex = lineData.findIndex(d => d.time === dayStartSeconds);
    
    if (existingIndex >= 0) {
      // Update with latest value for this day
      lineData[existingIndex].value = value;
    } else {
      // Add new day
      lineData.push({
        time: dayStartSeconds,
        value: value,
      });
    }
  }

  return lineData;
}


/**
 * The price on a lightweight-charts point: `value` on line/area data, `close` on
 * bars. Whitespace points carry neither and give undefined.
 */
export function pointPrice(point: object): number | undefined {
  const p = point as { value?: number; close?: number };
  return p.value || p.close;
}
