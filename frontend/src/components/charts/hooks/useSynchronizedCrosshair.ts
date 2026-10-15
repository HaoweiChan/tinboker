import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { pointPrice } from '@/utils/chartDataUtils';


interface UseSynchronizedCrosshairOptions {
  charts: (IChartApi | null)[];
  series: (ISeriesApi<'Area'> | null)[];
  enabled?: boolean;
}


/**
 * Hook to synchronize crosshair position across all charts when mouse moves.
 * Based on: https://tradingview.github.io/lightweight-charts/tutorials/how_to/set-crosshair-position
 */
export function useSynchronizedCrosshair({ 
  charts, 
  series, 
  enabled = true 
}: UseSynchronizedCrosshairOptions): void {
  const isSyncingRef = useRef(false);
  const chartsRef = useRef<(IChartApi | null)[]>([]);
  const seriesRef = useRef<(ISeriesApi<'Area'> | null)[]>([]);

  useEffect(() => {
    chartsRef.current = charts;
  }, [charts]);

  useEffect(() => {
    seriesRef.current = series;
  }, [series]);

  useEffect(() => {
    if (!enabled || charts.length === 0 || series.length === 0) {
      return;
    }

    const validCharts = charts.filter((chart): chart is IChartApi => chart !== null);
    const validSeries = series.filter((s): s is ISeriesApi<'Area'> => s !== null);
    
    if (validCharts.length === 0 || validSeries.length === 0) {
      return;
    }

    const unsubscribeFunctions: (() => void)[] = [];

    // Subscribe to crosshair move on each chart
    validCharts.forEach((chart, index) => {
      const seriesInstance = validSeries[index];
      if (!seriesInstance) return;

      try {
        const unsubscribe = chart.subscribeCrosshairMove((param) => {
          // Prevent infinite loop
          if (isSyncingRef.current || !param.time) {
            return;
          }

          isSyncingRef.current = true;

          const time = param.time as number;
          const data = param.seriesData.get(seriesInstance);
          
          if (!data) {
            isSyncingRef.current = false;
            return;
          }

          // Get price from the current chart's data
          const price = pointPrice(data);
          
          if (price === undefined || price === null || !Number.isFinite(price)) {
            isSyncingRef.current = false;
            return;
          }

          // Sync crosshair to all other charts
          const currentCharts = chartsRef.current.filter((c): c is IChartApi => c !== null);
          const currentSeries = seriesRef.current.filter((s): s is ISeriesApi<'Area'> => s !== null);

          currentCharts.forEach((otherChart, otherIndex) => {
            if (otherIndex !== index && otherChart !== null) {
              const otherSeries = currentSeries[otherIndex];
              if (otherSeries) {
                try {
                  // Find the closest data point in the other chart's series
                  const otherData = otherSeries.data();
                  if (otherData && otherData.length > 0) {
                    let closestPoint = otherData[0];
                    let minDiff = Math.abs((closestPoint.time as number) - time);

                    for (const point of otherData) {
                      const diff = Math.abs((point.time as number) - time);
                      if (diff < minDiff) {
                        minDiff = diff;
                        closestPoint = point;
                      }
                    }

                    const closestPrice = pointPrice(closestPoint);
                    const closestTime = closestPoint.time;

                    if (closestPrice !== undefined && closestPrice !== null && Number.isFinite(closestPrice)) {
                      otherChart.setCrosshairPosition(closestPrice, closestTime, otherSeries);
                    }
                  }
                } catch {
                  // Ignore errors
                }
              }
            }
          });

          setTimeout(() => {
            isSyncingRef.current = false;
          }, 0);
        });

        if (typeof unsubscribe === 'function') {
          unsubscribeFunctions.push(unsubscribe);
        }
      } catch {
        // Ignore errors
      }
    });

    return () => {
      unsubscribeFunctions.forEach((unsubscribe) => {
        if (typeof unsubscribe === 'function') {
          try {
            unsubscribe();
          } catch {
            // Ignore errors
          }
        }
      });
    };
  }, [charts, series, enabled]);
}

