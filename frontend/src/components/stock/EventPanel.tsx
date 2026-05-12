import React, { useMemo, useState, useEffect } from 'react';
import { getSortedNews, fetchWithFallback, getStockByTicker, fetchWithFallbackAndErrorHandler } from '@/services';
import { mockStockEvents, calculateEventMovement, mockCompanyDetails } from '@/services/mocks';
import { useAppStore } from '@/store/useAppStore';
import type { StockEvent, CompanyDetail } from '@/services/types';
import { EventMovementIndicator } from './EventMovementIndicator';
import { EventIcon } from '@/components/icons/EventIcon';


interface EventPanelProps {
  tickers: string[];
}

export const EventPanel: React.FC<EventPanelProps> = ({ tickers }) => {
  const { selectedEvent, setSelectedEvent } = useAppStore();
  const [isExpanded, setIsExpanded] = useState(false);
  const [stockEvents, setStockEvents] = useState<StockEvent[]>(mockStockEvents);
  const [companyDetails, setCompanyDetails] = useState<Record<string, CompanyDetail>>({});

  // Fetch stock events from API with fallback to mocks
  useEffect(() => {
    fetchWithFallback(
      () => getSortedNews('date'),
      mockStockEvents,
      'getSortedNews'
    ).then(setStockEvents);
  }, []);

  // Fetch company details for tickers
  useEffect(() => {
    const fetchCompanyDetails = async () => {
      const details: Record<string, CompanyDetail> = {};
      for (const ticker of tickers) {
        await fetchWithFallbackAndErrorHandler(
          () => getStockByTicker(ticker),
          mockCompanyDetails[ticker] || null,
          `getStockByTicker(${ticker})`,
          () => {} // Silently fail for individual tickers
        ).then((detail) => {
          if (detail) {
            details[ticker] = detail;
          }
        });
      }
      setCompanyDetails(details);
    };
    if (tickers.length > 0) {
      fetchCompanyDetails();
    }
  }, [tickers]);

  const relevantEvents = useMemo(() => {
    return stockEvents
      .filter(event => event.relatedTickers.some(ticker => tickers.includes(ticker)))
      .sort((a, b) => b.date - a.date);
  }, [tickers, stockEvents]);


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
      case 'custom':
        return 'bg-orange-500';
      default:
        return 'bg-slate-500';
    }
  };

  const handleEventClick = (event: StockEvent) => {
    if (selectedEvent === event.id) {
      setSelectedEvent(null);
    } else {
      setSelectedEvent(event.id);
    }
  };

  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="border-t overlay-border">
      {/* Collapsible Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:opacity-80 transition-opacity"
      >
        <h3 className="text-lg font-semibold overlay-text">Events Timeline</h3>
        <svg
          className={`w-5 h-5 overlay-text-secondary transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      
      {/* Expanded Content */}
      {isExpanded && (
        <div className="max-h-64 overflow-y-auto p-4 pt-0">
          {relevantEvents.length === 0 ? (
            <p className="overlay-text-secondary text-sm">No events found for selected stocks</p>
          ) : (
            <div className="space-y-2">
              {relevantEvents.map((event) => (
                <div key={event.id}>
                  <button
                    onClick={() => handleEventClick(event)}
                    className={`
                      w-full text-left p-3 rounded-lg transition-all border-2
                      ${selectedEvent === event.id
                        ? 'overlay-event-item-selected'
                        : 'overlay-event-item border-transparent'
                      }
                    `}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${getEventColor(event.type)}`}>
                        <EventIcon type={event.type} size={20} />
                      </div>
                      
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="overlay-text font-semibold text-sm truncate">{event.title}</h4>
                          <span className="text-xs overlay-text-secondary ml-2 whitespace-nowrap">
                            {formatDate(event.date)}
                          </span>
                        </div>
                        
                        <p className="overlay-text-secondary text-xs mb-2">{event.description}</p>
                        
                        <div className="flex flex-wrap gap-1">
                          {event.relatedTickers.map((ticker) => (
                            <span
                              key={ticker}
                              className="px-2 py-0.5 overlay-tag text-xs rounded"
                            >
                              {ticker}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </button>
              
              {selectedEvent === event.id && (
                <div className="mt-2 ml-4 space-y-2">
                  {event.relatedTickers
                    .filter(ticker => tickers.includes(ticker))
                    .map((ticker) => {
                      const companyDetail = companyDetails[ticker] || mockCompanyDetails[ticker];
                      if (!companyDetail) return null;
                      
                      const movement = calculateEventMovement(
                        ticker,
                        event,
                        companyDetail.chartData
                      );
                      
                      if (!movement) return null;
                      
                      return (
                        <EventMovementIndicator
                          key={ticker}
                          ticker={ticker}
                          movement={movement}
                        />
                      );
                    })}
                </div>
              )}
            </div>
          ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

