import React, { useMemo } from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { generateMockPriceSeries } from '@/services/mocks';

interface MainChartProps {
  isDark: boolean;
  timeframe: string;
  index: {
    id: string;
    label: string;
    value: string;
    change: string;
    isPositive: boolean;
    ticker: string;
    baseValue: number;
  };
}

const TIMEFRAME_POINTS: Record<string, number> = {
  '1D': 60,
  '5D': 80,
  '1M': 100,
  '6M': 160,
  YTD: 200,
  '1Y': 220,
  '5Y': 260,
  ALL: 300,
};

const MainChart: React.FC<MainChartProps> = ({ isDark, index, timeframe }) => {
  const series = useMemo(() => {
    const points = TIMEFRAME_POINTS[timeframe] ?? 120;
    return generateMockPriceSeries(points, index.baseValue);
  }, [index.baseValue, timeframe]);
  const changeIcon = index.isPositive ? ArrowUpRight : ArrowDownRight;
  const changeColor = index.isPositive ? 'text-sentiment-bull' : 'text-sentiment-bear';
  const pillClasses = index.isPositive ? 'bg-sentiment-bull-soft text-sentiment-bull' : 'bg-sentiment-bear-soft text-sentiment-bear';
  const lineColor = index.isPositive ? 'hsl(var(--sentiment-bull))' : 'hsl(var(--sentiment-bear))';
  const fillColor = index.isPositive ? 'hsl(var(--sentiment-bull) / 0.25)' : 'hsl(var(--sentiment-bear) / 0.25)';
  const chartHeight = typeof window !== 'undefined' && window.innerWidth < 768 ? 260 : 320;

  return (
    <div className="flex flex-col w-full h-full">
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className={`text-xs font-bold px-2 py-1 rounded ${pillClasses}`}>{index.label}</div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">{index.value}</h2>
          <span className={`${changeColor} font-mono text-xl flex items-center gap-1`}>
            {React.createElement(changeIcon, { size: 20 })}
            {index.change}
          </span>
        </div>
        <p className="text-muted-foreground text-xs mt-1">{index.ticker} • Market Closed</p>
      </div>

      <div className="mt-4 flex-1 w-full">
        <div className="relative w-full h-[260px] md:h-[320px]">
        <TradingViewChart
          data={series}
          theme={isDark ? 'dark' : 'light'}
          height={chartHeight}
          lineColor={lineColor}
          topColor={fillColor}
          bottomColor="rgba(15,23,42,0.05)"
          className="h-full w-full"
          minimal={false}
        />
        </div>
      </div>
    </div>
  );
};

export default MainChart;

