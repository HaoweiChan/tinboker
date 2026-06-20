import React, { useMemo } from 'react';

interface SimpleSparklineProps {
  isPositive: boolean;
  className?: string;
  width?: number;
  height?: number;
  color?: string;        // Custom color for the line/area (overrides isPositive logic)
  data?: number[];       // Real data points (overrides generated mock data)
  smooth?: boolean;      // Smooth cubic-bezier curve instead of straight segments
  strokeWidth?: number;  // Line thickness (default 2)
  fill?: boolean;        // Render the gradient area fill under the line (default true)
}

interface Pt { x: number; y: number }

// Real data → normalized {x,y} points (10% vertical padding so peaks don't clip).
const normalizePoints = (data: number[], width: number, height: number): Pt[] => {
  if (data.length < 2) return [];
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const padded = height * 0.8;
  const pad = height * 0.1;
  return data.map((val, i) => ({
    x: i * stepX,
    y: height - (pad + ((val - min) / range) * padded),
  }));
};

// Generated 30-point mock trend (unchanged shape; used when no real data is supplied).
const mockPoints = (isPositive: boolean, width: number, height: number): Pt[] => {
  const n = 30;
  const stepX = width / (n - 1);
  const startY = isPositive ? height * 0.7 : height * 0.3;
  const endY = isPositive ? height * 0.1 : height * 0.9;
  return Array.from({ length: n }, (_, i) => {
    const baseY = startY + (endY - startY) * (i / (n - 1));
    const variation = Math.sin(i * 0.5) * height * 0.1;
    return { x: i * stepX, y: Math.max(0, Math.min(height, baseY + variation)) };
  });
};

const f = (n: number): string => n.toFixed(1);

// Straight path (visually identical to the old <polyline>).
const straightPath = (pts: Pt[]): string =>
  pts.length ? `M ${pts.map((p) => `${f(p.x)},${f(p.y)}`).join(' L ')}` : '';

// Catmull-Rom → cubic-bezier smoothing: gentle curves for sparse data, no overshoot.
const smoothPath = (pts: Pt[]): string => {
  if (pts.length < 3) return straightPath(pts);
  let d = `M ${f(pts[0].x)},${f(pts[0].y)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${f(c1x)},${f(c1y)} ${f(c2x)},${f(c2y)} ${f(p2.x)},${f(p2.y)}`;
  }
  return d;
};

export const SimpleSparkline: React.FC<SimpleSparklineProps> = ({
  isPositive,
  className = '',
  width = 60,
  height = 20,
  color: customColor,
  data,
  smooth = false,
  strokeWidth = 2,
  fill = true,
}) => {
  const { line, area } = useMemo(() => {
    const pts = data && data.length > 1
      ? normalizePoints(data, width, height)
      : mockPoints(isPositive, width, height);
    const linePath = smooth ? smoothPath(pts) : straightPath(pts);
    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPath = linePath && first && last
      ? `${linePath} L ${f(last.x)},${f(height)} L ${f(first.x)},${f(height)} Z`
      : '';
    return { line: linePath, area: areaPath };
  }, [data, isPositive, width, height, smooth]);

  // Custom color if provided, otherwise fall back to isPositive logic.
  const color = customColor || (isPositive ? '#22c55e' : '#ef4444'); // green-500 : red-500
  const gradientId = useMemo(
    () => `spark-${Math.random().toString(36).slice(2, 9)}`,
    [],
  );

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      preserveAspectRatio="none"
    >
      {fill && (
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
      )}

      {/* Area fill with gradient */}
      {fill && area && <path d={area} fill={`url(#${gradientId})`} stroke="none" />}

      {/* Line */}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};
