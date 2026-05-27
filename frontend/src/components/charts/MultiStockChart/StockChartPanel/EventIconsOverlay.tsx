import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import type { StockEvent } from '@/services/types';
import type { EventIconPosition } from './hooks/useChartEventIconPositions';
import earningsReportIconUrl from '@/assets/icons/earnings-report-icon.svg';
import announceIconUrl from '@/assets/icons/announce-icon.svg';
import dividendIconUrl from '@/assets/icons/dividend-icon.svg';

interface EventIconsOverlayProps {
  events: StockEvent[];
  positions: EventIconPosition[];
  color?: string;
  onEventHover?: (event: StockEvent | null) => void;
  onEventClick?: (event: StockEvent) => void;
}

/**
 * HTML overlay component that renders event icons on top of the chart canvas.
 * Icons are positioned at the bottom of the chart (10-14px from bottom),
 * centered on their x-coordinates.
 */
export const EventIconsOverlay: React.FC<EventIconsOverlayProps> = ({
  positions,
  color,
  onEventHover,
  onEventClick,
}) => {
  const { theme, hoveredEvent, selectedEvent, setHoveredEvent } = useAppStore();
  const isDark = theme === 'dark';

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

  // Don't return null - always render the container, even if empty, to ensure proper positioning

  const iconFilter = isDark ? 'brightness(0) invert(1)' : 'brightness(0)';
  const iconColor = color || '#06B6D4'; // Default cyan color

  return (
    <div className="chart-overlay" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', zIndex: 20 }}>
      {positions.map(({ event, x }) => {
        // Show icons if x coordinate is valid
        if (x < 0) return null;

        const isHovered = hoveredEvent?.id === event.id;
        const isSelected = selectedEvent === event.id;
        const eventColor = getEventColor(event.type);
        const ICON_WIDTH = 16;

        return (
          <div
            key={event.id}
            className="event-icon-wrapper"
            style={{
              position: 'absolute',
              left: `${x - ICON_WIDTH / 2}px`,
              bottom: '30px',
              pointerEvents: 'auto',
            }}
            onMouseEnter={() => {
              setHoveredEvent(event);
              onEventHover?.(event);
            }}
            onMouseLeave={() => {
              setHoveredEvent(null);
              onEventHover?.(null);
            }}
            onClick={() => {
              onEventClick?.(event);
            }}
          >
            <div
              className={`
                w-4 h-4 rounded flex items-center justify-center transition-all duration-150
                ${isHovered || isSelected ? eventColor : 'bg-slate-500/50'}
                ${isHovered || isSelected ? 'ring-1 ring-cyan opacity-100' : 'opacity-70 hover:opacity-100'}
              `}
              style={{
                filter: isHovered || isSelected 
                  ? `drop-shadow(0 0 4px ${iconColor}60)` 
                  : undefined,
              }}
              title={`${event.title} - ${new Date(event.date).toLocaleDateString()}`}
            >
              <img
                src={getEventIcon(event.type)}
                alt={`${event.type} icon: ${event.title}`}
                className="event-icon"
                width={12}
                height={12}
                loading="lazy"
                style={{
                  display: 'block',
                  width: '12px',
                  height: '12px',
                  objectFit: 'contain',
                  filter: iconFilter,
                  opacity: isHovered || isSelected ? 1 : 0.7,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

