import React, { useMemo, useState, useRef, useEffect } from 'react';
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
  yAxisLabel?: string;
  radiusTooltipLabel?: string;
  radiusTooltipSuffix?: string;
}

const SectorPerformance: React.FC<SectorPerformanceProps> = ({
  variant = 'standalone',
  data,
  xAxisLabel = '市值（兆 NTD）',
  xTickSuffix = '兆',
  xTooltipLabel = '市值',
  yAxisLabel = '近期漲跌 %',
  radiusTooltipLabel = '討論度',
  radiusTooltipSuffix = '',
}) => {
  const rawData = useMemo<SectorBubbleData[]>(() => data ?? getSectorBubbleData(), [data]);
  const [selectedSectorId, setSelectedSectorId] = useState<string | null>(null);
  const [hoveredSectorId, setHoveredSectorId] = useState<string | null>(null);
  const [timeValue] = useState(100);
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const isEmbedded = variant === 'embedded';

  // Track the chart panel's pixel size so the hover tooltip (an HTML overlay) can be
  // placed at the bubble's pixel position — readable at any SVG scale, unlike in-SVG text.
  const panelRef = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = panelRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setPanel({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Chart Dimensions — generous left/bottom padding so the rotated Y title and the X title
  // sit clear of the tick labels (the cramped 60px gutter made them collide).
  const width = 1000;
  const height = 500;
  const padding = { top: 30, right: 40, bottom: 78, left: 96 };
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

      {/* Main Content — chart on top of the list on mobile, side-by-side on desktop */}
      <div className="flex flex-1 overflow-hidden min-h-0 flex-col md:flex-row">

        {/* Chart Area */}
        <div className="flex-1 min-h-0 relative p-3 sm:p-4">
           <div
             ref={panelRef}
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
                            <text x={-10} y={y} dy={4} textAnchor="end" fill="#94a3b8" fontSize="16">{tick}%</text>
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
                            <text x={x} y={graphHeight + 22} textAnchor="middle" fill="#94a3b8" fontSize="16">{tick}{xTickSuffix}</text>
                          </g>
                        );
                    })}

                    {/* Axis Labels */}
                    <text x={-74} y={graphHeight/2} transform={`rotate(-90, -74, ${graphHeight/2})`} textAnchor="middle" fill="#94a3b8" fontSize="19" fontWeight="600">
                        {yAxisLabel}
                    </text>
                    <text x={graphWidth/2} y={graphHeight + 62} textAnchor="middle" fill="#94a3b8" fontSize="19" fontWeight="600">
                        {xAxisLabel}
                    </text>


                   {/* Bubbles */}
                   {rawData.map((item) => {
                      const x = xScale(item.marketCap || 0);
                      const y = yScale(item.returnRate || 0);
                      const r = rScale(item.volume || 10);
                      const activeId = hoveredSectorId ?? selectedSectorId;
                      const isActive = activeId === item.id;
                      const visuals = getBubbleVisuals(item.label || '', item.returnRate || 0, isDark);

                      return (
                         <g
                            key={item.id}
                            transform={`translate(${x}, ${y})`}
                            className="transition-all duration-300 cursor-pointer group"
                            onMouseEnter={() => setHoveredSectorId(item.id)}
                            onMouseLeave={() => setHoveredSectorId(null)}
                            onClick={() => setSelectedSectorId(item.id === selectedSectorId ? null : item.id)}
                            style={{ opacity: activeId && !isActive ? 0.3 : 1 }}
                         >
                            <circle
                              r={r}
                              fill={visuals.fill}
                              stroke={isActive ? (isDark ? '#fff' : '#0f172a') : visuals.baseColor}
                              strokeWidth={isActive ? 2 : 1.5}
                              style={{ filter: `drop-shadow(0 12px 24px ${visuals.glow})` }}
                            />
                            {/* Label */}
                            {(r > 20 || isActive) && (
                                <text 
                                  textAnchor="middle" 
                                  dy={-r - 5} 
                                  fill={isDark ? '#e2e8f0' : '#334155'} 
                                  fontSize="18" 
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

              {/* Hover/tap info — anchored at the bubble's pixel position (computed from the
                  panel size + preserveAspectRatio='meet' letterboxing). */}
              {(() => {
                  const activeId = hoveredSectorId ?? selectedSectorId;
                  if (!activeId || !panel.w || !panel.h) return null;
                  const s = rawData.find((i) => i.id === activeId);
                  if (!s) return null;
                  const scale = Math.min(panel.w / width, panel.h / height);
                  const ox = (panel.w - width * scale) / 2;
                  const oy = (panel.h - height * scale) / 2;
                  const px = ox + (padding.left + xScale(s.marketCap || 0)) * scale;
                  const py = oy + (padding.top + yScale(s.returnRate || 0)) * scale;
                  const CARD_W = 168;
                  const flipX = px + 14 + CARD_W > panel.w;
                  const left = flipX ? px - 14 - CARD_W : px + 14;
                  return (
                    <div
                      className="absolute z-10 pointer-events-none backdrop-blur border p-3 rounded-lg shadow-xl"
                      style={{
                        left: Math.max(4, Math.min(left, panel.w - CARD_W - 4)),
                        top: py,
                        width: CARD_W,
                        transform: 'translateY(-50%)',
                        backgroundColor: 'var(--bg-surface)',
                        borderColor: 'var(--border-default)',
                      }}
                    >
                       <h3 className="text-sm font-bold truncate" style={{ color: 'var(--text-primary)' }}>{s.label}</h3>
                       {s.subLabel && (
                         <div className="text-2xs mb-1.5" style={{ color: 'var(--text-muted)' }}>{s.subLabel}</div>
                       )}
                       <div className={`grid grid-cols-2 gap-x-3 gap-y-1 text-xs ${s.subLabel ? '' : 'mt-1.5'}`}>
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
                  );
              })()}

           </div>
        </div>

        {/* Selection list — below the chart on mobile, right sidebar on desktop */}
        <div className="w-full md:w-64 h-[42%] md:h-auto shrink-0 border-t md:border-t-0 md:border-l flex flex-col min-h-0 transition-colors" style={sidebarStyle}>
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
                      onMouseEnter={() => setHoveredSectorId(item.id)}
                      onMouseLeave={() => setHoveredSectorId(null)}
                      className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
                          (hoveredSectorId ?? selectedSectorId) === item.id
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

