import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { pointPrice } from '@/utils/chartDataUtils';


interface UseGlobalEventLineOptions {
  charts: (IChartApi | null)[];
  series: (ISeriesApi<'Area'> | null)[];
  eventDate: number | null;
  enabled?: boolean;
}


/**
 * Hook to synchronize crosshair position across all charts using setCrosshairPosition API.
 * Based on: https://tradingview.github.io/lightweight-charts/tutorials/how_to/set-crosshair-position
 */
export function useGlobalEventLine({ 
  charts, 
  series, 
  eventDate, 
  enabled = true 
}: UseGlobalEventLineOptions): void {
  const chartsRef = useRef(charts);
  const seriesRef = useRef(series);
  const isMountedRef = useRef(true);
  
  // Keep refs up to date - this must be a separate effect to maintain hook order
  useEffect(() => {
    chartsRef.current = charts;
    seriesRef.current = series;
  }, [charts, series]);

  // Track mount status
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled || !eventDate || charts.length === 0 || series.length === 0) {
      // Don't clear crosshair in cleanup - let charts handle their own cleanup
      // Calling clearCrosshairPosition can trigger async repaints on disposed charts
      return;
    }

    const validCharts = chartsRef.current.filter((chart): chart is IChartApi => chart !== null);
    const validSeries = seriesRef.current.filter((s): s is ISeriesApi<'Area'> => s !== null);
    
    if (validCharts.length === 0 || validSeries.length === 0) {
      return;
    }

    // Convert event date to seconds (Lightweight Charts expects Unix timestamp in seconds)
    const eventDateSeconds = Math.floor(eventDate / 1000);

    // Set crosshair position on all charts
    validCharts.forEach((chart, index) => {
      const seriesInstance = validSeries[index];
      if (!seriesInstance) return;

      try {
        // Get data from the series
        const data = seriesInstance.data();
        if (!data || data.length === 0) return;

        // Find the closest data point to the event date
        let closestPoint = data[0];
        let minDiff = Math.abs((closestPoint.time as number) - eventDateSeconds);

        for (const point of data) {
          const diff = Math.abs((point.time as number) - eventDateSeconds);
          if (diff < minDiff) {
            minDiff = diff;
            closestPoint = point;
          }
        }

        // Extract price from the closest point (area/line data has 'value' property)
        const price = pointPrice(closestPoint);
        const time = closestPoint.time;

        if (price !== undefined && price !== null && Number.isFinite(price)) {
          chart.setCrosshairPosition(price, time, seriesInstance);
        }
      } catch {
        // Ignore all errors including disposed chart errors
        // The chart might have been disposed
      }
    });

    // No cleanup needed - charts will handle their own cleanup when disposed
    // Calling clearCrosshairPosition in cleanup can trigger async repaints on disposed charts
    return () => {
      // Intentionally empty - don't call clearCrosshairPosition here
      // The charts will clear their crosshairs automatically when disposed
    };
  }, [charts, series, eventDate, enabled]);
}

