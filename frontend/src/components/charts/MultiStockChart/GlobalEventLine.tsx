import React from 'react';
import type { StockEvent } from '@/services/types';


interface GlobalEventLineProps {
  x: number;
  visible: boolean;
  event?: StockEvent | null;
}


/**
 * Global vertical event line component that spans across all stacked charts.
 * This creates a synchronized vertical marker visible across all chart panels.
 * 
 * Based on the pattern described in:
 * https://github.com/tradingview/lightweight-charts/issues/1765
 */
export const GlobalEventLine: React.FC<GlobalEventLineProps> = ({ x, visible, event }) => {
  if (!visible || x < 0) return null;

  return (
    <>
      {/* Dashed vertical line */}
      <div
        className="global-event-line absolute top-0 bottom-0 pointer-events-none z-[1000]"
        style={{
          left: `${x}px`,
          width: '1px',
          borderLeft: '1px dashed rgba(255, 255, 255, 0.6)',
        }}
        aria-label={event?.title || 'Global event marker'}
      />
      {/* Event label centered on the line */}
      {event && (
        <div
          className="absolute pointer-events-none z-[1001]"
          style={{
            left: `${x}px`,
            top: '50%',
            transform: 'translate(-50%, -50%)',
          }}
        >
          <div className="bg-overlay-bg/90 backdrop-blur-sm px-3 py-1.5 rounded border overlay-border shadow-lg">
            <span className="text-base font-medium overlay-text whitespace-nowrap">
              {event.title}
            </span>
          </div>
        </div>
      )}
    </>
  );
};

