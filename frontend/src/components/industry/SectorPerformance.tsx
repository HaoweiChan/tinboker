import React, { useMemo, useState, useRef, useEffect } from 'react';
import type { CSSProperties } from 'react';
import { Play, Pause, Info, ChevronDown } from 'lucide-react';
import { getSectorBubbleData } from '@/services/mocks';
import type { SectorBubbleData } from '@/services/mocks/types';
import { resolveIcon } from '@/components/topics/SectorIcon';
import { TOPICS_TYPOGRAPHY } from '@/components/topics/topicsTypography';
import { useAppStore } from '@/store/useAppStore';
import { getIndustryColor } from '@/utils/industryColors';

/** Small ⓘ with a styled hover tooltip (for axis-metric / list help). */
function InfoHint({ text }: { text: string }) {
  const type = TOPICS_TYPOGRAPHY.className;
  return (
    <span className="relative inline-flex items-center group align-middle">
      <Info size={13} className="cursor-help text-slate-400" />
      <span
        className={`pointer-events-none absolute right-0 top-5 z-30 hidden w-56 rounded-md border p-2 ${type.micro} font-normal normal-case leading-relaxed shadow-xl group-hover:block`}
        style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
      >
        {text}
      </span>
    </span>
  );
}


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
  /** Live data: x = X magnitude, returnRate = Y %, r = bubble size.
   *  When omitted, falls back to mock data. */
  data?: SectorBubbleData[];
  /** Axis/tooltip labels. Defaults preserve the standalone mock chart. */
  xAxisLabel?: string;
  xTickSuffix?: string;
  xTooltipLabel?: string;
  xHelp?: string; // explanation shown on the legend ⓘ for the X metric
  yAxisLabel?: string;
  radiusTooltipLabel?: string;
  radiusTooltipSuffix?: string;
  /** Extra control rendered at the left of the embedded top bar (e.g. a timeframe toggle). */
  headerLeft?: React.ReactNode;
  /** Click a bubble or list row → open that sector/theme. */
  onSelectExposure?: (exposureId: string) => void;
}

type PlottedSectorBubble = SectorBubbleData & {
  anchorX: number;
  anchorY: number;
  plotX: number;
  plotY: number;
  radius: number;
};

const SectorPerformance: React.FC<SectorPerformanceProps> = ({
  variant = 'standalone',
  data,
  xAxisLabel = '市值（兆 NTD）',
  xTickSuffix = '兆',
  xTooltipLabel = '市值',
  xHelp,
  yAxisLabel = '近期漲跌 %',
  radiusTooltipLabel = '討論度',
  radiusTooltipSuffix = '',
  headerLeft,
  onSelectExposure,
}) => {
  const rawData = useMemo<SectorBubbleData[]>(() => data ?? getSectorBubbleData(), [data]);
  const [hoveredSectorId, setHoveredSectorId] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false); // mobile: ranked list collapsed by default
  const [timeValue] = useState(100);
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const isEmbedded = variant === 'embedded';
  const type = TOPICS_TYPOGRAPHY.className;

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

  // Dismiss active tooltip when user taps outside the bubble or tooltip on mobile
  useEffect(() => {
    if (!hoveredSectorId) return;

    const handleOutsideTouch = (e: TouchEvent | MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-bubble]') && !target.closest('[data-tooltip]')) {
        setHoveredSectorId(null);
      }
    };

    document.addEventListener('touchstart', handleOutsideTouch, { passive: true });
    document.addEventListener('mousedown', handleOutsideTouch);

    return () => {
      document.removeEventListener('touchstart', handleOutsideTouch);
      document.removeEventListener('mousedown', handleOutsideTouch);
    };
  }, [hoveredSectorId]);

  // Chart Dimensions — the viewBox tracks the panel's real pixel size (1:1) so the plot fills
  // the container at any aspect (no letterbox margins on tall mobile cards) and fonts/padding
  // render at their true px size. Falls back to 1000×500 before the panel is measured.
  const width = Math.max(panel.w || 1000, 320);
  const height = Math.max(panel.h || 500, 240);
  const padding = { top: 18, right: 26, bottom: 66, left: 90 };
  const graphWidth = width - padding.left - padding.right;
  const graphHeight = height - padding.top - padding.bottom;

  const xValue = (d: SectorBubbleData) => d.x ?? d.marketCap ?? d.value ?? 0;
  const radiusValue = (d: SectorBubbleData) => d.r ?? d.volume ?? 0;

  // Scales — derived from the data so live numbers and the mock both render sensibly
  // without hardcoded bounds.
  const xMax = Math.max(1, ...rawData.map(xValue)) * 1.1;
  const returns = rawData.map((d) => d.returnRate ?? 0);
  const rawYMax = Math.max(1, ...returns);
  const rawYMin = Math.min(0, ...returns);
  const yPad = Math.max(1, (rawYMax - rawYMin) * 0.15);
  const yMax = rawYMax + yPad;
  const yMin = rawYMin - yPad;
  const maxVol = Math.max(1, ...rawData.map(radiusValue));

  const xScale = (val: number) => (val / xMax) * graphWidth;
  const yScale = (val: number) => graphHeight - ((val - yMin) / (yMax - yMin)) * graphHeight;
  const rScale = (vol: number) => 6 + Math.sqrt(vol / maxVol) * 26; // bounded 6..32px

  const niceNum = (n: number) => (n >= 10 ? Math.round(n) : +n.toFixed(1));
  const xTicks = Array.from({ length: 6 }, (_, i) => niceNum((xMax * (i + 1)) / 6));
  const yTicks = Array.from({ length: 7 }, (_, i) => niceNum(yMin + ((yMax - yMin) * i) / 6));

  // px-based viewBox → fonts render at true px; use the Topics typography scale so
  // SVG text stays aligned with the surrounding page typography.
  const compact = width < 480;
  const chartText = compact ? TOPICS_TYPOGRAPHY.chart.compact : TOPICS_TYPOGRAPHY.chart.default;

  const plottedData = useMemo<PlottedSectorBubble[]>(() => {
    const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
    const maxShift = compact ? 12 : 20;
    const goldenAngle = 2.399963229728653;
    const clampToAnchor = (node: PlottedSectorBubble) => {
      const dx = node.plotX - node.anchorX;
      const dy = node.plotY - node.anchorY;
      const distance = Math.hypot(dx, dy);

      if (distance > maxShift) {
        const ratio = maxShift / distance;
        node.plotX = node.anchorX + dx * ratio;
        node.plotY = node.anchorY + dy * ratio;
      }

      node.plotX = clamp(node.plotX, node.radius, graphWidth - node.radius);
      node.plotY = clamp(node.plotY, node.radius, graphHeight - node.radius);
    };
    const nodes = rawData.map((item, index) => {
      const radius = rScale(radiusValue(item));
      const anchorX = xScale(xValue(item));
      const anchorY = yScale(item.returnRate || 0);
      const jitter = Math.min(5, radius * 0.2);
      const angle = index * goldenAngle;

      return {
        ...item,
        anchorX,
        anchorY,
        plotX: clamp(anchorX + Math.cos(angle) * jitter, radius, graphWidth - radius),
        plotY: clamp(anchorY + Math.sin(angle) * jitter, radius, graphHeight - radius),
        radius,
      };
    });

    // Visual-only de-overlap; axes, tooltip values, and sorting still use source data.
    for (let pass = 0; pass < 5; pass += 1) {
      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          const minDistance = (a.radius + b.radius) * 0.72 + 3;
          let dx = b.plotX - a.plotX;
          let dy = b.plotY - a.plotY;
          let distance = Math.hypot(dx, dy);

          if (!distance) {
            const angle = (i + j + 1) * goldenAngle;
            dx = Math.cos(angle);
            dy = Math.sin(angle);
            distance = 1;
          }

          if (distance >= minDistance) continue;

          const push = (minDistance - distance) / 2;
          const nx = dx / distance;
          const ny = dy / distance;

          a.plotX -= nx * push;
          a.plotY -= ny * push;
          b.plotX += nx * push;
          b.plotY += ny * push;

          clampToAnchor(a);
          clampToAnchor(b);
        }
      }

      for (const node of nodes) {
        node.plotX += (node.anchorX - node.plotX) * 0.18;
        node.plotY += (node.anchorY - node.plotY) * 0.18;
        clampToAnchor(node);
      }
    }

    return nodes;
  }, [compact, graphHeight, graphWidth, maxVol, rawData, xMax, yMax, yMin]);

  const containerClasses = ['w-full md:h-full flex flex-col overflow-hidden', isEmbedded ? '' : 'transition-colors duration-300']
    .filter(Boolean)
    .join(' ');
  const wrapperStyle: CSSProperties | undefined = isEmbedded
    ? undefined
    : { backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)' };
  const headerSurfaceStyle: CSSProperties = { backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)' };
  const sidebarStyle: CSSProperties = { backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-default)' };
  const legendTextColor = { color: 'var(--text-muted)' };

  // Legend: bubbles are coloured by sector/theme identity (icons disambiguate), so the only
  // non-axis encoding to explain is SIZE. Ascending dots = more of the radius metric.
  const legendContent = (
    <div className={`flex items-center gap-1.5 ${type.micro}`} style={legendTextColor}>
      <span className="whitespace-nowrap">{radiusTooltipLabel}</span>
      <span className="flex items-center gap-0.5">
        <span className="inline-block w-1.5 h-1.5 rounded-full border border-current opacity-70" />
        <span className="inline-block w-2.5 h-2.5 rounded-full border border-current opacity-70" />
        <span className="inline-block w-3.5 h-3.5 rounded-full border border-current opacity-70" />
      </span>
      {xHelp && <InfoHint text={xHelp} />}
    </div>
  );

  const handleBubbleClick = (e: React.MouseEvent, itemId: string) => {
    const isTouch = window.matchMedia('(pointer: coarse)').matches;
    if (isTouch) {
      if (hoveredSectorId !== itemId) {
        e.preventDefault();
        e.stopPropagation();
        setHoveredSectorId(itemId);
        return;
      }
    }
    onSelectExposure?.(itemId);
  };

  const handleRankedItemClick = (e: React.MouseEvent, itemId: string) => {
    const isTouch = window.matchMedia('(pointer: coarse)').matches;
    if (isTouch && hoveredSectorId !== itemId) {
      e.preventDefault();
      e.stopPropagation();
      setHoveredSectorId(itemId);
      return;
    }
    onSelectExposure?.(itemId);
  };

  return (
    <div className={containerClasses} style={wrapperStyle}>
      {!isEmbedded && (
        <div className="px-8 py-6 flex justify-between items-end border-b transition-colors" style={headerSurfaceStyle}>
          <div>
            <h1 className={`${type.pageTitle} font-bold mb-1`} style={{ color: 'var(--text-primary)' }}>Sector Performance</h1>
            <div className={`flex gap-2 ${type.body}`} style={{ color: 'var(--text-muted)' }}>
              <span className="text-indigo-500 hover:underline cursor-pointer">Home</span> 
              <span>/</span>
              <span>Industry</span>
            </div>
          </div>
          {legendContent}
        </div>
      )}

      {isEmbedded && (
        <div className="px-3 pt-2.5 pb-1.5 flex items-center justify-between gap-2">
          <div className="shrink-0">{headerLeft}</div>
          <div className="min-w-0 shrink">{legendContent}</div>
        </div>
      )}

      {/* Main Content — chart on top of the list on mobile, side-by-side on desktop */}
      <div className="flex flex-col md:flex-row md:flex-1 md:overflow-hidden md:min-h-0">

        {/* Chart Area */}
        <div className="relative px-2 pb-2 sm:px-3 sm:pb-3 h-[340px] md:h-auto md:flex-1 md:min-h-0">
           <div
             ref={panelRef}
             className="w-full h-full relative overflow-hidden"
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
                            <text x={-10} y={y} dy={4} textAnchor="end" fill="#94a3b8" fontSize={chartText.tick}>{tick}%</text>
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
                            <text x={x} y={graphHeight + 20} textAnchor="middle" fill="#94a3b8" fontSize={chartText.tick}>{tick}{xTickSuffix}</text>
                          </g>
                        );
                    })}

                    {/* Axis Labels */}
                    <text x={-70} y={graphHeight/2} transform={`rotate(-90, -70, ${graphHeight/2})`} textAnchor="middle" fill="#94a3b8" fontSize={chartText.axis} fontWeight="600">
                        {yAxisLabel}
                    </text>
                    <text x={graphWidth/2} y={graphHeight + 52} textAnchor="middle" fill="#94a3b8" fontSize={chartText.axis} fontWeight="600">
                        {xAxisLabel}
                    </text>


                   {/* Bubbles */}
                   {plottedData.map((item) => {
                      const x = item.plotX;
                      const y = item.plotY;
                      const r = item.radius;
                      const activeId = hoveredSectorId;
                      const isActive = activeId === item.id;
                      const visuals = getBubbleVisuals(item.label || '', item.returnRate || 0, isDark);

                      return (
                         <g
                            key={item.id}
                            data-bubble="true"
                            transform={`translate(${x}, ${y})`}
                            className="transition-all duration-300 cursor-pointer group"
                            onMouseEnter={() => setHoveredSectorId(item.id)}
                            onMouseLeave={() => setHoveredSectorId(null)}
                            onClick={(e) => handleBubbleClick(e, item.id)}
                            style={{ opacity: activeId && !isActive ? 0.3 : 1 }}
                         >
                            <circle
                              r={r}
                              fill={visuals.fill}
                              stroke={isActive ? (isDark ? '#fff' : '#0f172a') : visuals.baseColor}
                              strokeWidth={isActive ? 2 : 1.5}
                              style={{ filter: `drop-shadow(0 12px 24px ${visuals.glow})` }}
                            />
                            {/* Icon — disambiguates bubbles that share a color */}
                            {r >= 12 && (() => {
                              const Icon = resolveIcon(item.id, item.icon_id);
                              const s = Math.min(Math.round(r * 1.05), 26);
                              return (
                                <g transform={`translate(${-s / 2}, ${-s / 2})`} className="pointer-events-none">
                                  <Icon width={s} height={s} color={isDark ? '#f1f5f9' : '#1e293b'} strokeWidth={2.4} />
                                </g>
                              );
                            })()}
                         </g>
                       );
                    })}

                 </g>
              </svg>

              {/* Hover/tap info — anchored at the bubble's pixel position (computed from the
                  panel size + preserveAspectRatio='meet' letterboxing). */}
              {(() => {
                  const activeId = hoveredSectorId;
                  if (!activeId || !panel.w || !panel.h) return null;
                  const s = plottedData.find((i) => i.id === activeId);
                  if (!s) return null;
                  const scale = Math.min(panel.w / width, panel.h / height);
                  const ox = (panel.w - width * scale) / 2;
                  const oy = (panel.h - height * scale) / 2;
                  const px = ox + (padding.left + s.plotX) * scale;
                  const py = oy + (padding.top + s.plotY) * scale;
                  const CARD_W = 168;
                  const flipX = px + 14 + CARD_W > panel.w;
                  const left = flipX ? px - 14 - CARD_W : px + 14;
                  return (
                    <div
                      data-tooltip="true"
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
                       <h3 className={`${type.sectionTitle} font-bold truncate`} style={{ color: 'var(--text-primary)' }}>{s.label}</h3>
                       {s.subLabel && (
                         <div className={`${type.micro} mb-1.5`} style={{ color: 'var(--text-muted)' }}>{s.subLabel}</div>
                       )}
                       <div className={`grid grid-cols-2 gap-x-3 gap-y-1 ${type.meta} ${s.subLabel ? '' : 'mt-1.5'}`}>
                          <span style={{ color: 'var(--text-muted)' }}>{xTooltipLabel}</span>
                          <span className="text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{xValue(s)}{xTickSuffix}</span>

                          <span style={{ color: 'var(--text-muted)' }}>漲跌</span>
                          <span className={`text-right font-mono font-bold ${(s.returnRate || 0) > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {(s.returnRate || 0) > 0 ? '+' : ''}{s.returnRate || 0}%
                          </span>

                          <span style={{ color: 'var(--text-muted)' }}>{radiusTooltipLabel}</span>
                          <span className="text-right font-mono" style={{ color: 'var(--text-secondary)' }}>{radiusValue(s)}{radiusTooltipSuffix}</span>
                       </div>
                    </div>
                  );
              })()}

           </div>
        </div>

        {/* Selection list — below the chart on mobile, right sidebar on desktop */}
        <div className="w-full md:w-64 shrink-0 border-t md:border-t-0 md:border-l flex flex-col min-h-0 transition-colors md:h-auto" style={sidebarStyle}>
            <button
              type="button"
              onClick={() => setListOpen((o) => !o)}
              className="p-3 md:p-4 border-b flex items-center justify-between gap-2 text-left md:cursor-default"
              style={{ borderColor: 'var(--border-default)' }}
            >
               <span className="flex items-center gap-2">
                 <span className={`${type.meta} font-bold text-slate-500 uppercase tracking-wider`}>依漲跌排序</span>
                 <InfoHint text="依所選漲跌期間的漲跌幅，由高到低排序。點任一項可在圖上標示對應泡泡。" />
               </span>
               <ChevronDown size={16} className={`md:hidden text-slate-400 transition-transform ${listOpen ? 'rotate-180' : ''}`} />
            </button>
            <div className={`overflow-y-auto p-2 space-y-1 scrollbar-thin max-h-[45vh] md:max-h-none md:flex-1 md:block ${listOpen ? 'block' : 'hidden'}`}>
               {[...rawData].sort((a,b) => (b.returnRate || 0) - (a.returnRate || 0)).map(item => {
                 const visuals = getBubbleVisuals(item.label || '', item.returnRate || 0, isDark);
                 const RowIcon = resolveIcon(item.id, item.icon_id);
                 return (
                   <div
                      key={item.id}
                      onClick={(e) => handleRankedItemClick(e, item.id)}
                      onMouseEnter={() => setHoveredSectorId(item.id)}
                      onMouseLeave={() => setHoveredSectorId(null)}
                      className={`flex items-center gap-2.5 p-2 rounded cursor-pointer transition-colors ${
                          hoveredSectorId === item.id
                              ? (isDark ? 'bg-indigo-900/30 border border-indigo-800' : 'bg-indigo-50 border border-indigo-100')
                              : (isDark ? 'hover:bg-slate-800 border border-transparent' : 'hover:bg-white border border-transparent')
                      }`}
                   >
                      <span
                        className="grid place-items-center w-6 h-6 rounded-md flex-shrink-0"
                        style={{ color: visuals.baseColor, backgroundColor: `${visuals.baseColor}22` }}
                      >
                        <RowIcon size={14} />
                      </span>
                      <span className={`${type.chartRow} truncate flex-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{item.label}</span>
                      <span className={`${type.meta} font-mono ${(item.returnRate || 0) > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
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
                    className={`absolute right-0 -top-8 ${type.meta} font-bold px-2 py-1 rounded shadow-lg transform -translate-x-1/2`}
                    style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)' }}
                  >
                     2025-09-24
                  </div>
               </div>
            </div>
         </div>
         
         <div className={`${type.meta} font-mono text-slate-400 w-24 text-right`}>
            LIVE DATA
         </div>
      </div>
      )}

    </div>
  );
};

export default SectorPerformance;
