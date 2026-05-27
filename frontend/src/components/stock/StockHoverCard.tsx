import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { getStockByTicker } from '@/services/api';
import { fetchWithFallbackAndErrorHandler } from '@/services/api/migration';
import { mockCompanyDetails } from '@/services/mocks';
import type { CompanyDetail } from '@/services/types';

interface StockHoverCardProps {
  symbol: string;
  children: React.ReactNode;
  className?: string;
  onClick?: (e: React.MouseEvent) => void;
}

export const StockHoverCard: React.FC<StockHoverCardProps> = ({ symbol, children, className, onClick }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [stockData, setStockData] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  
  const triggerRef = useRef<HTMLButtonElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    
    // Calculate position
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      // Center the tooltip above the element
      setCoords({
        top: rect.top - 10, // 10px offset up, fixed positioning relative to viewport
        left: rect.left + (rect.width / 2),
      });
    }
    
    setIsVisible(true);

    // Fetch data if not already loaded
    if (!stockData && !loading) {
      setLoading(true);
      const fetchData = async () => {
        try {
          const data = await fetchWithFallbackAndErrorHandler(
            () => getStockByTicker(symbol),
            mockCompanyDetails[symbol] || null, // Fallback to null instead of hardcoded TSLA
            `GET /api/stocks/${symbol}`,
            (error) => {
              // Silently handle 404s for stocks that might not exist in backend yet
              if (import.meta.env.DEV) {
                 console.debug(`[StockHoverCard] Failed to fetch data for ${symbol}`, error);
              }
            }
          );
          setStockData(data);
        } catch (error) {
          // Error already handled by fetchWithFallbackAndErrorHandler or caught here if it threw
          // Set minimal data with just the symbol if fetch fails
          setStockData({
            ticker: symbol,
            name: symbol, // Fallback to symbol as name
            price: 0,
            change: 0,
            changePercent: 0,
            stats: {
              volume: 0,
              beta: 0,
              volatility: 0
            },
            chartData: [],
            marketCap: 0,
            about: ''
          });
        } finally {
          setLoading(false);
        }
      };
      fetchData();
    }
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsVisible(false);
    }, 200); // Small delay to allow moving to tooltip if needed (though pointer-events-none usually better for simple tooltips)
  };

  const isPositive = stockData ? stockData.change >= 0 : true;

  return (
    <>
      <button
        ref={triggerRef}
        className={className}
        onClick={onClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {children}
      </button>

      {isVisible && createPortal(
        <div 
          className="fixed z-[9999] pointer-events-none transform -translate-x-1/2 -translate-y-full"
          style={{ top: coords.top, left: coords.left }}
        >
          <div className="mb-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl p-3 w-48 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex justify-between items-start mb-1">
              <div>
                <div className="font-bold text-slate-900 dark:text-slate-50 text-sm">
                  {stockData?.name || symbol}
                </div>
                <div className="text-xs text-slate-500 font-financial">
                  {symbol}.TW
                </div>
              </div>
            </div>
            
            {loading ? (
              <div className="h-6 w-20 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
            ) : (
              <div className="flex items-baseline gap-2">
                <span className={`text-lg font-bold font-financial ${isPositive ? 'text-red-500' : 'text-green-500'}`}>
                  {stockData?.price.toLocaleString() || '---'}
                </span>
                <span className={`text-xs font-medium font-financial ${isPositive ? 'text-red-500' : 'text-green-500'}`}>
                  {isPositive ? '▲' : '▼'} {Math.abs(stockData?.changePercent || 0).toFixed(2)}%
                </span>
              </div>
            )}
          </div>
          {/* Arrow */}
          <div className="w-3 h-3 bg-white dark:bg-slate-900 border-r border-b border-slate-200 dark:border-slate-700 transform rotate-45 absolute bottom-0.5 left-1/2 -translate-x-1/2"></div>
        </div>,
        document.body
      )}
    </>
  );
};

