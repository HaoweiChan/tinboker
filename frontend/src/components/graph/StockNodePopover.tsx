import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, X } from 'lucide-react';
import { useViewport } from 'reactflow';
import type { Node } from 'reactflow';
import type { StockNodeData } from '@/services/types';
import { useAppStore } from '@/store/useAppStore';
import { getStockLabel } from '@/utils/stockDisplay';

type PopoverVariant = 'standard' | 'compact';

interface StockNodePopoverProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  nodes: Node[];
  disabled?: boolean;
  variant?: PopoverVariant;
}

interface PopoverData {
  nodeId: string;
  ticker: string;
  title: string;
  subtitle?: string;
  price?: number | string;
  changePct?: number;
  status?: string;
  marketCap?: number | string;
  revenue?: number | string;
  position: { x: number; y: number };
  dimensions: { width: number; height: number };
}

const formatCurrencyValue = (value?: number | string) => {
  const numeric =
    typeof value === 'string'
      ? Number(value.replace(/[^0-9.-]/g, ''))
      : typeof value === 'number'
        ? value
        : null;
  if (numeric === null || Number.isNaN(numeric)) {
    return '$0.00';
  }
  return numeric.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

const formatPercentValue = (value?: number) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '+0.00%';
  }
  const percentage = (value * 100).toFixed(2);
  const sign = value >= 0 ? '+' : '';
  return `${sign}${percentage}%`;
};

const formatMetricValue = (value?: number | string) => {
  if (value === undefined || value === null || value === '') {
    return '—';
  }
  const numeric =
    typeof value === 'string'
      ? Number(value.replace(/[^0-9.-]/g, ''))
      : typeof value === 'number'
        ? value
        : null;
  if (numeric === null || Number.isNaN(numeric)) {
    return typeof value === 'string' ? value : '—';
  }
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(numeric);
};

const getStatusToken = (status?: string) => {
  if (!status) {
    return {
      label: '中性',
      className:
        'bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-500/20 dark:text-slate-200 dark:border-slate-600',
    };
  }
  const normalized = status.toLowerCase();
  if (normalized.includes('risk')) {
    return {
      label: '風險',
      className:
        'bg-rose-100 text-rose-600 border border-rose-200 dark:bg-rose-500/20 dark:text-rose-200 dark:border-rose-500/40',
    };
  }
  if (normalized.includes('pending')) {
    return {
      label: '待定',
      className:
        'bg-accent-info-soft text-accent-info border border-accent-info-soft dark:bg-accent-info/20 dark:text-accent-info-soft dark:border-accent-info/40',
    };
  }
  if (normalized.includes('stable')) {
    return {
      label: '穩定',
      className:
        'bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-500/20 dark:text-slate-100 dark:border-slate-600',
    };
  }
  return {
    label: '活躍',
    className:
      'bg-emerald-100 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-200 dark:border-emerald-500/40',
  };
};

export const StockNodePopover: React.FC<StockNodePopoverProps> = ({
  containerRef,
  nodes,
  disabled = false,
  variant = 'standard',
}) => {
  const navigate = useNavigate();
  const { x: viewportX, y: viewportY, zoom } = useViewport();
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setSelectedCompany = useAppStore((state) => state.setSelectedCompany);
  const isDark = useAppStore((state) => state.theme === 'dark');
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [popoverData, setPopoverData] = useState<PopoverData | null>(null);
  const [domBounds, setDomBounds] = useState<{ nodeRect: DOMRect; containerRect: DOMRect } | null>(null);

  useEffect(() => {
    if (!selectedCompany || disabled) {
      setPopoverData(null);
      setDomBounds(null);
      return;
    }
    const matchingNode = nodes.find((node: Node) => {
      const data = node.data as StockNodeData | undefined;
      if (!data?.ticker) {
        return false;
      }
      return data.ticker.toLowerCase() === selectedCompany.toLowerCase();
    });

    if (!matchingNode) {
      setPopoverData(null);
      setDomBounds(null);
      return;
    }

    const nodeData = matchingNode.data as StockNodeData;
    if (!nodeData.ticker) {
      setPopoverData(null);
      setDomBounds(null);
      return;
    }

    const basePosition = matchingNode.positionAbsolute || matchingNode.position || { x: 0, y: 0 };
    setPopoverData({
      nodeId: matchingNode.id,
      ticker: nodeData.ticker,
      title: nodeData.name || nodeData.label || nodeData.ticker,
      subtitle: nodeData.category,
      price: nodeData.price,
      changePct: nodeData.changePct,
      status: nodeData.status,
      marketCap: nodeData.marketCapVal ?? nodeData.marketCap,
      revenue: nodeData.revenueVal ?? nodeData.revenue,
      position: basePosition,
      dimensions: {
        width: typeof matchingNode.width === 'number' ? matchingNode.width : 220,
        height: typeof matchingNode.height === 'number' ? matchingNode.height : 120,
      },
    });
  }, [selectedCompany, disabled, nodes]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (!selectedCompany) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (!target) {
        return;
      }
      if (target.closest('.react-flow__node')) {
        return;
      }
      if (popoverRef.current && popoverRef.current.contains(target)) {
        return;
      }
      setSelectedCompany(null);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [selectedCompany, setSelectedCompany]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelectedCompany(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setSelectedCompany]);

  useEffect(() => {
    return () => {
      setSelectedCompany(null);
    };
  }, [setSelectedCompany]);

  useEffect(() => {
    if (!popoverData || !containerRef.current) {
      setDomBounds(null);
      return;
    }
    const containerEl = containerRef.current;
    const nodeElement = containerEl.querySelector(`[data-id="${popoverData.nodeId}"]`);
    if (!nodeElement) {
      setDomBounds(null);
      return;
    }
    const updateBounds = () => {
      const nodeRect = nodeElement.getBoundingClientRect();
      const containerRect = containerEl.getBoundingClientRect();
      setDomBounds({
        nodeRect,
        containerRect,
      });
    };
    updateBounds();
    window.addEventListener('resize', updateBounds);
    window.addEventListener('scroll', updateBounds, true);
    return () => {
      window.removeEventListener('resize', updateBounds);
      window.removeEventListener('scroll', updateBounds, true);
    };
  }, [popoverData?.nodeId, containerRef, viewportX, viewportY, zoom]);

  const { cardWidth, cardHeight, paddingClass, gridColumns, priceClass, metricValueClass } = useMemo(() => {
    if (variant === 'compact') {
      return {
        cardWidth: 260,
        cardHeight: 200,
        paddingClass: 'p-3',
        gridColumns: 'grid-cols-1 gap-2',
        priceClass: 'text-xl',
        metricValueClass: 'text-base',
      };
    }
    return {
      cardWidth: 320,
      cardHeight: 220,
      paddingClass: 'p-4',
      gridColumns: 'grid-cols-2 gap-3',
      priceClass: 'text-2xl',
      metricValueClass: 'text-base',
    };
  }, [variant]);

  const popoverStyle = useMemo(() => {
    if (!popoverData || !domBounds) {
      return null;
    }
    const { nodeRect, containerRect } = domBounds;
    const containerWidth = containerRect.width;
    const containerHeight = containerRect.height;
    let left = nodeRect.left - containerRect.left + nodeRect.width / 2 - cardWidth / 2;
    left = Math.min(Math.max(16, left), containerWidth - cardWidth - 16);
    let top = nodeRect.top - containerRect.top - cardHeight - 16;
    if (top < 16) {
      top = nodeRect.bottom - containerRect.top + 16;
      if (top + cardHeight > containerHeight - 16) {
        top = containerHeight - cardHeight - 16;
      }
    }
    return { left, top };
  }, [popoverData, domBounds, cardWidth, cardHeight]);

  if (disabled || !popoverData || !popoverStyle) {
    return null;
  }

  const statusToken = getStatusToken(popoverData.status);
  const metrics = [
    { label: '市值', value: formatMetricValue(popoverData.marketCap) },
    { label: '營收', value: formatMetricValue(popoverData.revenue) },
  ];

  const handleNavigate = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!popoverData?.ticker) {
      return;
    }
    const ticker = popoverData.ticker;
    setSelectedCompany(null);
    navigate(`/stock/${ticker}`);
  };

  return (
    <div
      data-stock-popover="true"
      ref={popoverRef}
      className={`
        absolute z-40 rounded-2xl border ${paddingClass} shadow-2xl transition-all duration-200
        ${isDark ? 'bg-slate-900 border-slate-700 text-slate-100 shadow-black/50' : 'bg-white border-slate-200 text-slate-900 shadow-slate-900/10'}
      `}
      style={{ left: popoverStyle.left, top: popoverStyle.top, width: cardWidth }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-2xs font-semibold uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">
            {popoverData.subtitle ? `${popoverData.subtitle} 概覽` : '股票概覽'}
          </p>
          {(() => {
            const { primary, secondary } = getStockLabel({
              ticker: popoverData.ticker,
              name: popoverData.title !== popoverData.ticker ? popoverData.title : undefined,
            });
            return (
              <>
                <p className="mt-1 text-xl font-semibold leading-tight">{primary}</p>
                {secondary && (
                  <p className="text-base font-mono text-slate-500 dark:text-slate-400">{secondary}</p>
                )}
              </>
            );
          })()}
        </div>
        <span className={`px-2 py-0.5 text-2xs font-semibold rounded-full ${statusToken.className}`}>
          {statusToken.label}
        </span>
        <button
          type="button"
          onClick={() => setSelectedCompany(null)}
          className={`ml-auto rounded-full p-1.5 transition-colors ${isDark ? 'hover:bg-white/10 text-slate-400' : 'hover:bg-slate-100 text-slate-500'}`}
          aria-label="關閉節點詳情"
        >
          <X size={14} />
        </button>
      </div>

      <div className="mt-4 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 dark:text-slate-500">價格</p>
          <p className={`${priceClass} font-bold`}>{formatCurrencyValue(popoverData.price)}</p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wider text-slate-400 dark:text-slate-500">漲跌</p>
          <p
            className={`inline-flex items-center gap-1 text-lg font-semibold ${
              typeof popoverData.changePct === 'number' && popoverData.changePct < 0 ? 'text-rose-500' : 'text-emerald-500'
            }`}
          >
            <span className="inline-block h-2 w-2 rounded-full bg-current" />
            {formatPercentValue(popoverData.changePct)}
          </p>
        </div>
      </div>

      <div className={`mt-4 grid ${gridColumns}`}>
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className={`rounded-xl border px-3 py-2 ${
              isDark ? 'border-slate-700 bg-slate-800/60' : 'border-slate-100 bg-slate-50'
            }`}
          >
            <p className="text-2xs uppercase tracking-wider text-slate-400 dark:text-slate-500">{metric.label}</p>
            <p className={`${metricValueClass} font-semibold`}>{metric.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-end">
        <button
          type="button"
          onClick={handleNavigate}
          className={`rounded-xl px-4 py-2 text-base font-semibold transition-all inline-flex items-center gap-2 ${
            isDark ? 'bg-indigo-500/20 text-indigo-200 hover:bg-indigo-500/30' : 'bg-indigo-600 text-slate-50 hover:bg-indigo-700'
          }`}
        >
          儀表板
          <ArrowUpRight className="h-4 w-4" />
        </button>
      </div>
      <span className="pointer-events-none absolute -bottom-2 left-1/2 block h-4 w-4 -translate-x-1/2 rotate-45 border-b border-r border-slate-200 bg-inherit dark:border-slate-700" />
    </div>
  );
};

export default StockNodePopover;

