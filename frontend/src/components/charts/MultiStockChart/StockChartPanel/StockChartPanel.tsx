import React, { useEffect, useRef, useMemo, useState } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { useChartResizeObserver } from '../../hooks/useChartResizeObserver';
import { convertToLineData } from '@/utils/chartDataUtils';
import type { ChartDataPoint, StockEvent } from '@/services/types';
import { useAppStore } from '@/store/useAppStore';
import { mockStockEvents } from '@/services/mocks';
import { EventIconsOverlay } from './EventIconsOverlay';
import { useChartEventIconPositions } from './hooks/useChartEventIconPositions';

interface StockChartPanelProps {
  ticker: string;
  name: string;
  data: ChartDataPoint[];
  color: string;
  isLast: boolean;
  sidebarWidth?: number;
  chart?: IChartApi | null;
  onRemoveStock?: (ticker: string) => void;
  onChartReady?: (chart: IChartApi) => void;
  onSeriesReady?: (series: ISeriesApi<'Area'>) => void;
}

/**
 * Stock chart panel component that wraps:
 * - the lightweight-chart instance
 * - the HTML overlay icons
 */
export const StockChartPanel: React.FC<StockChartPanelProps> = ({
  ticker,
  name: _name,
  data,
  color,
  isLast,
  sidebarWidth = 400,
  chart: externalChart,
  onRemoveStock,
  onChartReady,
  onSeriesReady,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [internalChart, setInternalChart] = useState<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const legendRef = useRef<HTMLDivElement | null>(null);
  const onChartReadyRef = useRef(onChartReady);
  const onSeriesReadyRef = useRef(onSeriesReady);
  const { theme, overlayFullscreen, setSelectedEvent } = useAppStore();
  const isDark = theme === 'dark';

  // Calculate chart height linearly based on sidebar width
  // Min sidebar width (250px) -> min height (150px)
  // Max sidebar width (800px) -> max height (300px)
  const calculateChartHeight = (width: number): number => {
    const minWidth = 250;
    const maxWidth = 800;
    const minHeight = 150;
    const maxHeight = 300;
    
    // Clamp width to valid range
    const clampedWidth = Math.max(minWidth, Math.min(maxWidth, width));
    
    // Linear interpolation
    const height = minHeight + (clampedWidth - minWidth) * (maxHeight - minHeight) / (maxWidth - minWidth);
    return Math.round(height);
  };

  const chartHeight = overlayFullscreen ? 300 : calculateChartHeight(sidebarWidth);

  // Get events related to this ticker
  const relevantEvents = useMemo(() => {
    return mockStockEvents
      .filter(event => event.relatedTickers.includes(ticker))
      .sort((a, b) => a.date - b.date);
  }, [ticker]);

  // Get the current chart instance (external or internal)
  // Use state for internal chart so hook re-runs when chart becomes available
  const currentChart = externalChart || internalChart;


  // Calculate icon positions using the hook
  const iconPositions = useChartEventIconPositions(currentChart, relevantEvents);

  useEffect(() => {
    onChartReadyRef.current = onChartReady;
  }, [onChartReady ?? undefined]);

  useEffect(() => {
    onSeriesReadyRef.current = onSeriesReady;
  }, [onSeriesReady ?? undefined]);

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const container = containerRef.current;
    const height = chartHeight;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let retryTimeoutId: ReturnType<typeof setTimeout> | null = null;
    
    const initChartWithRetry = (attempt = 0) => {
      if (chartRef.current || !containerRef.current) return;
      
      const rect = container.getBoundingClientRect();
      const width = rect.width || container.clientWidth || container.offsetWidth || 800;
      const actualHeight = rect.height || container.clientHeight || container.offsetHeight || height;

      if ((width <= 0 || actualHeight <= 0) && attempt < 5) {
        retryTimeoutId = setTimeout(() => initChartWithRetry(attempt + 1), 50);
        return;
      }

      if (width <= 0 || actualHeight <= 0) {
        console.warn('Chart container has invalid dimensions after retries:', { width, height: actualHeight });
        return;
      }

      try {
        // Get CSS variables for theme-aware colors
        const bgColor = getComputedStyle(document.documentElement)
          .getPropertyValue('--bg-surface')
          .trim() || (isDark ? '#1a1a1a' : '#ffffff');
        const textColor = getComputedStyle(document.documentElement)
          .getPropertyValue('--text-secondary')
          .trim() || (isDark ? '#94a3b8' : '#64748b');
        const gridColor = getComputedStyle(document.documentElement)
          .getPropertyValue('--border-subtle')
          .trim() || (isDark ? '#1e293b' : '#f1f5f9');
        const borderColor = getComputedStyle(document.documentElement)
          .getPropertyValue('--border-default')
          .trim() || (isDark ? '#334155' : '#e2e8f0');

        const chart = createChart(container, {
          autoSize: false,
          width: width,
          height: actualHeight,
          handleScroll: {
            mouseWheel: false,
            pressedMouseMove: true,
            horzTouchDrag: true,
            vertTouchDrag: true,
          },
          handleScale: {
            axisPressedMouseMove: {
              time: false,
              price: false,
            },
            axisDoubleClickReset: {
              time: false,
              price: false,
            },
            mouseWheel: false,
            pinch: false,
          },
          layout: {
            background: { 
              type: ColorType.Solid,
              color: bgColor 
            },
            textColor: textColor,
          },
          grid: {
            vertLines: { color: gridColor },
            horzLines: { color: gridColor },
          },
          timeScale: {
            visible: isLast,
            borderColor: borderColor,
            timeVisible: isLast,
          },
          rightPriceScale: {
            borderColor: borderColor,
            visible: true,
          },
          leftPriceScale: {
            visible: false,
          },
        });

        chartRef.current = chart;
        setInternalChart(chart); // Update state so hook re-runs

        // Convert hex color to rgba for transparency
        const hexToRgba = (hex: string, alpha: number) => {
          const r = parseInt(hex.slice(1, 3), 16);
          const g = parseInt(hex.slice(3, 5), 16);
          const b = parseInt(hex.slice(5, 7), 16);
          return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        };

        const areaSeries = chart.addAreaSeries({
          lineColor: color,
          topColor: hexToRgba(color, 0.25), // Semi-transparent fill
          bottomColor: hexToRgba(color, 0), // Fully transparent at bottom
          lineWidth: 2,
        });

        seriesRef.current = areaSeries;

        // Notify parent component about series ready
        if (onSeriesReadyRef.current) {
          onSeriesReadyRef.current(areaSeries);
        }

        // Set initial data if available
        if (data.length > 0) {
          const lineData = convertToLineData(data);
          if (lineData.length > 0) {
            areaSeries.setData(lineData as unknown as Parameters<typeof areaSeries.setData>[0]);
            setTimeout(() => {
              if (chartRef.current) {
                try {
                  chartRef.current.timeScale().fitContent();
                } catch (e) {
                  if (e instanceof Error && !e.message.includes('disposed')) {
                    console.warn('Error fitting content:', e);
                  }
                }
              }
            }, 0);
          }
        }

        // Setup legend
        if (legendRef.current) {
          const legend = legendRef.current;
          const legendTextColor = getComputedStyle(document.documentElement)
            .getPropertyValue('--text-secondary')
            .trim() || (isDark ? '#94a3b8' : '#64748b');
          
          const updateLegend = (param: any) => {
            if (!legend || !param.time) {
              legend.innerHTML = `<div style="color: ${legendTextColor}">${ticker}</div>`;
              return;
            }

            const data = param.seriesData.get(areaSeries);
            if (data) {
              const price = (data as any).value || (data as any).close || 0;
              const date = new Date((param.time as number) * 1000);
              const formattedDate = date.toLocaleDateString('zh-TW', { month: '2-digit', day: '2-digit' });
              const formattedPrice = typeof price === 'number' ? price.toFixed(2) : 'N/A';
              
              legend.innerHTML = `
                <div style="color: ${legendTextColor}; font-weight: 600; font-size: 14px; margin-bottom: 4px;">${ticker}</div>
                <div style="color: ${legendTextColor}; font-size: 12px;">${formattedDate}</div>
                <div style="color: ${color}; font-size: 16px; font-weight: 600; margin-top: 4px;">$${formattedPrice}</div>
              `;
            } else {
              legend.innerHTML = `<div style="color: ${legendTextColor}">${ticker}</div>`;
            }
          };

          chart.subscribeCrosshairMove(updateLegend);
          
          // Set initial legend state
          legend.innerHTML = `<div style="color: ${legendTextColor}">${ticker}</div>`;
        }

        if (onChartReadyRef.current) {
          onChartReadyRef.current(chart);
        }
      } catch (error) {
        console.error('Error creating chart:', error);
      }
    };

    timeoutId = setTimeout(() => initChartWithRetry(), 100);

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (retryTimeoutId) clearTimeout(retryTimeoutId);
      // Cleanup will be handled by chart.remove() which unsubscribes all listeners
            if (chartRef.current) {
              try {
                chartRef.current.remove();
              } catch (e) {
                console.warn('Error removing chart:', e);
              }
              chartRef.current = null;
              setInternalChart(null); // Clear state
            }
      if (seriesRef.current) {
        seriesRef.current = null;
      }
    };
  }, [isDark, isLast, overlayFullscreen, chartHeight, ticker, color]);

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;
    
    if (data.length === 0) {
      seriesRef.current.setData([]);
      return;
    }

    try {
      const lineData = convertToLineData(data);
      if (lineData.length > 0) {
        seriesRef.current.setData(lineData as unknown as Parameters<typeof seriesRef.current.setData>[0]);
        
        // Use setTimeout to defer fitContent to avoid disposal errors
        setTimeout(() => {
          if (chartRef.current) {
            try {
              chartRef.current.timeScale().fitContent();
            } catch (error) {
              if (error instanceof Error && error.message.includes('disposed')) {
                return;
              }
            }
          }
        }, 0);
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes('disposed')) {
        return;
      }
      console.error('Error setting chart data:', error);
    }
  }, [data]);

  useChartResizeObserver({
    chart: chartRef.current,
    containerRef,
    enabled: true,
  });

  // Update chart colors when theme changes
  useEffect(() => {
    if (!chartRef.current) return;

    const bgColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--bg-surface')
      .trim() || (isDark ? '#1a1a1a' : '#ffffff');
    const textColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--text-secondary')
      .trim() || (isDark ? '#94a3b8' : '#64748b');
    const gridColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--border-subtle')
      .trim() || (isDark ? '#1e293b' : '#f1f5f9');
    const borderColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--border-default')
      .trim() || (isDark ? '#334155' : '#e2e8f0');

    try {
      chartRef.current.applyOptions({
        layout: {
          background: { 
            type: ColorType.Solid,
            color: bgColor 
          },
          textColor: textColor,
        },
        grid: {
          vertLines: { color: gridColor },
          horzLines: { color: gridColor },
        },
        timeScale: {
          borderColor: borderColor,
        },
        rightPriceScale: {
          borderColor: borderColor,
        },
      });
    } catch (e) {
      // Chart might be disposed, ignore
    }
  }, [isDark]);

  const handleEventClick = (event: StockEvent) => {
    setSelectedEvent(event.id);
  };

  return (
    <div className="relative group chart-container" style={{ height: chartHeight, minHeight: chartHeight, width: '100%', marginLeft: '0px', marginRight: '0px', padding: 0 }}>
      {/* Chart container */}
      <div ref={containerRef} className="absolute inset-0 chart-container z-0" style={{ width: '100%', height: '100%', minHeight: chartHeight, margin: 0, padding: 0 }} />

      {/* Native Legend - positioned top-left */}
      <div
        ref={legendRef}
        className="absolute left-3 top-2 z-10 pointer-events-none"
      />

      {/* HTML Overlay for Event Icons */}
      <EventIconsOverlay
        events={relevantEvents}
        positions={iconPositions}
        color={color}
        onEventClick={handleEventClick}
      />

      {/* Remove stock button */}
      {onRemoveStock && (
        <button
          onClick={() => onRemoveStock(ticker)}
          className="absolute right-3 top-1 z-10 p-1.5 rounded-md bg-overlay-bg/90 hover:bg-overlay-bg border border-overlay-border/50 hover:border-red-500/50 opacity-0 group-hover:opacity-100 transition-all pointer-events-auto backdrop-blur-sm"
          title={`Remove ${ticker}`}
        >
          <svg className="w-3.5 h-3.5 text-overlay-text-secondary hover:text-red-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
};

