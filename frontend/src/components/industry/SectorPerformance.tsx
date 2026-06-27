import React, { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Play, Pause, Info } from 'lucide-react';
import { getSectorBubbleData } from '@/services/mocks';
import type { SectorBubbleData } from '@/services/mocks/types';
import { useAppStore } from '@/store/useAppStore';
import { getIndustryColor } from '@/utils/industryColors';


const hexToRgb = (hex: string) => {
  const normalized = hex.replace('#', '');
  const formatted = normalized.length === 3 ? normalized.split('').map((char) => char + char).join('') : normalized;
  const parsed = parseInt(formatted, 16);
  return {
    r: (parsed >> 16) & 255,
    g: (parsed >> 8) & 255,
    b: parsed & 255,
  };
};

const toRgba = (hex: string, alpha: number) => {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

const getBubbleVisuals = (label: string, returnRate: number, isDark: boolean) => {
  const baseColor = getIndustryColor(label);
  const magnitude = Math.min(Math.abs(returnRate) / 35, 1);
  const alphaBase = isDark ? 0.35 : 0.4;
  const fill = toRgba(baseColor, alphaBase + magnitude * 0.35);
  const glow = toRgba(baseColor, isDark ? 0.35 : 0.25);
  return { baseColor, fill, glow };
};

interface SectorPerformanceProps {
  variant?: 'standalone' | 'embedded';
  /** Live data: marketCap = X magnitude, returnRate = Y %, volume = bubble size.
   *  When omitted, falls back to mock data. */
  data?: SectorBubbleData[];
  /** Axis/tooltip labels — defaults frame X as market cap (產業 tab). The 題材 tab
   *  overrides them to frame X as discussion volume and the bubble as money flow. */
  xAxisLabel?: string;
  xTickSuffix?: string;
  xTooltipLabel?: string;
  radiusTooltipLabel?: string;
  radiusTooltipSuffix?: string;
}

const SectorPerformance: React.FC<SectorPerformanceProps> = ({
  variant = 'standalone',
  data,
  xAxisLabel = '市值（兆 NTD）',
  xTickSuffix = '兆',
  xTooltipLabel = '市值',
  radiusTooltipLabel = '討論度',
  radiusTooltipSuffix = '',
}) => {
  const rawData = useMemo<SectorBubbleData[]>(() => data ?? getSectorBubbleData(), [data]);
  const [selectedSectorId, setSelectedSectorId] = useState<string | null>(null);
  const [timeValue] = useState(100); 
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const isEmbedded = variant === 'embedded';

  // Chart Dimensions
  const width = 1000;
  const height = 500;
  const padding = { top: 40, right: 60, bottom: 60, left: 60 };
  const graphWidth = width - padding.left - padding.right;
  const graphHeight = height - padding.top - padding.bottom;

  // Scales — derived from the data so live numbers (兆 NTD market caps, small daily
  // returns) and the mock both render sensibly without hardcoded bounds.
  const maxCap = Math.max(1, ...rawData.map((d) => d.marketCap ?? 0));
  const xMax = maxCap * 1.1;
  const returns = rawData.map((d) => d.returnRate ?? 0);
  const rawYMax = Math.max(1, ...returns);
  const rawYMin = Math.min(0, ...returns);
  const yPad = Math.max(1, (rawYMax - rawYMin) * 0.15);
  const yMax = rawYMax + yPad;
  const yMin = rawYMin - yPad;
  const maxVol = Math.max(1, ...rawData.map((d) => d.volume ?? 0));

  const xScale = (val: number) => (val / xMax) * graphWidth;
  const yScale = (val: number) => graphHeight - ((val - yMin) / (yMax - yMin)) * graphHeight;
  const rScale = (vol: number) => 6 + Math.sqrt(vol / maxVol) * 26; // bounded 6..32px

  const niceNum = (n: number) => (n >= 10 ? Math.round(n) : +n.toFixed(1));
  const xTicks = Array.from({ length: 6 }, (_, i) => niceNum((xMax * (i + 1)) / 6));
  const yTicks = Array.from({ length: 7 }, (_, i) => niceNum(yMin + ((yMax - yMin) * i) / 6));

  const containerClasses = ['w-full h-full flex flex-col overflow-hidden', isEmbedded ? '' : 'transition-colors duration-300']
    .filter(Boolean)
    .join(' ');
  const wrapperStyle: CSSProperties | undefined = isEmbedded
    ? undefined
    : { backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)' };
  const headerSurfaceStyle: CSSProperties = { backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)' };
  const chartPanelStyle: CSSProperties = { backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border-default)' };
  const sidebarStyle: CSSProperties = { backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)' };
  const legendTextColor = { color: 'var(--text-muted)' };

  const legendContent = (
    <div className="flex flex-col items-end gap-1">
      <div className="flex justify-between w-48 text-2xs uppercase tracking-wider" style={legendTextColor}>
         <span>漲跌 %</span>
         <span>{xTooltipLabel}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="w-32 h-2 rounded-full bg-gradient-to-r from-red-400 via-slate-300 to-green-400" />
        <div className="flex items-center gap-1">
           <div className="w-2 h-2 rounded-full border border-slate-400" />
           <div className="w-3 h-3 rounded-full border border-slate-400" />
           <div className="w-4 h-4 rounded-full border border-slate-400" />
        </div>
      </div>
    </div>
  );

  return (
    <div className={containerClasses} style={wrapperStyle}>
      {!isEmbedded && (
        <div className="px-8 py-6 flex justify-between items-end border-b transition-colors" style={headerSurfaceStyle}>
          <div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>Sector Performance</h1>
            <div className="flex gap-2 text-base" style={{ color: 'var(--text-muted)' }}>
              <span className="text-indigo-500 hover:underline cursor-pointer">Home</span> 
              <span>/</span>
              <span>Industry</span>
            </div>
          </div>
          {legendContent}
        </div>
      )}

      {isEmbedded && (
        <div className="px-4 pt-4 flex justify-end">
          {legendContent}
        </div>
      )}

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* Chart Area */}
        <div className="flex-1 relative p-4">
           <div
             className="w-full h-full relative border rounded-lg overflow-hidden shadow-sm transition-colors"
             style={chartPanelStyle}
           >
              
              {/* SVG Container */}
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
                 <g transform={`translate(${padding.left}, ${padding.top})`}>
                    
                    {/* Grid Lines Y */}
                    {yTicks.map((tick) => {
                        const y = yScale(tick);
                        return (
                          <g key={tick}>
                            <line x1={0} y1={y} x2={graphWidth} y2={y} stroke={isDark ? '#334155' : '#e2e8f0'} strokeDasharray="4 4" />
                            <text x={-10} y={y} dy={4} textAnchor="end" fill="#94a3b8" fontSize="10">{tick}%</text>
                          </g>
                        );
                    })}
                    {/* Zero Line */}
                    <line x1={0} y1={yScale(0)} x2={graphWidth} y2={yScale(0)} stroke="#94a3b8" strokeWidth="1" />

                    {/* Grid Lines X */}
                    {xTicks.map((tick) => {
                        const x = xScale(tick);
                        return (
                          <g key={tick}>
                            <line x1={x} y1={0} x2={x} y2={graphHeight} stroke={isDark ? '#334155' : '#e2e8f0'} strokeDasharray="4 4" />
                            <text x={x} y={graphHeight + 20} textAnchor="middle" fill="#94a3b8" fontSize="10">{tick}{xTickSuffix}</text>
                          </g>
                        );
                    })}

                    {/* Axis Labels */}
                    <text x={-40} y={graphHeight/2} transform={`rotate(-90, -40, ${graphHeight/2})`} textAnchor="middle" fill="#64748b" fontSize="12" fontWeight="bold">
                        近期漲跌 %
                    </text>
                    <text x={graphWidth - 20} y={graphHeight + 40} textAnchor="end" fill="#64748b" fontSize="12" fontWeight="bold">
                        {xAxisLabel}
                    </text>


                   {/* Bubbles */}
                   {rawData.map((item) => {
                      const x = xScale(item.marketCap || 0);
                      const y = yScale(item.returnRate || 0);
                      const r = rScale(item.volume || 10);
                      const isSelected = selectedSectorId === item.id;
                      const visuals = getBubbleVisuals(item.label || '', item.returnRate || 0, isDark);
                      
                      // Determine text color based on bubble size/theme if inside bubble, or use contrast
                      // For simplicity, we use dark text for bright bubbles or fallback
                      
                      return (
                         <g 
                            key={item.id} 
                            transform={`translate(${x}, ${y})`}
                            className="transition-all duration-500 cursor-pointer group"
                            onClick={() => setSelectedSectorId(item.id)}
                            style={{ opacity: selectedSectorId && !isSelected ? 0.3 : 1 }}
                         >
                            <circle 
                              r={r} 
                              fill={visuals.fill}
                              stroke={isSelected ? (isDark ? '#fff' : '#0f172a') : visuals.baseColor}
                              strokeWidth={isSelected ? 2 : 1.5}
                              style={{ filter: `drop-shadow(0 12px 24px ${visuals.glow})` }}
                            />
                            {/* Label */}
                            {(r > 20 || isSelected) && (
                                <text 
                                  textAnchor="middle" 
                                  dy={-r - 5} 
                                  fill={isDark ? '#e2e8f0' : '#334155'} 
                                  fontSize="12" 
                                  fontWeight="bold"
                                  className="pointer-events-none"
                                >
                                    {item.label}
                                </text>
                            )}
                         </g>
                       );
                    })}

                 </g>
              </svg>

              {/* Tooltip / Info Overlay */}
              <div className="absolute top-4 left-4">
                  {selectedSectorId && (() => {
                      const s = rawData.find(i => i.id === selectedSectorId);
                      if (!s) return null;
                      return (
                        <div
                          className="backdrop-blur border p-4 rounded-lg shadow-xl"
                          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)' }}
                        >
                           <h3 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>{s.label}</h3>
                           <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-base">
                              <span style={{ color: 'var(--text-muted)' }}>{xTooltipLabel}</span>
                              <span className="text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{s.marketCap}{xTickSuffix}</span>

                              <span style={{ color: 'var(--text-muted)' }}>漲跌</span>
                              <span className={`text-right font-mono font-bold ${(s.returnRate || 0) > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                {(s.returnRate || 0) > 0 ? '+' : ''}{s.returnRate || 0}%
                              </span>

                              <span style={{ color: 'var(--text-muted)' }}>{radiusTooltipLabel}</span>
                              <span className="text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{s.volume}{radiusTooltipSuffix}</span>
                           </div>
                        </div>
                      )
                  })()}
              </div>

           </div>
        </div>

        {/* Right Sidebar: Selection List */}
        <div className="w-64 border-l flex flex-col transition-colors" style={sidebarStyle}>
            <div className="p-4 border-b flex justify-between items-center" style={{ borderColor: 'var(--border-default)' }}>
               <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">依漲跌排序</span>
               <Info size={14} className="text-slate-400" />
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
               {[...rawData].sort((a,b) => (b.returnRate || 0) - (a.returnRate || 0)).map(item => {
                 const visuals = getBubbleVisuals(item.label || '', item.returnRate || 0, isDark);
                 return (
                   <div 
                      key={item.id}
                      onClick={() => setSelectedSectorId(item.id === selectedSectorId ? null : item.id)}
                      className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
                          selectedSectorId === item.id 
                              ? (isDark ? 'bg-indigo-900/30 border border-indigo-800' : 'bg-indigo-50 border border-indigo-100')
                              : (isDark ? 'hover:bg-slate-800 border border-transparent' : 'hover:bg-white border border-transparent')
                      }`}
                   >
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{
                          backgroundColor: visuals.baseColor,
                          boxShadow: `0 0 10px ${visuals.glow}`,
                        }}
                      />
                      <span className={`text-base truncate flex-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{item.label}</span>
                      <span className={`text-xs font-mono ${(item.returnRate || 0) > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                          {item.returnRate || 0}%
                      </span>
                   </div>
                 );
               })}
            </div>
        </div>
      </div>

      {/* Bottom Controls (Slider) — mock playback; hidden for live data */}
      {!data && (
      <div className="h-16 border-t px-8 flex items-center gap-6 transition-colors" style={headerSurfaceStyle}>
         <button className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${isDark ? 'bg-slate-800 hover:bg-slate-700 text-slate-300' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}`}>
            {timeValue < 100 ? <Play size={18} fill="currentColor" /> : <Pause size={18} fill="currentColor" />}
         </button>
         
         <div className="flex-1 relative">
            <div className="h-1 rounded-full w-full" style={{ backgroundColor: 'var(--border-default)' }}>
               <div className="h-full bg-indigo-500 rounded-full relative" style={{ width: `${timeValue}%` }}>
                  <div className={`absolute right-0 top-1/2 -translate-y-1/2 w-4 h-4 bg-indigo-500 rounded-full shadow-lg transform scale-125 cursor-grab border-2 ${isDark ? 'border-slate-900' : 'border-white'}`} />
                  <div
                    className="absolute right-0 -top-8 text-xs font-bold px-2 py-1 rounded shadow-lg transform -translate-x-1/2"
                    style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)' }}
                  >
                     2025-09-24
                  </div>
               </div>
            </div>
         </div>
         
         <div className="text-xs font-mono text-slate-400 w-24 text-right">
            LIVE DATA
         </div>
      </div>
      )}

    </div>
  );
};

export default SectorPerformance;

