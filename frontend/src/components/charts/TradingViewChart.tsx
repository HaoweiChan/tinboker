import React, { useEffect, useRef, useState } from 'react';
import { ColorType, CrosshairMode, createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import { RSI, MACD, Stochastic } from 'technicalindicators';
import type { PricePoint } from '@/utils/priceSeries';
import type { ChartDataPoint } from '@/services/types';

interface TradingViewChartProps {
  data: (PricePoint | ChartDataPoint)[];
  theme: 'light' | 'dark';
  height?: number;
  className?: string;
  lineColor?: string;
  topColor?: string;
  bottomColor?: string;
  minimal?: boolean;

  // Configuration
  activeIndicators?: string[]; // 'MA5', 'MA20', 'MA60'
  activeSubChart?: string; // 'Volume', 'RSI', 'MACD'
  showMA?: boolean; // Legacy
  showVolume?: boolean; // Legacy

  // Infinite scroll
  onLoadMore?: (beforeTimestamp: number) => void;
  isLoadingMore?: boolean;

  // Settings
  showPriceLines?: boolean;
}

// Helper to calculate Simple Moving Average
function calculateSMA(data: (ChartDataPoint | PricePoint)[], count: number) {
  const result = [];
  for (let i = count - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < count; j++) {
      const p = data[i - j];
      const val = 'close' in p ? p.close! : ('price' in p ? p.price! : ('value' in p ? p.value : 0));
      sum += val;
    }
    const val = sum / count;
    const p = data[i];
    let time = 0;
    if ('timestamp' in p) time = p.timestamp / 1000;
    else if ('time' in p) time = typeof p.time === 'number' ? p.time : new Date(p.time).getTime() / 1000;
    else if ('date' in p) time = new Date((p as any).date!).getTime() / 1000;

    result.push({ time: time as any, value: val });
  }
  return result;
}

export const TradingViewChart: React.FC<TradingViewChartProps> = ({
  data,
  theme,
  height = 400,
  className,
  lineColor = '#ef4444',
  topColor,
  bottomColor,
  minimal = false,
  activeIndicators = ['MA5', 'MA20', 'MA60'],
  activeSubChart = 'Volume',
  showMA = true, // Legacy fallback
  showVolume = true, // Legacy fallback
  onLoadMore,
  isLoadingMore = false,
  showPriceLines = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const loadMoreDebounceRef = useRef<any>(null);
  const isLoadingRef = useRef(false);
  const isFrozenRef = useRef(false); // Hoisted ref for freeze state
  const frozenTimeRef = useRef<number | null>(null); // Store time to re-calc position on scroll
  const [frozenX, setFrozenX] = useState<number | null>(null); // State for rendering the line

  // Normalize props
  const effectiveIndicators = minimal ? [] : (showMA ? activeIndicators : []);
  const effectiveSubChart = minimal ? 'None' : (showVolume ? activeSubChart : 'None');

  useEffect(() => {
    if (!containerRef.current) return;
    if (!data || data.length === 0) {
      return;
    }

    let resizeObserver: ResizeObserver | null = null;
    let seriesMap: Record<string, ISeriesApi<any>> = {};

    try {
      // 1. Initialize Chart
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: theme === 'dark' ? '#94a3b8' : '#64748b',
          fontFamily: "'Inter', sans-serif",
          // @ts-ignore
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: minimal ? 'transparent' : theme === 'dark' ? 'rgba(30, 41, 59, 0.5)' : 'rgba(226, 232, 240, 0.5)' },
          horzLines: { color: minimal ? 'transparent' : theme === 'dark' ? 'rgba(30, 41, 59, 0.5)' : 'rgba(226, 232, 240, 0.5)' },
        },
        crosshair: {
          mode: minimal ? CrosshairMode.Hidden : CrosshairMode.Normal,
        },
        rightPriceScale: {
          visible: !minimal,
          borderColor: theme === 'dark' ? '#1e293b' : '#e2e8f0',
          scaleMargins: {
            top: 0.1,
            bottom: effectiveSubChart !== 'None' ? 0.3 : 0.1,
          },
        },
        timeScale: {
          visible: !minimal,
          borderColor: theme === 'dark' ? '#1e293b' : '#e2e8f0',
          timeVisible: true,
        },
        handleScroll: !minimal,
        handleScale: !minimal,
      });

      chartRef.current = chart;

      // Prepare Data
      const sortedData = [...data].sort((a, b) => {
        const getTs = (p: PricePoint | ChartDataPoint) => {
          if ('timestamp' in p) return p.timestamp;
          if ('time' in p) return typeof p.time === 'number' ? p.time * 1000 : new Date(p.time).getTime(); // PricePoint time is usually seconds or date string
          if ('date' in p) return new Date((p as any).date!).getTime();
          return 0;
        };
        return getTs(a) - getTs(b);
      });

      const closeValues = sortedData.map(d => {
        if ('close' in d) return d.close ?? 0;
        if ('price' in d) return d.price ?? 0;
        if ('value' in d) return d.value;
        return 0;
      });

      // Simple heuristic: if first point has 'open', treat as OHLC
      const isCandlestick = 'open' in sortedData[0];

      const getSeconds = (p: PricePoint | ChartDataPoint) => {
        if ('timestamp' in p) return p.timestamp / 1000;
        if ('time' in p) return typeof p.time === 'number' ? p.time : new Date(p.time).getTime() / 1000;
        if ('date' in p) return new Date((p as any).date!).getTime() / 1000;
        return 0;
      };

      // 2. Sub-Charts (Bottom Pane)
      if (effectiveSubChart === 'Volume') {
        const volSeries = chart.addHistogramSeries({
          color: '#26a69a',
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume', // Separate scale
          priceLineVisible: false,
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.75, bottom: 0 }, // Bottom 25%
        });

        const volData = sortedData.map(p => {
          const time = getSeconds(p);
          // Volume color logic: match candle (Red=Up, Green=Down in Taiwan)
          let isUp = false;
          let vol = 0;

          if ('close' in p) {
            isUp = (p.close || 0) >= (p.open || 0);
            vol = p.volume || 0;
          } else if ('value' in p) {
            vol = 0;
          } else if ('price' in p) {
            vol = (p as any).volume || 0;
          }

          const finalColor = isUp
            ? '#ef4444' // Red
            : '#22c55e'; // Green

          return { time: time as any, value: vol, color: finalColor };
        });
        volSeries.setData(volData);
        seriesMap['Volume'] = volSeries;
      }
      else if (effectiveSubChart === 'RSI') {
        const rsiSeries = chart.addLineSeries({
          color: '#8b5cf6', // Violet
          lineWidth: 1,
          priceScaleId: 'rsi',
          title: 'RSI(14)',
          priceLineVisible: false,
        });
        chart.priceScale('rsi').applyOptions({
          scaleMargins: { top: 0.75, bottom: 0 },
        });

        // Calculate RSI using technicalindicators
        const rsiValues = RSI.calculate({ values: closeValues, period: 14 });
        // Map back to times (RSI array is shorter by period)
        const rsiData = [];
        const diff = sortedData.length - rsiValues.length;
        for (let i = 0; i < rsiValues.length; i++) {
          const time = getSeconds(sortedData[i + diff]);
          rsiData.push({ time: time as any, value: rsiValues[i] });
        }
        rsiSeries.setData(rsiData);

        // Add Overbought/Oversold lines? LightWeightCharts doesn't support easy horizontal lines without Series
        // We can add a "Constant" line series or just let user read values
        seriesMap['RSI'] = rsiSeries;
      }
      else if (effectiveSubChart === 'MACD') {
        // MACD Line
        const macdSeries = chart.addLineSeries({ color: '#2962FF', lineWidth: 1, priceScaleId: 'macd', title: 'MACD', priceLineVisible: false });
        // Signal Line
        const signalSeries = chart.addLineSeries({ color: '#FF6D00', lineWidth: 1, priceScaleId: 'macd', title: 'Signal', priceLineVisible: false });
        // Histogram
        const histSeries = chart.addHistogramSeries({ color: '#26a69a', priceScaleId: 'macd', title: 'Hist', priceLineVisible: false });

        chart.priceScale('macd').applyOptions({
          scaleMargins: { top: 0.75, bottom: 0 },
        });

        const macdResult = MACD.calculate({
          values: closeValues,
          fastPeriod: 12,
          slowPeriod: 26,
          signalPeriod: 9,
          SimpleMAOscillator: false,
          SimpleMASignal: false
        });

        const diff = sortedData.length - macdResult.length;
        const macdData = [];
        const signalData = [];
        const histData = [];

        for (let i = 0; i < macdResult.length; i++) {
          const time = getSeconds(sortedData[i + diff]);

          macdData.push({ time: time as any, value: macdResult[i].MACD });
          signalData.push({ time: time as any, value: macdResult[i].signal });

          const histVal = macdResult[i].histogram;
          histData.push({
            time: time as any,
            value: histVal,
            color: (histVal || 0) >= 0 ? '#ef4444' : '#22c55e'
          });
        }

        macdSeries.setData(macdData);
        signalSeries.setData(signalData);
        histSeries.setData(histData);
        seriesMap['MACD'] = macdSeries; // Store main one
      }
      else if (effectiveSubChart === 'KD') {
        const kSeries = chart.addLineSeries({ color: '#ff9800', lineWidth: 1, priceScaleId: 'kd', title: 'K', priceLineVisible: false });
        const dSeries = chart.addLineSeries({ color: '#2962ff', lineWidth: 1, priceScaleId: 'kd', title: 'D', priceLineVisible: false });
        chart.priceScale('kd').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

        const input = {
          high: sortedData.map(d => 'high' in d ? d.high! : ('value' in d ? d.value : (d as any).price || 0)),
          low: sortedData.map(d => 'low' in d ? d.low! : ('value' in d ? d.value : (d as any).price || 0)),
          close: closeValues,
          period: 9,
          signalPeriod: 3
        };
        const stochResult = Stochastic.calculate(input);
        const diff = sortedData.length - stochResult.length;
        const kData = [], dData = [];
        for (let i = 0; i < stochResult.length; i++) {
          const time = getSeconds(sortedData[i + diff]);
          kData.push({ time: time as any, value: stochResult[i].k });
          dData.push({ time: time as any, value: stochResult[i].d });
        }
        kSeries.setData(kData);
        dSeries.setData(dData);
        seriesMap['KD_K'] = kSeries;
        seriesMap['KD_D'] = dSeries;
      }
      else if (effectiveSubChart === 'Bias') {
        const biasSeries = chart.addLineSeries({ color: '#e91e63', lineWidth: 1, priceScaleId: 'bias', title: 'Bias', priceLineVisible: false });
        chart.priceScale('bias').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

        const period = 20;
        // Simple manual calculation for efficient single loop
        const biasData = [];
        for (let i = period - 1; i < sortedData.length; i++) {
          let sum = 0;
          for (let j = 0; j < period; j++) {
            sum += closeValues[i - j];
          }
          const ma = sum / period;
          const close = closeValues[i];
          const bias = ((close - ma) / ma) * 100;
          const time = getSeconds(sortedData[i]);
          biasData.push({ time: time as any, value: bias });
        }
        biasSeries.setData(biasData);
        seriesMap['Bias'] = biasSeries;
      }


      // 3. Main Series
      let mainSeries: ISeriesApi<any>;
      if (isCandlestick) {
        mainSeries = chart.addCandlestickSeries({
          upColor: '#ef4444',
          downColor: '#22c55e',
          borderVisible: false,
          wickUpColor: '#ef4444',
          wickDownColor: '#22c55e',
          priceLineVisible: showPriceLines,
        });
        const candleData = sortedData.map(p => {
          const time = getSeconds(p);
          const c = p as any; // Cast to access open/high/low/close safely
          return {
            time: time as any,
            open: c.open || c.value || 0,
            high: c.high || c.value || 0,
            low: c.low || c.value || 0,
            close: c.close || c.value || 0,
          };
        });
        mainSeries.setData(candleData);
      } else {
        mainSeries = chart.addAreaSeries({
          lineColor,
          topColor: topColor ?? `${lineColor}aa`,
          bottomColor: bottomColor ?? `${lineColor}15`,
          lineWidth: 2,
          priceLineVisible: showPriceLines,
        });
        const areaData = sortedData.map((p, i) => {
          const time = getSeconds(p);
          return { time: time as any, value: closeValues[i] };
        });
        mainSeries.setData(areaData);
      }
      seriesMap['Main'] = mainSeries;

      // 4. Moving Averages
      if (effectiveIndicators.includes('MA5')) {
        const maData = calculateSMA(sortedData as ChartDataPoint[], 5);
        const series = chart.addLineSeries({ color: '#ff9800', lineWidth: 1, crosshairMarkerVisible: false, title: '', priceLineVisible: false });
        series.setData(maData);
        seriesMap['MA5'] = series;
      }
      if (effectiveIndicators.includes('MA20')) {
        const maData = calculateSMA(sortedData as ChartDataPoint[], 20);
        const series = chart.addLineSeries({ color: '#2962ff', lineWidth: 1, crosshairMarkerVisible: false, title: '', priceLineVisible: false });
        series.setData(maData);
        seriesMap['MA20'] = series;
      }
      if (effectiveIndicators.includes('MA60')) {
        const maData = calculateSMA(sortedData as ChartDataPoint[], 60);
        const series = chart.addLineSeries({ color: '#00bcd4', lineWidth: 1, crosshairMarkerVisible: false, title: '', priceLineVisible: false });
        series.setData(maData);
        seriesMap['MA60'] = series;
      }

      chart.timeScale().fitContent();

      // 5. Legend / Crosshair

      chart.subscribeClick((param) => {
        if (!param.point || !param.time) return;

        const isFrozen = !isFrozenRef.current;
        isFrozenRef.current = isFrozen;

        if (isFrozen) {
          // Freeze: Capture time and calculate X
          frozenTimeRef.current = param.time as number;
          const x = chart.timeScale().timeToCoordinate(param.time as any);
          setFrozenX(x);
        } else {
          // Unfreeze
          frozenTimeRef.current = null;
          setFrozenX(null);
        }
      });

      // Update frozen line position on scroll/zoom
      chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        if (isFrozenRef.current && frozenTimeRef.current !== null) {
          const x = chart.timeScale().timeToCoordinate(frozenTimeRef.current as any);
          setFrozenX(x);
        }
      });

      chart.subscribeCrosshairMove(param => {
        if (!legendRef.current) return;

        // If frozen, do NOT update the legend
        if (isFrozenRef.current) return;

        if (
          param.point === undefined ||
          !param.time ||
          param.point.x < 0 ||
          param.point.x > containerRef.current!.clientWidth ||
          param.point.y < 0 ||
          param.point.y > height
        ) {
          legendRef.current.innerHTML = ''; // Hide or clear? 
          // Better: Show last point or empty
          return;
        }

        // Format Date to YYYY/MM/DD
        const dateObj = param.time ? new Date((param.time as number) * 1000) : new Date();
        const dateStr = `${dateObj.getFullYear()}/${(dateObj.getMonth() + 1).toString().padStart(2, '0')}/${dateObj.getDate().toString().padStart(2, '0')}`;

        // Get values
        // Main Series (OHLC)
        const mainData = param.seriesData.get(mainSeries) as any;
        let ohlcHtml = '';
        let changeHtml = '';

        if (mainData) {
          if (mainData.open !== undefined) {
            // Candlestick
            const open = mainData.open;
            const close = mainData.close;
            const change = close - open;
            const changePercent = (change / open) * 100;
            const isUp = change >= 0;
            const colorClass = isUp ? 'text-red-500' : 'text-green-500'; // Red Up

            changeHtml = `<span class="${colorClass} mr-4">漲跌 ${change.toFixed(2)} (${changePercent.toFixed(2)}%)</span>`;

            ohlcHtml = `
                    <span class="mr-3">開 <span class="${colorClass}">${open.toFixed(2)}</span></span>
                    <span class="mr-3">高 <span class="${colorClass}">${mainData.high.toFixed(2)}</span></span>
                    <span class="mr-3">低 <span class="${colorClass}">${mainData.low.toFixed(2)}</span></span>
                    <span>收 <span class="${colorClass}">${close.toFixed(2)}</span></span>
                  `;
          } else {
            // Line
            ohlcHtml = `<span class="text-slate-200">Price: ${mainData.value.toFixed(2)}</span>`;
          }
        }

        // MAs (Row 2) - Orange(#ff9800), Blue(#2962ff), Cyan(#00bcd4)
        let maHtml = '';
        ['MA5', 'MA20', 'MA60'].forEach(ma => {
          if (seriesMap[ma]) {
            const val = param.seriesData.get(seriesMap[ma]) as any;
            if (val) {
              const color = ma === 'MA5' ? 'text-[#ff9800]' : ma === 'MA20' ? 'text-[#2962ff]' : 'text-[#00bcd4]';
              maHtml += `<span class="${color} mr-4">${ma} ${val.value.toFixed(2)}</span>`;
            }
          }
        });

        // Sub-Chart Legend (Row 3 or Side)
        let subHtml = '';
        if (effectiveSubChart === 'Volume' && seriesMap['Volume']) {
          const val = param.seriesData.get(seriesMap['Volume']) as any;
          if (val) subHtml = `<span class="text-slate-500 ml-4">Vol ${val.value.toLocaleString()}</span>`;
        } else if (effectiveSubChart === 'RSI' && seriesMap['RSI']) {
          const val = param.seriesData.get(seriesMap['RSI']) as any;
          if (val) subHtml = `<span class="text-[#8b5cf6] ml-4">RSI ${val.value.toFixed(2)}</span>`;
        } else if (effectiveSubChart === 'MACD' && seriesMap['MACD']) {
          const val = param.seriesData.get(seriesMap['MACD']) as any;
          if (val) subHtml = `<span class="text-[#2962FF] ml-4">MACD ${val.value.toFixed(2)}</span>`;
        } else if (effectiveSubChart === 'KD') {
          const kVal = seriesMap['KD_K'] ? param.seriesData.get(seriesMap['KD_K']) as any : null;
          const dVal = seriesMap['KD_D'] ? param.seriesData.get(seriesMap['KD_D']) as any : null;
          if (kVal && dVal) subHtml = `<span class="text-[#ff9800] ml-4">K ${kVal.value.toFixed(2)}</span> <span class="text-[#2962ff] ml-2">D ${dVal.value.toFixed(2)}</span>`;
        } else if (effectiveSubChart === 'Bias' && seriesMap['Bias']) {
          const val = param.seriesData.get(seriesMap['Bias']) as any;
          if (val) subHtml = `<span class="text-[#e91e63] ml-4">Bias ${val.value.toFixed(2)}%</span>`;
        }

        // Update Legend DOM - Two Rows
        legendRef.current.innerHTML = `
             <div class="flex flex-col text-xs font-medium">
                <div class="flex items-center mb-1">
                    <span class="text-slate-900 dark:text-slate-200 mr-4">${dateStr}</span>
                    ${changeHtml}
                    <span class="text-slate-500 dark:text-slate-400 flex">${ohlcHtml}</span>
                </div>
                <div class="flex items-center">
                    ${maHtml}
                    ${subHtml}
                </div>
             </div>
          `;
      });


      // Resize Logic
      const handleResize = () => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
        }
      };
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(containerRef.current);

      // Infinite Scroll Logic
      if (onLoadMore && !minimal) {
        const LOAD_MORE_THRESHOLD = 10; // Load more when less than 10 bars remain unseen on left

        const unsubscribe = chart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
          if (!logicalRange || isLoadingRef.current || isLoadingMore) return;

          // logicalRange.from is the leftmost visible bar index (can be negative if scrolled past data)
          // If from < THRESHOLD, we're near the left edge and should load more
          if (logicalRange.from < LOAD_MORE_THRESHOLD) {
            // Debounce to prevent multiple rapid calls
            if (loadMoreDebounceRef.current) {
              clearTimeout(loadMoreDebounceRef.current);
            }

            loadMoreDebounceRef.current = setTimeout(() => {
              if (sortedData.length > 0 && onLoadMore) {
                // Get the oldest data point's timestamp
                const oldestPoint = sortedData[0];
                let oldestTimestamp = 0;
                const op = oldestPoint as any;
                if (op.timestamp) oldestTimestamp = op.timestamp;
                else if (op.time) oldestTimestamp = typeof op.time === 'number' ? op.time * 1000 : new Date(op.time).getTime();
                else if (op.date) oldestTimestamp = new Date(op.date).getTime();


                isLoadingRef.current = true;
                onLoadMore(oldestTimestamp);

                // Reset loading state after a delay (will be overridden by new data)
                setTimeout(() => {
                  isLoadingRef.current = false;
                }, 5000);
              }
            }, 500); // 500ms debounce
          }
        });

        // Store unsubscribe function for cleanup
        (chart as any)._infiniteScrollUnsubscribe = unsubscribe;
      }

    } catch (err) {
      console.error('[TradingViewChart] Error:', err);
    }

    return () => {
      if (loadMoreDebounceRef.current) {
        clearTimeout(loadMoreDebounceRef.current);
      }
      if (resizeObserver) resizeObserver.disconnect();
      if (chartRef.current) {
        // Unsubscribe from infinite scroll listener
        if ((chartRef.current as any)._infiniteScrollUnsubscribe) {
          (chartRef.current as any)._infiniteScrollUnsubscribe();
        }
        chartRef.current.remove();
        chartRef.current = null;
      }
    };

  }, [data, theme, height, minimal, activeIndicators, effectiveSubChart, onLoadMore, isLoadingMore, showPriceLines]);

  return (
    <div className={`relative ${className || ''}`} style={{ height }}>
      {/* Legend Overlay */}
      <div
        ref={legendRef}
        className="absolute top-2 left-2 z-20 pointer-events-none text-xs bg-white/0 text-slate-800 dark:text-slate-200"
      />

      {/* Frozen Vertical Line */}
      {frozenX !== null && (
        <div
          className="absolute top-0 bottom-[30px] z-10 border-l border-primary pointer-events-none"
          style={{ left: frozenX }}
        />
      )}
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
};

export default TradingViewChart;
