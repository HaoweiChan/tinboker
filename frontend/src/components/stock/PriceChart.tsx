import React, { useEffect, useMemo, useRef } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { ChartDataPoint } from '@/services/types';
import { useAppStore } from '@/store/useAppStore';

interface PriceChartProps {
  data: ChartDataPoint[];
  ticker: string;
}

interface FormattedPoint {
  time: UTCTimestamp;
  value: number;
}

const getTimestamp = (point: ChartDataPoint): number => {
  if (point.timestamp) {
    return point.timestamp;
  }
  if (point.date) {
    const parsed = new Date(point.date).getTime();
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return Date.now();
};

const resolveChartColors = (isDark: boolean) => {
  if (typeof window === 'undefined') {
    return {
      bgColor: isDark ? '#101826' : '#f5f7fb',
      textColor: isDark ? '#94a3b8' : '#475569',
      gridColor: isDark ? 'rgba(148,163,184,0.15)' : 'rgba(148,163,184,0.25)',
      borderColor: isDark ? 'rgba(148,163,184,0.15)' : 'rgba(100,116,139,0.3)',
    };
  }

  const styles = getComputedStyle(document.documentElement);
  const readVar = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;

  return {
    bgColor: readVar('--color-card', isDark ? '#101826' : '#f5f7fb'),
    textColor: readVar('--color-muted-foreground', isDark ? '#94a3b8' : '#475569'),
    gridColor: readVar('--color-border', isDark ? 'rgba(148,163,184,0.15)' : 'rgba(148,163,184,0.25)'),
    borderColor: readVar('--color-border', isDark ? 'rgba(148,163,184,0.15)' : 'rgba(100,116,139,0.3)'),
  };
};

const PRICE_CHART_HEIGHT = 280;

export const PriceChart: React.FC<PriceChartProps> = ({ data, ticker }) => {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const legendRef = useRef<HTMLDivElement | null>(null);
  const legendFormatterRef = useRef<(price?: number, timestamp?: number) => void>(() => {});
  const theme = useAppStore((state) => state.theme);
  const isDark = theme === 'dark';
  const initialThemeRef = useRef(isDark);

  const formattedData = useMemo<FormattedPoint[]>(() => {
    if (!Array.isArray(data)) {
      return [];
    }

    return data
      .map((point) => {
        const price = point.price ?? point.close ?? point.open ?? 0;
        if (!Number.isFinite(price)) {
    return null;
        }
        const unixSeconds = Math.floor(getTimestamp(point) / 1000) as UTCTimestamp;
        return {
          time: unixSeconds,
          value: Number(price.toFixed(2)),
        };
      })
      .filter((point): point is FormattedPoint => Boolean(point));
  }, [data]);

  useEffect(() => {
    if (!chartContainerRef.current || chartRef.current) {
      return;
    }

    const { bgColor, textColor, gridColor, borderColor } = resolveChartColors(initialThemeRef.current);
    const setLegendContent = (price?: number, timestamp?: number) => {
      if (!legendRef.current) {
        return;
      }

      const dateLabel = timestamp
        ? new Date(timestamp * 1000).toLocaleDateString('zh-TW', { month: '2-digit', day: '2-digit' })
        : '';
      const priceLabel =
        typeof price === 'number' ? `$${price.toFixed(2)}` : '';

      legendRef.current.innerHTML = `
        <div style="color: var(--color-muted-foreground); font-weight: 600; font-size: 12px;">${ticker}</div>
        ${dateLabel ? `<div style="color: var(--color-secondary-foreground, var(--color-muted-foreground)); font-size: 10px;">${dateLabel}</div>` : ''}
        ${priceLabel ? `<div style="color: hsl(var(--primary)); font-size: 14px; font-weight: 600;">${priceLabel}</div>` : ''}
      `;
    };
    legendFormatterRef.current = setLegendContent;

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight || PRICE_CHART_HEIGHT,
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor,
        borderVisible: false,
      },
      timeScale: {
        borderColor,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: {
          width: 1,
          color: 'rgba(148,163,184,0.4)',
          style: 0,
        },
        horzLine: {
          visible: true,
          labelVisible: true,
        },
      },
      watermark: {
        visible: false,
      },
    });

    const areaSeries = chart.addAreaSeries({
      lineColor: '#22D3EE',
      topColor: 'rgba(34,211,238,0.45)',
      bottomColor: 'rgba(34,211,238,0.05)',
      lineWidth: 2,
      priceFormat: {
        type: 'price',
        minMove: 0.01,
      },
    });

    chartRef.current = chart;
    seriesRef.current = areaSeries;
    setLegendContent();

    const updateLegend: Parameters<IChartApi['subscribeCrosshairMove']>[0] = (param) => {
      if (!legendRef.current || !param.time || !seriesRef.current) {
        return;
      }

      const seriesData = param.seriesData.get(seriesRef.current);
      if (!seriesData) {
        return;
      }

      const price =
        typeof (seriesData as any).value === 'number'
          ? (seriesData as any).value
          : typeof (seriesData as any).close === 'number'
            ? (seriesData as any).close
            : undefined;

      setLegendContent(price, param.time as number);
    };

    chart.subscribeCrosshairMove(updateLegend);

    const resizeObserver = new ResizeObserver((entries) => {
      if (!chartRef.current || !entries.length) {
        return;
      }
      const { width, height } = entries[0].contentRect;
      chartRef.current.applyOptions({ width, height });
      chartRef.current.timeScale().fitContent();
    });

    resizeObserver.observe(chartContainerRef.current);
    resizeObserverRef.current = resizeObserver;

    return () => {
      legendFormatterRef.current = () => {};
      chart.unsubscribeCrosshairMove(updateLegend);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      resizeObserverRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) {
      return;
    }

    const { bgColor, textColor, gridColor, borderColor } = resolveChartColors(isDark);
    chartRef.current.applyOptions({
      layout: {
        background: {
          type: ColorType.Solid,
          color: bgColor,
        },
        textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      timeScale: {
        borderColor,
      },
      rightPriceScale: {
        borderColor,
        borderVisible: false,
      },
    });

    seriesRef.current.applyOptions({
      lineColor: '#22D3EE',
      topColor: isDark ? 'rgba(34,211,238,0.35)' : 'rgba(14,165,233,0.25)',
      bottomColor: isDark ? 'rgba(34,211,238,0.04)' : 'rgba(14,165,233,0.1)',
    });
  }, [theme]);

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) {
      return;
    }

    if (!formattedData.length) {
      seriesRef.current.setData([]);
      legendFormatterRef.current();
      return;
    }

    seriesRef.current.setData(formattedData);
    chartRef.current.timeScale().fitContent();
    const lastPoint = formattedData[formattedData.length - 1];
    if (lastPoint) {
      legendFormatterRef.current(lastPoint.value, lastPoint.time);
    }
  }, [formattedData]);

  return (
    <div className="w-full">
      <div
        className="relative w-full chart-container overflow-hidden"
        style={{ height: `${PRICE_CHART_HEIGHT}px`, backgroundColor: 'var(--color-card)' }}
      >
        <div ref={chartContainerRef} className="absolute inset-0 chart-container" />
        <div
          ref={legendRef}
          className="absolute left-4 top-3 z-10 text-xs font-semibold pointer-events-none select-none space-y-0.5"
        />
        {!formattedData.length && (
          <div className="absolute inset-0 flex items-center justify-center text-base text-foreground/70">
            No price data available
          </div>
        )}
      </div>
    </div>
  );
};

