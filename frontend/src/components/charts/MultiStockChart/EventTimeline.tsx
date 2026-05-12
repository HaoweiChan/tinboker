import React, { useMemo } from 'react';
import { mockStockEvents } from '@/services/mocks';
import { useAppStore } from '@/store/useAppStore';
import type { StockEvent } from '@/services/types';
import earningsReportIconUrl from '@/assets/icons/earnings-report-icon.svg';
import announceIconUrl from '@/assets/icons/announce-icon.svg';
import dividendIconUrl from '@/assets/icons/dividend-icon.svg';


interface EventTimelineProps {
  tickers: string[];
}


const getEventIcon = (type: string, isDark: boolean): React.ReactNode => {
  const iconSize = 24;
  // CSS filter for theme-aware icons - make them white in dark theme, black in light theme
  // Since the SVGs use currentColor (which is black by default), we need to:
  // - Dark theme: invert to white (brightness(0) invert(1))
  // - Light theme: keep black (brightness(0) or no filter)
  const themeAwareFilter = isDark ? 'brightness(0) invert(1)' : 'brightness(0)';
  
  switch (type) {
    case 'earnings':
      return (
        <img
          src={earningsReportIconUrl}
          alt="Earnings Report Icon"
          className="w-6 h-6"
          width={iconSize}
          height={iconSize}
          style={{ display: 'inline-block', filter: themeAwareFilter }}
          loading="lazy"
        />
      );
    case 'dividend':
      return (
        <img
          src={dividendIconUrl}
          alt="Dividend Icon"
          className="w-6 h-6"
          width={iconSize}
          height={iconSize}
          style={{ display: 'inline-block', filter: themeAwareFilter }}
          loading="lazy"
        />
      );
    case 'conference':
    case 'news':
    case 'announcement':
    case 'custom':
    default:
      return (
        <img
          src={announceIconUrl}
          alt="Announcement Icon"
          className="w-6 h-6"
          width={iconSize}
          height={iconSize}
          style={{ display: 'inline-block', filter: themeAwareFilter }}
          loading="lazy"
        />
      );
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
    case 'custom':
      return 'bg-orange-500';
    default:
      return 'bg-slate-500';
  }
};

const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

export const EventTimeline: React.FC<EventTimelineProps> = ({ tickers }) => {
  const { selectedEvent, setSelectedEvent, theme } = useAppStore();
  const isDark = theme === 'dark';

  const relevantEvents = useMemo(() => {
    return mockStockEvents
      .filter(event => event.relatedTickers.some(ticker => tickers.includes(ticker)))
      .sort((a, b) => a.date - b.date);
  }, [tickers]);

  const handleEventClick = (event: StockEvent) => {
    if (selectedEvent === event.id) {
      setSelectedEvent(null);
    } else {
      setSelectedEvent(event.id);
    }
  };

  if (relevantEvents.length === 0) {
    return (
      <div className="w-full p-4 border-t overlay-border">
        <p className="text-sm overlay-text-secondary text-center">No events found for selected stocks</p>
      </div>
    );
  }

  return (
    <div className="w-full border-t overlay-border bg-overlay-bg">
      <div className="p-4">
        <h3 className="text-sm font-semibold overlay-text mb-3">Events Timeline</h3>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {relevantEvents.map((event) => (
            <button
              key={event.id}
              onClick={() => handleEventClick(event)}
              className={`
                flex flex-col items-center gap-2 p-3 rounded-lg transition-all min-w-[80px] flex-shrink-0
                ${selectedEvent === event.id
                  ? 'ring-2 ring-cyan ring-offset-2 ring-offset-overlay-bg'
                  : 'hover:opacity-80'
                }
              `}
              title={`${event.title} - ${formatDate(event.date)}`}
            >
              <div className={`p-2 rounded-lg ${getEventColor(event.type)} flex items-center justify-center`}>
                {getEventIcon(event.type, isDark)}
              </div>
              <div className="text-xs overlay-text-secondary text-center">
                {formatDate(event.date)}
              </div>
              <div className="text-xs overlay-text font-medium text-center truncate w-full">
                {event.title}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

