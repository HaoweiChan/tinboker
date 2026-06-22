import React, { useMemo, useState } from 'react';
import { getTreeMapData } from '@/services/mocks';
import type { TreeMapItem } from '@/services/types';
import TradingViewChart from '@/components/charts/TradingViewChart';
import { generateMockPriceSeries } from '@/services/mocks';
import { useAppStore } from '@/store/useAppStore';


// --- Helper: Color Logic (Finviz Style) ---
const getPerformanceColor = (change: number) => {
    // Finviz scale: Bright Green (+3%) to Bright Red (-3%)
    // We use a slightly softer palette for UI consistency
    if (change >= 3) return '#10b981'; // Bright Emerald
    if (change >= 1) return '#34d399'; // Soft Emerald
    if (change > 0) return '#6ee7b7'; // Light Emerald
    if (change === 0) return '#4b5563'; // Grey
    if (change <= -3) return '#ef4444'; // Bright Red
    if (change <= -1) return '#f87171'; // Soft Red
    return '#fca5a5'; // Light Red
};

// --- Component: Detailed Tooltip ---
const Tooltip = ({ item, position, isDark }: { item: TreeMapItem, position: { x: number, y: number }, isDark: boolean }) => {
    
    // Helper for sparkline in tooltip
    const Sparkline = ({ data }: { data: number[] }) => {
        const series = useMemo(() => {
            if (!data || data.length === 0) {
                return generateMockPriceSeries(18, 100);
            }
            const now = Date.now();
            return data.map((value, index) => ({
                time: new Date(now - (data.length - index) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
                value: Number(Number(value).toFixed(2)),
            }));
        }, [data]);

        return (
            <div className="w-full h-8">
                <TradingViewChart
                    data={series}
                    theme={isDark ? 'dark' : 'light'}
                    height={32}
                    lineColor="#ffffff"
                    topColor="rgba(255,255,255,0.5)"
                    bottomColor="transparent"
                    minimal
                    className="h-full w-full"
                />
            </div>
        );
    };

    // Determine positioning (prevent going off screen)
    const style: React.CSSProperties = {
        top: position.y + 10,
        left: position.x + 10,
        zIndex: 100
    };

    // Adjust if close to right edge
    if (window.innerWidth - position.x < 250) {
        style.left = position.x - 260;
    }

    return (
        <div className={`fixed shadow-2xl rounded-lg overflow-hidden w-64 border pointer-events-none animate-in fade-in zoom-in-95 duration-150 ${isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-slate-200'}`} style={style}>
            {/* Header */}
            <div className={`px-3 py-2 border-b ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-slate-100 border-slate-200'}`}>
                 <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                     {item.ticker ? 'Stock' : 'Sector'}
                 </div>
                 <h3 className={`font-bold text-base leading-tight ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{item.name}</h3>
            </div>

            {/* Body */}
            <div className="p-4" style={{ backgroundColor: getPerformanceColor(item.change) }}>
                 <div className="flex items-center justify-between text-white mb-2">
                     <span className="text-2xl font-bold">{item.ticker || 'IDX'}</span>
                     <div className="text-right">
                         <div className="text-xl font-bold leading-none">{item.change > 0 ? '+' : ''}{item.change.toFixed(2)}%</div>
                         <div className="text-xs opacity-80">{item.price ? `$${item.price}` : ''}</div>
                     </div>
                 </div>
                 
                 {item.history && (
                    <div className="mt-2 border-t border-white/30 pt-2">
                        <Sparkline data={item.history} />
                    </div>
                 )}
            </div>
            
            {/* Footer Stats */}
            <div className={`p-2 flex justify-between text-xs border-t ${isDark ? 'bg-slate-900 text-slate-400 border-slate-700' : 'bg-white text-slate-500 border-slate-100'}`}>
                <span>Mkt Cap: ${(item.value / 10).toFixed(1)}B</span>
                <span>Vol: 1.2M</span>
            </div>
        </div>
    );
};


// --- Component: Recursive Treemap Tile ---
interface TreeMapTileProps { 
    item: TreeMapItem; 
    depth?: number; 
    onHover: (item: TreeMapItem, e: React.MouseEvent) => void;
    onLeave: () => void;
    isDark: boolean;
}

const TreeMapTile: React.FC<TreeMapTileProps> = ({ 
    item, 
    depth = 0, 
    onHover, 
    onLeave,
    isDark
}) => {
    // Layout Logic:
    // We simulate squarified tiling by using Flexbox.
    // Items are given flex-grow based on their value.
    // This isn't a perfect squarified algorithm, but it creates a very similar "packed" effect for web.
    
    const isLeaf = !item.children || item.children.length === 0;
    const color = getPerformanceColor(item.change);

    if (isLeaf) {
        return (
            <div 
                className="relative border border-slate-900/10 overflow-hidden group transition-all duration-200 hover:z-10 hover:shadow-[0_0_0_2px_white]"
                style={{ 
                    flexGrow: item.value,
                    flexBasis: 'auto', // Allow grow to dominate
                    backgroundColor: color,
                    minWidth: item.value > 1000 ? '120px' : '80px',
                    minHeight: '60px'
                }}
                onMouseEnter={(e) => onHover(item, e)}
                onMouseMove={(e) => onHover(item, e)}
                onMouseLeave={onLeave}
            >
                <div className="absolute inset-0 flex flex-col items-center justify-center p-1 text-center">
                    <span className="text-white font-bold text-base drop-shadow-md leading-none truncate w-full">
                        {item.ticker}
                    </span>
                    {/* Only show percent if box is big enough */}
                    {item.value > 200 && (
                        <span className="text-white text-2xs font-medium drop-shadow-md mt-0.5">
                            {item.change > 0 ? '+' : ''}{item.change.toFixed(2)}%
                        </span>
                    )}
                </div>
            </div>
        );
    }

    // Non-Leaf (Sector/Industry)
    return (
        <div 
            className={`flex flex-col border overflow-hidden relative ${isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-900/5'}`}
            style={{ 
                flexGrow: item.value,
                flexBasis: '200px', // Minimum width for sectors
                minHeight: '250px'
            }}
        >
            {/* Header for Sector/Industry */}
            <div className={`border-b px-2 py-1 ${isDark ? 'bg-slate-800 border-white/10' : 'bg-slate-50 border-slate-200'}`}>
                <span className={`text-2xs font-bold uppercase tracking-wider truncate block ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    {item.name}
                </span>
            </div>
            
            {/* Container for children */}
            <div className="flex flex-wrap content-stretch h-full w-full">
                {item.children!.map((child) => (
                    <TreeMapTile 
                        key={child.id} 
                        item={child} 
                        depth={depth + 1} 
                        onHover={onHover}
                        onLeave={onLeave}
                        isDark={isDark}
                    />
                ))}
            </div>
        </div>
    );
};

interface TreeMapProps {
  variant?: 'standalone' | 'embedded';
}

const TreeMap: React.FC<TreeMapProps> = ({ variant = 'standalone' }) => {
    const data = useMemo(() => getTreeMapData(), []);
    const [hoveredItem, setHoveredItem] = useState<TreeMapItem | null>(null);
    const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
    const { theme } = useAppStore();
    const isDark = theme === 'dark';
    const isEmbedded = variant === 'embedded';

    const handleHover = (item: TreeMapItem, e: React.MouseEvent) => {
        setHoveredItem(item);
        setMousePos({ x: e.clientX, y: e.clientY });
    };

    const handleLeave = () => {
        setHoveredItem(null);
    };

    const legendTextClass = isDark ? 'text-slate-300' : 'text-slate-500';
    const Legend = (
      <div className={`flex gap-4 text-xs font-bold ${legendTextClass}`}>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-[#ef4444]" /> -3%
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-[#4b5563]" /> 0%
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-[#10b981]" /> +3%
        </div>
      </div>
    );

    const rootClasses = isEmbedded
      ? 'w-full h-full flex flex-col gap-4'
      : `w-full h-full p-4 overflow-hidden flex flex-col transition-colors ${isDark ? 'bg-slate-950' : 'bg-slate-100'}`;

    return (
        <div className={rootClasses}>
            {!isEmbedded && (
              <div className="flex justify-between items-center mb-2">
                <h1 className={`text-2xl font-bold ${isDark ? 'text-slate-50' : 'text-slate-800'}`}>S&P 500 Map</h1>
                {Legend}
              </div>
            )}

            {isEmbedded && (
              <div className="flex justify-end">{Legend}</div>
            )}

            {/* Map Container */}
            <div className={`flex-1 border shadow-sm flex flex-wrap content-stretch overflow-hidden rounded-2xl ${isDark ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-300'}`}>
                {/* We map the top level Sectors */}
                {data.map((sector) => (
                    <TreeMapTile 
                        key={sector.id} 
                        item={sector} 
                        onHover={handleHover} 
                        onLeave={handleLeave}
                        isDark={isDark}
                    />
                ))}
            </div>

            {/* Tooltip Portal */}
            {hoveredItem && <Tooltip item={hoveredItem} position={mousePos} isDark={isDark} />}
        </div>
    );
};

export default TreeMap;
