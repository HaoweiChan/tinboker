import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';


interface UseSynchronizedChartsOptions {
  charts: (IChartApi | null)[];
  enabled?: boolean;
}


export function useSynchronizedCharts({ charts, enabled = true }: UseSynchronizedChartsOptions): void {
  const isSyncingRef = useRef(false);
  const throttleTimeoutRef = useRef<number | null>(null);
  const chartsRef = useRef<(IChartApi | null)[]>([]);

  useEffect(() => {
    chartsRef.current = charts;
  }, [charts]);

  useEffect(() => {
    if (!enabled || charts.length === 0) return;

    const validCharts = charts.filter((chart): chart is IChartApi => chart !== null);
    if (validCharts.length === 0) return;

    const unsubscribeFunctions: (() => void)[] = [];

    validCharts.forEach((chart, index) => {
      try {
        const unsubscribe = chart.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
          if (isSyncingRef.current || !timeRange || !timeRange.from || !timeRange.to) return;

          if (throttleTimeoutRef.current !== null) {
            clearTimeout(throttleTimeoutRef.current);
          }

          throttleTimeoutRef.current = window.setTimeout(() => {
            isSyncingRef.current = true;

            const currentCharts = chartsRef.current.filter((c): c is IChartApi => c !== null);
            currentCharts.forEach((otherChart, otherIndex) => {
              if (otherIndex !== index && otherChart !== null) {
                try {
                  // Check if chart is still valid before calling methods
                  const timeScale = otherChart.timeScale();
                  if (timeScale) {
                    timeScale.setVisibleRange(timeRange);
                  }
                } catch {
                  // Silently ignore all errors including disposed chart errors
                  // The chart might have been disposed during the async operation
                }
              }
            });

            setTimeout(() => {
              isSyncingRef.current = false;
            }, 100);
          }, 50);
        });

        if (typeof unsubscribe === 'function') {
          unsubscribeFunctions.push(unsubscribe);
        }
      } catch (e) {
        if (e instanceof Error && !e.message.includes('disposed')) {
          console.warn('Failed to subscribe to chart time range changes:', e);
        }
      }
    });

    return () => {
      if (throttleTimeoutRef.current !== null) {
        clearTimeout(throttleTimeoutRef.current);
        throttleTimeoutRef.current = null;
      }
      unsubscribeFunctions.forEach((unsubscribe) => {
        if (typeof unsubscribe === 'function') {
          try {
            unsubscribe();
          } catch (e) {
            if (e instanceof Error && !e.message.includes('disposed')) {
              console.warn('Error unsubscribing from chart:', e);
            }
          }
        }
      });
    };
  }, [charts, enabled]);
}

