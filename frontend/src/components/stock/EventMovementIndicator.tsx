import React from 'react';
import type { EventMovementIndicator as EventMovementType } from '@/services/types';


interface EventMovementIndicatorProps {
  ticker: string;
  movement: EventMovementType;
}

export const EventMovementIndicator: React.FC<EventMovementIndicatorProps> = ({
  ticker,
  movement,
}) => {
  const formatPercentage = (percent?: number): string => {
    if (percent === undefined) return 'N/A';
    const sign = percent >= 0 ? '+' : '';
    return `${sign}${percent.toFixed(2)}%`;
  };

  const getColorClass = (percent?: number): string => {
    if (percent === undefined) return 'text-muted-foreground';
    return percent >= 0 ? 'text-green-500' : 'text-red-500';
  };

  const getArrowIcon = (percent?: number) => {
    if (percent === undefined) return null;
    if (percent >= 0) {
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
        </svg>
      );
    }
    return (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
    );
  };

  return (
    <div className="bg-muted/50 rounded-lg p-3 border border-border">
      <div className="flex items-center justify-between mb-2">
        <span className="text-base font-semibold text-foreground">{ticker}</span>
        <span className="text-xs text-muted-foreground">
          At Event: ${movement.priceAtEvent.toFixed(2)}
        </span>
      </div>
      
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex flex-col items-center">
          <span className="text-muted-foreground mb-1">1 Day</span>
          <div className={`flex items-center gap-1 font-semibold ${getColorClass(movement.changePercent1d)}`}>
            {getArrowIcon(movement.changePercent1d)}
            <span>{formatPercentage(movement.changePercent1d)}</span>
          </div>
        </div>
        
        <div className="flex flex-col items-center">
          <span className="text-muted-foreground mb-1">1 Week</span>
          <div className={`flex items-center gap-1 font-semibold ${getColorClass(movement.changePercent1w)}`}>
            {getArrowIcon(movement.changePercent1w)}
            <span>{formatPercentage(movement.changePercent1w)}</span>
          </div>
        </div>
        
        <div className="flex flex-col items-center">
          <span className="text-muted-foreground mb-1">1 Month</span>
          <div className={`flex items-center gap-1 font-semibold ${getColorClass(movement.changePercent1m)}`}>
            {getArrowIcon(movement.changePercent1m)}
            <span>{formatPercentage(movement.changePercent1m)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

