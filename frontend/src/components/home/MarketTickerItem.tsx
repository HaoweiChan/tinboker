import React, { useMemo } from 'react';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { generateMockPriceSeries } from '@/services/mocks';

interface MarketTickerItemProps {
  label: string;
  value: string;
  change: string;
  isPositive: boolean;
  isDark: boolean;
  isActive?: boolean;
  onSelect?: () => void;
}

const MarketTickerItem: React.FC<MarketTickerItemProps> = ({ label, value, change, isPositive, isDark, isActive = false, onSelect }) => {
  const numericValue = Number(value.replace(/,/g, '')) || 100;
  const series = useMemo(() => generateMockPriceSeries(24, numericValue), [numericValue]);
  const baseClasses = `flex flex-col min-w-[140px] p-3 rounded-lg border transition-colors ${
    isDark ? 'hover:bg-white/5 border-transparent hover:border-white/10' : 'hover:bg-muted border-transparent hover:border-border'
  }`;
  const activeClasses = isActive ? (isDark ? 'border-accent-info bg-accent-info-soft' : 'border-accent-info bg-accent-info-soft') : '';

  const content = (
    <>
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-muted-foreground text-xs font-bold">{label}</span>
        <div className="w-16 h-8">
          <TradingViewChart
            data={series}
            theme={isDark ? 'dark' : 'light'}
            height={32}
            lineColor={isPositive ? 'hsl(var(--sentiment-bull))' : 'hsl(var(--sentiment-bear))'}
            topColor={isPositive ? 'hsl(var(--sentiment-bull) / 0.4)' : 'hsl(var(--sentiment-bear) / 0.4)'}
            bottomColor="transparent"
            minimal
            className="h-full w-full"
          />
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-financial text-base font-medium text-foreground">{value}</span>
        <span className={`text-xs font-financial ${isPositive ? 'text-sentiment-bull' : 'text-sentiment-bear'}`}>{change}</span>
      </div>
    </>
  );

  if (onSelect) {
    return (
      <button
        type="button"
        onClick={onSelect}
        className={`${baseClasses} ${activeClasses} text-left w-full cursor-pointer`}
      >
        {content}
      </button>
    );
  }

  return (
    <div className={`${baseClasses} ${activeClasses}`}>
      {content}
    </div>
  );
};

export default MarketTickerItem;
