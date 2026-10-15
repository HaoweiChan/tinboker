import { useEffect, useState, useRef } from 'react';
import type { Coordinate, IChartApi, UTCTimestamp } from 'lightweight-charts';
import type { StockEvent } from '@/services/types';

export interface EventIconPosition {
  event: StockEvent;
  x: number;
  visible: boolean;
}

/**
 * Hook to compute x-coordinates for event icons based on chart timeline.
 * Observes chart pan/zoom and window resize to keep positions synchronized.
 */
export function useChartEventIconPositions(
  chart: IChartApi | null,
  events: StockEvent[]
): EventIconPosition[] {
  const [positions, setPositions] = useState<EventIconPosition[]>([]);
  const chartRef = useRef(chart);
  const eventsRef = useRef(events);

  // Keep refs up to date
  useEffect(() => {
    chartRef.current = chart;
  }, [chart, events]);

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  useEffect(() => {
    if (!chart || events.length === 0) {
      setPositions([]);
      return;
    }

    const calculatePositions = () => {
      if (!chartRef.current) {
        return;
      }

      try {
        const timeScale = chartRef.current.timeScale();
        const visibleRange = timeScale.getVisibleRange();
        
        // Get chart width for approximate calculations
        let chartWidth = 800; // Default fallback
        try {
          const chartOptions = chartRef.current.options();
          if (chartOptions && chartOptions.width) {
            chartWidth = chartOptions.width;
          }
        } catch {
          // Use default width if we can't get it
        }
        
        const newPositions: EventIconPosition[] = eventsRef.current
          .map((event) => {
            try {
              const eventDateSeconds = Math.floor(event.date / 1000);
              
              // Try timeToCoordinate first
              let x = timeScale.timeToCoordinate(eventDateSeconds as UTCTimestamp);
              
              // If x is null, try to calculate approximate position if event is within buffer
              if ((x === null || x === undefined) && visibleRange && visibleRange.from && visibleRange.to) {
                const from = Number(visibleRange.from);
                const to = Number(visibleRange.to);
                const buffer = 86400 * 60; // 60 day buffer
                const isWithinBuffer = eventDateSeconds >= (from - buffer) && eventDateSeconds <= (to + buffer);
                
                if (isWithinBuffer) {
                  // Calculate approximate x based on time proportion
                  const timeRange = to - from;
                  const timePosition = (eventDateSeconds - from) / timeRange;
                  // Approximate x position (assuming price scale takes ~80px on right)
                  const plotAreaWidth = chartWidth > 0 ? chartWidth - 80 : 800;
                  x = (timePosition * plotAreaWidth) as Coordinate;
                }
              }
              
              // Check for null/undefined
              if (x === null || x === undefined) {
                return { event, x: -1, visible: false };
              }

              // Check if event is within visible range
              if (!visibleRange || !visibleRange.from || !visibleRange.to) {
                return { event, x: -1, visible: false };
              }

              // Clamp x to valid range: if negative but within reasonable bounds, clamp to 0
              // This allows events just outside the visible range to show at the left edge
              const clampedX = Math.max(0, x as number);
              
              // Only show events that are within a reasonable buffer of the visible range
              const eventTime = eventDateSeconds;
              const from = Number(visibleRange.from);
              const to = Number(visibleRange.to);
              const buffer = 86400 * 60; // 60 day buffer to show more events
              const isWithinBuffer = eventTime >= (from - buffer) && eventTime <= (to + buffer);
              
              if (!isWithinBuffer) {
                return { event, x: -1, visible: false };
              }

              return { event, x: clampedX, visible: true };
            } catch {
              return { event, x: -1, visible: false };
            }
          })
          .filter((pos) => pos.x >= 0 && pos.x !== -1);

        setPositions(newPositions);
      } catch (error) {
        // Silently ignore disposed chart errors
        if (error instanceof Error && error.message.includes('disposed')) {
          return;
        }
        console.warn('Error calculating event positions:', error);
      }
    };

    // Delay initial calculation to ensure chart is fully initialized
    // Use a longer delay to ensure the chart is fully rendered and has data
    const timeoutId = setTimeout(() => {
      // Double-check chart is still available before calculating
      if (chartRef.current) {
        calculatePositions();
      }
    }, 300);

    // Subscribe to visible time range changes (pan/zoom)
    let unsubscribeVisibleRange: (() => void) | null = null;
    let initialTimeout: ReturnType<typeof setTimeout> | null = null;

    try {
      const timeScale = chart.timeScale();
      
      // Initial calculation after a short delay to ensure chart is ready
      initialTimeout = setTimeout(() => {
        if (chartRef.current) {
          calculatePositions();
        }
      }, 500);
      
      const handler = () => {
        // Debounce to avoid too many calculations
        setTimeout(() => {
          if (chartRef.current) {
            calculatePositions();
          }
        }, 50);
      };
      
      timeScale.subscribeVisibleTimeRangeChange(handler);
      unsubscribeVisibleRange = () => timeScale.unsubscribeVisibleTimeRangeChange(handler);
      
    } catch (error) {
      if (error instanceof Error && !error.message.includes('disposed')) {
        console.warn('Error subscribing to chart events:', error);
      }
    }

    // Subscribe to window resize
    const handleResize = () => {
      calculatePositions();
    };
    window.addEventListener('resize', handleResize);

    // Return cleanup function
    return () => {
      clearTimeout(timeoutId);
      if (initialTimeout) {
        clearTimeout(initialTimeout);
      }
      if (unsubscribeVisibleRange && typeof unsubscribeVisibleRange === 'function') {
        try {
          unsubscribeVisibleRange();
        } catch (error) {
          if (error instanceof Error && !error.message.includes('disposed')) {
            console.warn('Error unsubscribing from visible range:', error);
          }
        }
      }
      window.removeEventListener('resize', handleResize);
    };
  }, [chart]);

  return positions;
}

