import React, { useMemo } from 'react';
import { mockCompanyDetails, calculateEventMovement } from '@/services/mocks';
import { useAppStore } from '@/store/useAppStore';
import type { StockEvent } from '@/services/types';
import earningsReportIconUrl from '@/assets/icons/earnings-report-icon.svg';
import announceIconUrl from '@/assets/icons/announce-icon.svg';
import dividendIconUrl from '@/assets/icons/dividend-icon.svg';


interface EventDetailsGridProps {
  event: StockEvent;
  tickers: string[];
  onClose: () => void;
  sidebarWidth?: number;
}


/**
 * Event details grid that expands when an event is clicked.
 * Shows event information and price changes for affected stocks.
 */
export const EventDetailsGrid: React.FC<EventDetailsGridProps> = ({
  event,
  tickers,
  onClose,
  sidebarWidth = 400,
}) => {
  const { theme } = useAppStore();
  const isDark = theme === 'dark';

  // Calculate price movements for each ticker affected by this event
  const priceMovements = useMemo(() => {
    return tickers
      .filter(ticker => event.relatedTickers.includes(ticker))
      .map(t => {
        const companyDetail = mockCompanyDetails[t];
        if (!companyDetail) return null;
        
        const movements = calculateEventMovement(t, event, companyDetail.chartData);
        if (!movements) return null;
        
        return {
          ...movements,
          ticker: companyDetail.ticker,
          name: companyDetail.name,
        };
      })
      .filter((movement): movement is NonNullable<typeof movement> => movement !== null);
  }, [event, tickers]);

  const getEventIcon = (type: string): string => {
    switch (type) {
      case 'earnings':
        return earningsReportIconUrl;
      case 'dividend':
        return dividendIconUrl;
      default:
        return announceIconUrl;
    }
  };

  const getEventColor = (type: string): string => {
    switch (type) {
      case 'earnings':
        return 'bg-accent-info';
      case 'conference':
        return 'bg-purple-500';
      case 'news':
        return 'bg-cyan-500';
      case 'dividend':
        return 'bg-lime-500';
      default:
        return 'bg-slate-500';
    }
  };

  const formatDate = (timestamp: number): string => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatPriceChange = (changePercent?: number): string => {
    if (changePercent === undefined) return 'N/A';
    const sign = changePercent >= 0 ? '+' : '';
    return `${sign}${changePercent.toFixed(2)}%`;
  };

  const iconFilter = isDark ? 'brightness(0) invert(1)' : 'brightness(0)';

  // Account for header height (typically 64px)
  const headerHeight = 64;
  
  return (
    <div 
      className="fixed bg-overlay-bg/95 backdrop-blur-sm border overlay-border p-4 z-[2000] shadow-2xl overflow-y-auto"
      style={{
        top: `${headerHeight}px`,
        right: 0,
        width: `${sidebarWidth}px`,
        height: `calc(100vh - ${headerHeight}px)`,
        marginLeft: '0px',
        marginRight: '0px',
        paddingLeft: '24px', // Match SidebarWrapper padding
        paddingRight: '24px',
      }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg ${getEventColor(event.type)} flex items-center justify-center`}>
            <img
              src={getEventIcon(event.type)}
              alt={`${event.type} icon: ${event.title}`}
              className="w-6 h-6"
              style={{ filter: iconFilter }}
              loading="lazy"
            />
          </div>
          <div>
            <h3 className="text-lg font-semibold overlay-text">{event.title}</h3>
            <p className="text-sm overlay-text-secondary">{formatDate(event.date)}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-overlay-border transition-colors"
          aria-label="Close event details"
        >
          <svg className="w-5 h-5 overlay-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <p className="text-sm overlay-text-secondary mb-4">{event.description}</p>

      {priceMovements.length > 0 && (
        <div className="border-t overlay-border pt-4">
          <h4 className="text-sm font-semibold overlay-text mb-3">Price Impact After Event</h4>
          <div className="flex flex-col gap-3 max-h-[300px] overflow-y-auto pr-2">
            {priceMovements.map((movement) => (
              <div
                key={movement.ticker}
                className="p-3 rounded-lg bg-overlay-border/50 border overlay-border hover:bg-overlay-border/70 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="font-semibold overlay-text">{movement.ticker}</div>
                    <div className="text-xs overlay-text-secondary">{movement.name}</div>
                  </div>
                  {movement.priceAtEvent && (
                    <div className="text-sm font-medium overlay-text">
                      ${movement.priceAtEvent.toFixed(2)}
                    </div>
                  )}
                </div>
                <div className="space-y-1.5 text-xs mt-3">
                  {movement.changePercent1d !== undefined && (
                    <div className="flex justify-between items-center">
                      <span className="overlay-text-secondary">1 Day:</span>
                      <span className={`font-medium ${movement.changePercent1d >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPriceChange(movement.changePercent1d)}
                        {movement.priceAfter1d && (
                          <span className="ml-1 overlay-text-secondary text-[10px]">
                            (${movement.priceAfter1d.toFixed(2)})
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                  {movement.changePercent1w !== undefined && (
                    <div className="flex justify-between items-center">
                      <span className="overlay-text-secondary">1 Week:</span>
                      <span className={`font-medium ${movement.changePercent1w >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPriceChange(movement.changePercent1w)}
                        {movement.priceAfter1w && (
                          <span className="ml-1 overlay-text-secondary text-[10px]">
                            (${movement.priceAfter1w.toFixed(2)})
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                  {movement.changePercent1m !== undefined && (
                    <div className="flex justify-between items-center">
                      <span className="overlay-text-secondary">1 Month:</span>
                      <span className={`font-medium ${movement.changePercent1m >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatPriceChange(movement.changePercent1m)}
                        {movement.priceAfter1m && (
                          <span className="ml-1 overlay-text-secondary text-[10px]">
                            (${movement.priceAfter1m.toFixed(2)})
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

