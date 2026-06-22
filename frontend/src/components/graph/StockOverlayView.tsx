import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { StockOverlayPage } from '@/pages/StockOverlayPage';
import { SidebarWrapper } from '@/components/sidebar/SidebarWrapper';
import type { TimeframeOption } from '@/services/types';


export const StockOverlayView: React.FC = () => {
  const {
    selectedStocksForOverlay,
    overlayOpen,
    overlayFullscreen,
    overlayTimeframe,
    removeStockFromOverlay,
    setOverlayFullscreen,
    setOverlayTimeframe,
    closeOverlay,
  } = useAppStore();

  const [overlayWidth, setOverlayWidth] = useState(400);
  const [isResizing, setIsResizing] = useState(false);
  const resizeRef = useRef<HTMLDivElement>(null);

  const timeframeOptions: TimeframeOption[] = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && overlayOpen) {
        closeOverlay();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [overlayOpen, closeOverlay]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsResizing(true);
    e.preventDefault();
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      
      const newWidth = window.innerWidth - e.clientX;
      setOverlayWidth(Math.max(300, Math.min(newWidth, window.innerWidth * 0.9)));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const handleTouchStart = useCallback(() => {
    setIsResizing(true);
  }, []);

  useEffect(() => {
    const handleTouchMove = (e: TouchEvent) => {
      if (!isResizing || e.touches.length === 0) return;
      
      const touch = e.touches[0];
      const newWidth = window.innerWidth - touch.clientX;
      setOverlayWidth(Math.max(300, Math.min(newWidth, window.innerWidth * 0.9)));
    };

    const handleTouchEnd = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleTouchEnd);
    }

    return () => {
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleTouchEnd);
    };
  }, [isResizing]);

  if (!overlayOpen || selectedStocksForOverlay.length === 0) {
    return null;
  }

  const handleRemoveStock = (ticker: string) => {
    removeStockFromOverlay(ticker);
    if (selectedStocksForOverlay.length === 1) {
      closeOverlay();
    }
  };

  const actualWidth = overlayFullscreen ? '100%' : `${overlayWidth}px`;

  return (
    <>
      <div
        className={`
          fixed right-0 top-16 h-[calc(100vh-4rem)]
          overlay-bg backdrop-blur-sm
          border-l overlay-border
          transform transition-all duration-300 ease-in-out z-40
          flex flex-col
          ${overlayOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
        style={{ width: actualWidth }}
      >
        {/* Draggable resize handle */}
        {!overlayFullscreen && (
          <div
            ref={resizeRef}
            onMouseDown={handleMouseDown}
            onTouchStart={handleTouchStart}
            className={`
              absolute left-0 top-0 bottom-0 w-1 cursor-col-resize
              hover:bg-cyan/30 transition-colors z-50
              ${isResizing ? 'bg-cyan/50' : ''}
            `}
            style={{ touchAction: 'none' }}
          />
        )}

        {/* Timeframe and Fullscreen Controls */}
        <div className="flex-shrink-0 p-4 border-b overlay-border">
          <div className="flex items-center justify-end gap-2">
            {/* Timeframe Dropdown */}
            <select
              value={overlayTimeframe}
              onChange={(e) => setOverlayTimeframe(e.target.value as TimeframeOption)}
              className="overlay-btn px-3 py-2 rounded-lg text-base font-medium overlay-text cursor-pointer transition-all"
            >
              {timeframeOptions.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
            
            <button
              onClick={() => setOverlayFullscreen(!overlayFullscreen)}
              className="overlay-btn p-2 rounded-lg transition-all"
              title={overlayFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            >
              <svg className="w-5 h-5 overlay-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {overlayFullscreen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Use StockOverlayPage wrapped in SidebarWrapper for content */}
        <div className="flex-1 overflow-hidden">
          <SidebarWrapper
            title="Stock Comparison"
            subtitle={`${selectedStocksForOverlay.length} stock${selectedStocksForOverlay.length !== 1 ? 's' : ''}`}
            onClose={closeOverlay}
          >
            <div style={{ marginLeft: '-20px', marginRight: '-20px', width: 'calc(100% + 40px)' }}>
              <StockOverlayPage
                tickers={selectedStocksForOverlay}
                onRemoveTicker={handleRemoveStock}
              />
            </div>
          </SidebarWrapper>
        </div>
      </div>

      {isResizing && (
        <div className="fixed inset-0 z-30 cursor-col-resize" style={{ touchAction: 'none' }} />
      )}
    </>
  );
};
