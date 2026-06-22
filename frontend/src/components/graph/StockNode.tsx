import React, { useMemo, useRef, useCallback } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import type { StockNodeData } from '@/services/types';
import { useAppStore } from '@/store/useAppStore';
import { calculateCircleRadius, formatLargeNumber } from '@/utils/nodeSize';
import { getIndustryColor, getIndustryFromTicker } from '@/utils/industryColors';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { generateMockPriceSeries } from '@/services/mocks';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { getStockLabel } from '@/utils/stockDisplay';

type Theme = 'dark' | 'light';

interface StockNodeProps extends NodeProps<StockNodeData> {
  allNodes?: Array<{ data: StockNodeData }>;
}

const Sparkline: React.FC<{ points: number[]; theme: Theme; isRising: boolean }> = ({ points, theme, isRising }) => {
  const series = useMemo(() => {
    if (!points || points.length < 2) {
      return generateMockPriceSeries(20, 100);
    }
    const now = Date.now();
    return points.map((value, index) => ({
      time: new Date(now - (points.length - 1 - index) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      value: Number(Number(value).toFixed(2)),
    }));
  }, [points]);

  return (
    <div className="w-full h-full">
      <TradingViewChart
        data={series}
        theme={theme}
        height={32}
        lineColor={isRising ? '#22c55e' : '#ef4444'}
        topColor={isRising ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}
        bottomColor="transparent"
        minimal
        className="h-full w-full"
      />
    </div>
  );
};

const formatPct = (pct: number) => {
  const sign = pct > 0 ? '+' : '';
  return `${sign}${(pct * 100).toFixed(2)}%`;
};

const formatPrice = (price: number | string | undefined) => {
  const numPrice = typeof price === 'string' ? parseFloat(price) : price;
  if (typeof numPrice !== 'number' || isNaN(numPrice)) return '$0.00';
  return `$${numPrice.toFixed(2)}`;
};

// Company-specific colors (logo-based)
const getCompanyColor = (ticker: string): string => {
  const colorMap: Record<string, string> = {
    'TSLA': '#EF4444', // Red
    'ROK': '#64748B', // Gray
    'NVDA': '#10B981', // Green
    'ABB': '#F97316', // Orange
    'IRBT': '#64748B', // Gray
    'INTC': '#2563EB', // Blue
    'MSFT': '#2563EB', // Blue
    'GOOGL': '#7C3AED', // Purple
    'AMD': '#F97316', // Orange
    'PLTR': '#2563EB', // Blue
    'SNOW': '#2563EB', // Blue
    'ENPH': '#059669', // Green
    'FSLR': '#2563EB', // Blue
    'NEE': '#7C3AED', // Purple
    'PLUG': '#059669', // Green
    'SEDG': '#F97316', // Orange
  };
  return colorMap[ticker] || '#64748B'; // Default gray
};

// Convert hex color to rgba with opacity
const hexToRgba = (hex: string, opacity: number): string => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
};

export const StockNode: React.FC<StockNodeProps> = (props) => {
  const { data, selected, allNodes = [], isConnectable } = props;
  const theme: Theme = data.theme ?? 'dark';
  const isUp = data.changePct >= 0;
  
  // Store state
  const storeNodeDisplayMode = useAppStore((state) => state.nodeDisplayMode);
  const storeNodeStyle = useAppStore((state) => state.nodeStyle);
  
  // Override from props if available (mapped from DisplayMode enum to internal string types)
  let nodeDisplayMode = storeNodeDisplayMode;
  if (data.displayMode) {
    if (data.displayMode === 'PRICE') nodeDisplayMode = 'default';
    else if (data.displayMode === 'MARKET_CAP') nodeDisplayMode = 'marketCap';
    else if (data.displayMode === 'REVENUE') nodeDisplayMode = 'revenue';
  }

  let nodeStyle = storeNodeStyle;
  if (data.nodeStyle) {
    if (data.nodeStyle === 'GHOST') nodeStyle = 'ghost';
    else if (data.nodeStyle === 'SOLID') nodeStyle = 'solid';
  }

  const nodeColorMode = useAppStore((state) => state.nodeColorMode);
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setSelectedCompany = useAppStore((state) => state.setSelectedCompany);
  const overlayOpen = useAppStore((state) => state.overlayOpen);
  const selectedStocksForOverlay = useAppStore((state) => state.selectedStocksForOverlay);
  const setSelectedStocksForOverlay = useAppStore((state) => state.setSelectedStocksForOverlay);
  const setOverlayOpen = useAppStore((state) => state.setOverlayOpen);
  const addStockToOverlay = useAppStore((state) => state.addStockToOverlay);
  
  const longPressTimerRef = useRef<number | null>(null);
  const isLongPressRef = useRef(false);
  
  // Interaction Logic
  const isDimmedBySelection = selectedCompany !== null && selectedCompany !== data.ticker;
  const isDimmedByOverlay = overlayOpen && !selectedStocksForOverlay.includes(data.ticker);
  const isDimmed = isDimmedBySelection || isDimmedByOverlay;
  const isInOverlay = selectedStocksForOverlay.includes(data.ticker);
  
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    isLongPressRef.current = false;
    longPressTimerRef.current = window.setTimeout(() => {
      isLongPressRef.current = true;
      setSelectedCompany(null);
      if (!overlayOpen) {
        setSelectedStocksForOverlay([data.ticker]);
        setOverlayOpen(true);
      } else {
        addStockToOverlay(data.ticker);
      }
      e.preventDefault();
      e.stopPropagation();
    }, 1000);
  }, [data.ticker, overlayOpen, setSelectedStocksForOverlay, setOverlayOpen, addStockToOverlay, setSelectedCompany]);
  
  const handlePointerUp = useCallback(() => {
    if (longPressTimerRef.current !== null) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);
  
  const handlePointerLeave = useCallback(() => {
    if (longPressTimerRef.current !== null) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);
  
  const handleClick = useCallback((e: React.MouseEvent) => {
    if (isLongPressRef.current) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    if (overlayOpen) {
      if (!selectedStocksForOverlay.includes(data.ticker)) {
        addStockToOverlay(data.ticker);
      }
      e.stopPropagation();
      return;
    }
    setSelectedCompany(data.ticker);
  }, [data.ticker, overlayOpen, selectedStocksForOverlay, addStockToOverlay, setSelectedCompany]);

  // --- RENDER: CARD MODE (Default/Price) ---
  if (nodeDisplayMode === 'default') {
    // Using visual style from CompanyNode.tsx for PRICE/Default mode
    // Adapting to use StockNodeData props
    
    // Determine styling based on "Risk" status (not in StockNodeData but in CompanyData - we'll default to normal)
    // TODO: Add status to StockNodeData if needed. For now assume normal.
    const isRisk = false; 
    
    const borderColor = isRisk ? 'border-destructive' : (selected ? 'border-accent-info' : 'border-border');
    const bgColor = isRisk ? 'bg-destructive/10' : 'bg-card';
    const textColor = 'text-foreground';
    const subTextColor = 'text-muted-foreground';
    const shadow = selected ? 'shadow-md ring-2 ring-accent-info ring-offset-2' : 'shadow-sm hover:shadow-md';

    return (
      <div 
        className={`relative group min-w-[220px] rounded-lg border-2 ${borderColor} ${bgColor} ${shadow} p-3 transition-all duration-200 cursor-pointer ${isDimmed ? 'opacity-40' : ''}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onClick={handleClick}
      >
        {/* Handles */}
        <Handle type="target" position={Position.Left} isConnectable={isConnectable} className="!bg-muted-foreground" />
        <Handle type="source" position={Position.Right} isConnectable={isConnectable} className="!bg-muted-foreground" />
        <Handle type="target" position={Position.Top} isConnectable={isConnectable} className="!bg-muted-foreground !opacity-0" />
        <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className="!bg-muted-foreground !opacity-0" />

        <div className="flex justify-between items-start mb-2">
          <div>
            {(() => {
              const { primary, secondary } = getStockLabel({
                ticker: data.ticker,
                name: data.name || data.label,
              });
              return (
                <>
                  <h3 className={`text-base font-bold leading-tight ${textColor}`}>{primary}</h3>
                  {secondary && <span className={`text-xs font-mono ${subTextColor}`}>{secondary}</span>}
                </>
              );
            })()}
          </div>
        </div>

        <div className="flex justify-between items-end">
          <div>
            <div className={`text-xl font-bold tracking-tight ${textColor}`}>{formatPrice(data.price)}</div>
            <div className={`flex items-center text-xs font-medium ${isUp ? 'text-sentiment-bull' : 'text-sentiment-bear'}`}>
              {isUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
              {formatPct(data.changePct)}
            </div>
          </div>
          
          {/* Mini Sparkline */}
          <div className="mb-1 w-20 h-8">
             <Sparkline points={data.history || []} theme={theme} isRising={isUp} />
          </div>
        </div>
      </div>
    );
  }

  // --- RENDER: BUBBLE MODE (Market Cap / Revenue) ---
  // Adapting visual style from CompanyNode.tsx for Bubble mode
  
  const metric = nodeDisplayMode === 'marketCap' ? 'marketCap' : 'revenue';
  const value = metric === 'marketCap' ? data.marketCap : data.revenue;
  const numericValue = metric === 'marketCap' 
    ? (data.marketCapVal ?? (typeof data.marketCap === 'number' ? data.marketCap : 0))
    : (data.revenueVal ?? (typeof data.revenue === 'number' ? data.revenue : 0));
  
  // Default size if no value
  let circleSize = 100;
  
  if (numericValue && numericValue > 0 && allNodes.length > 0) {
    const values = allNodes
      .map((node) => {
        const val = metric === 'marketCap' 
          ? (node.data.marketCapVal ?? (typeof node.data.marketCap === 'number' ? node.data.marketCap : 0))
          : (node.data.revenueVal ?? (typeof node.data.revenue === 'number' ? node.data.revenue : 0));
        return val || 0;
      })
      .filter((v) => v > 0);

    if (values.length > 0) {
      const minValue = Math.min(...values);
      const maxValue = Math.max(...values);
      circleSize = calculateCircleRadius(numericValue, minValue, maxValue, 80, 160);
    }
  }

  // Colors
  const nodeColor = nodeColorMode === 'industry' 
    ? getIndustryColor(getIndustryFromTicker(data.ticker, data.category))
    : getCompanyColor(data.ticker);

  // Check if solid style is active
  const isSolid = nodeStyle === 'solid';

  const bubbleStyle = isSolid ? {
    backgroundColor: hexToRgba(nodeColor, 0.8),
    borderColor: nodeColor,
    color: 'white'
  } : {
    backgroundColor: theme === 'dark' ? 'rgba(15, 23, 42, 0.8)' : 'rgba(255, 255, 255, 0.9)',
    borderColor: nodeColor,
    color: theme === 'dark' ? 'white' : 'black'
  };

  // Add hover effect and selection ring
  const selectionRing = selected || isInOverlay ? `0 0 0 4px ${theme === 'dark' ? '#3730a3' : '#c7d2fe'}` : 'none';

  return (
    <div 
      className={`rounded-full border-4 flex flex-col items-center justify-center shadow-sm transition-all duration-200 cursor-pointer hover:scale-105 ${isDimmed ? 'opacity-40' : ''}`}
      style={{ 
        width: circleSize, 
        height: circleSize,
        ...bubbleStyle,
        boxShadow: selectionRing
      }}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}
      onClick={handleClick}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />
      
      <span className="text-xs font-bold text-center leading-tight px-2 mb-1 truncate w-full">{getStockLabel({ ticker: data.ticker, name: data.name }).primary}</span>
      <span className="text-base font-mono font-bold">
        {typeof value === 'string' ? value : formatLargeNumber(numericValue || 0)}
      </span>
      <span className="text-2xs uppercase opacity-80 font-bold tracking-wider mt-0.5">
        {metric === 'marketCap' ? 'Mkt Cap' : 'Revenue'}
      </span>
    </div>
  );
};
