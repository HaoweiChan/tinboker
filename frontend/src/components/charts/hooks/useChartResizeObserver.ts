import { useEffect, useRef } from 'react';
import type { IChartApi } from 'lightweight-charts';


interface UseChartResizeObserverOptions {
  chart: IChartApi | null;
  containerRef: React.RefObject<HTMLDivElement | null>;
  enabled?: boolean;
}


export function useChartResizeObserver({ chart, containerRef, enabled = true }: UseChartResizeObserverOptions): void {
  // All hooks must be called unconditionally and in the same order
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const isDisposedRef = useRef(false);
  const pendingRafRef = useRef<number | null>(null);
  const resizeTimeoutRef = useRef<number | null>(null);

  // Update refs - always called
  useEffect(() => {
    // If chart becomes null, mark as disposed and cleanup
    if (!chart) {
      isDisposedRef.current = true;
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
    } else {
      chartRef.current = chart;
      isDisposedRef.current = false;
    }
  }, [chart]);

  useEffect(() => {
    if (!enabled || !chart || !containerRef.current) {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      return;
    }

    const container = containerRef.current;

    const resizeObserver = new ResizeObserver(() => {
      // Check if chart is still valid and container is still connected
      if (isDisposedRef.current || !chartRef.current || !container || !container.isConnected) {
        if (!container?.isConnected) {
          isDisposedRef.current = true;
          if (resizeObserverRef.current) {
            resizeObserverRef.current.disconnect();
            resizeObserverRef.current = null;
          }
        }
        return;
      }

      // Pre-check: Verify chart is not disposed before queuing resize operation
      try {
        const currentChart = chartRef.current;
        if (!currentChart) {
          isDisposedRef.current = true;
          return;
        }
        
        // Try to access timeScale to verify chart is not disposed
        // This will throw if the chart is disposed
        const timeScale = currentChart.timeScale();
        if (!timeScale) {
          isDisposedRef.current = true;
          return;
        }
      } catch {
        // Chart is disposed, mark it and cleanup immediately
        isDisposedRef.current = true;
        if (resizeObserverRef.current) {
          resizeObserverRef.current.disconnect();
          resizeObserverRef.current = null;
        }
        return;
      }

      const rect = container.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      // Cancel any pending resize operations
      if (pendingRafRef.current !== null) {
        cancelAnimationFrame(pendingRafRef.current);
        pendingRafRef.current = null;
      }
      if (resizeTimeoutRef.current !== null) {
        clearTimeout(resizeTimeoutRef.current);
        resizeTimeoutRef.current = null;
      }

      // Debounce resize operations to prevent rapid successive calls
      resizeTimeoutRef.current = window.setTimeout(() => {
        resizeTimeoutRef.current = null;
        
        // Final check before queuing resize
        if (isDisposedRef.current || !chartRef.current || !container || !container.isConnected) {
          return;
        }

        // Use requestAnimationFrame to defer and check again before calling applyOptions
        pendingRafRef.current = requestAnimationFrame(() => {
        pendingRafRef.current = null;
        // Double-check everything is still valid before calling applyOptions
        if (isDisposedRef.current || !chartRef.current || !container || !container.isConnected) {
          return;
        }

        // Store reference to chart before async operation
        const currentChart = chartRef.current;
        if (!currentChart) return;

        // Final check: Verify chart is not disposed right before calling applyOptions
        try {
          const timeScale = currentChart.timeScale();
          if (!timeScale) {
            isDisposedRef.current = true;
            return;
          }
        } catch {
          // Chart is disposed, mark it and cleanup
          isDisposedRef.current = true;
          if (resizeObserverRef.current) {
            resizeObserverRef.current.disconnect();
            resizeObserverRef.current = null;
          }
          return;
        }

        // Now safely call applyOptions with comprehensive error handling
        // Wrap in try-catch and also use a timeout to detect if chart becomes disposed
        try {
          // Use a flag to track if we should proceed
          let shouldProceed = true;
          
          // Double-check one more time right before calling
          if (isDisposedRef.current || !chartRef.current) {
            shouldProceed = false;
          }
          
          if (shouldProceed) {
            // Call applyOptions - errors here will be caught
            currentChart.applyOptions({
              autoSize: false,
              width: rect.width,
              height: rect.height,
            });
          }
        } catch {
          // Mark as disposed and cleanup on any error
          // This handles cases where chart is disposed during applyOptions execution
          isDisposedRef.current = true;
          if (resizeObserverRef.current) {
            resizeObserverRef.current.disconnect();
            resizeObserverRef.current = null;
          }
          // Silently ignore all errors including disposed chart errors
        }
        
        // Also set up a check after a short delay to catch async errors
        // This won't prevent the error but will help cleanup
        setTimeout(() => {
          if (isDisposedRef.current && resizeObserverRef.current) {
            resizeObserverRef.current.disconnect();
            resizeObserverRef.current = null;
          }
        }, 100);
        });
      }, 16); // ~60fps debounce
    });

    resizeObserver.observe(container);
    resizeObserverRef.current = resizeObserver;

    return () => {
      isDisposedRef.current = true;
      
      // Cancel any pending resize operations
      if (pendingRafRef.current !== null) {
        cancelAnimationFrame(pendingRafRef.current);
        pendingRafRef.current = null;
      }
      if (resizeTimeoutRef.current !== null) {
        clearTimeout(resizeTimeoutRef.current);
        resizeTimeoutRef.current = null;
      }
      
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
    };
  }, [chart, containerRef, enabled]);
}
