import React from 'react';
import earningsReportIconUrl from '@/assets/icons/earnings-report-icon.svg';
import announceIconUrl from '@/assets/icons/announce-icon.svg';
import dividendIconUrl from '@/assets/icons/dividend-icon.svg';
import type { StockEventType } from '@/services/types';

interface EventIconProps {
  type: StockEventType;
  className?: string;
  size?: number;
  asText?: boolean; // For chart labels that need text
}

export const EventIcon: React.FC<EventIconProps> = ({ 
  type, 
  className = '', 
  size = 16,
  asText = false 
}) => {
  if (asText) {
    // Return text labels for chart libraries that don't support images
    const labels: Record<StockEventType, string> = {
      earnings: 'E',
      conference: 'C',
      news: 'N',
      dividend: 'D',
      custom: '★',
    };
    return <span>{labels[type] || '•'}</span>;
  }

  const iconMap: Record<StockEventType, string> = {
    earnings: earningsReportIconUrl,
    conference: announceIconUrl,
    news: announceIconUrl,
    dividend: dividendIconUrl,
    custom: announceIconUrl,
  };

  const iconUrl = iconMap[type] || announceIconUrl;

  return (
    <img 
      src={iconUrl} 
      alt={`${type} event icon`}
      className={className}
      width={size}
      height={size}
      style={{ display: 'inline-block' }}
      loading="lazy"
    />
  );
};

