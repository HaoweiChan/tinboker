import React, { useMemo, useState } from 'react';
import { ResponsiveSankey } from '@nivo/sankey';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, X } from 'lucide-react';
import type { SankeyData } from '@/services/types';
import { useAppStore } from '@/store/useAppStore';


const fallbackData: SankeyData = {
  nodes: [
    { id: 'Softbank Vision Fund', nodeColor: '#fbbf24' },
    { id: 'Uber', nodeColor: '#0f172a' },
    { id: 'WeWork', nodeColor: '#ef4444' },
    { id: 'DoorDash', nodeColor: '#f87171' },
    { id: 'Grab', nodeColor: '#10b981' },
    { id: 'Coupang', nodeColor: '#60a5fa' },
    { id: 'Consumer A' },
    { id: 'Consumer B' },
    { id: 'Real Estate' },
  ],
  links: [
    { source: 'Softbank Vision Fund', target: 'Uber', value: 150 },
    { source: 'Softbank Vision Fund', target: 'WeWork', value: 80 },
    { source: 'Softbank Vision Fund', target: 'DoorDash', value: 40 },
    { source: 'Softbank Vision Fund', target: 'Grab', value: 60 },
    { source: 'Softbank Vision Fund', target: 'Coupang', value: 90 },
    { source: 'Uber', target: 'Consumer A', value: 100 },
    { source: 'Uber', target: 'Consumer B', value: 50 },
    { source: 'WeWork', target: 'Real Estate', value: 80 },
  ],
};

// Helper to extract ticker from ID or custom field if available
const getTicker = (nodeId: string, nodeData?: any) => {
    if (nodeData && nodeData.ticker) return nodeData.ticker;
    // Simple heuristic for mock data IDs that might be names
    const nameToTicker: Record<string, string> = {
        'Uber': 'UBER',
        'DoorDash': 'DASH',
        'Grab': 'GRAB',
        'Coupang': 'CPNG',
        'WeWork': 'WE',
        'Tesla': 'TSLA',
        'NVIDIA': 'NVDA',
        'SoftBank': 'SFTBY' 
    };
    return nameToTicker[nodeId] || nodeId; // Fallback to ID as ticker
};

interface SankeyGraphProps {
  isWidget?: boolean;
  data?: SankeyData;
  title?: string;
  description?: string;
}

const SankeyGraph: React.FC<SankeyGraphProps> = ({ isWidget = false, data, title, description }) => {
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const nodeColorFallback = isDark ? '#475569' : '#cbd5e1';
  const navigate = useNavigate();
  const [activeNode, setActiveNode] = useState<any | null>(null);
  const Container = isWidget ? React.Fragment : 'div';
  const containerProps = isWidget
    ? {}
    : {
        className: 'w-full h-full flex flex-col rounded-[28px] p-8 border shadow-xl',
        style: {
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-default)',
          color: 'var(--text-primary)',
        },
      };

  const sankeyTheme = useMemo(
    () => ({
      textColor: isDark ? '#e2e8f0' : '#0f172a',
      fontSize: 12,
      tooltip: {
        container: {
          background: isDark ? '#020617' : '#ffffff',
          color: isDark ? '#e2e8f0' : '#0f172a',
          borderRadius: 16,
          border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
          boxShadow: '0 15px 45px rgba(2,6,23,0.45)',
        },
      },
      labels: {
        text: {
          fill: isDark ? '#f8fafc' : '#0f172a',
          fontSize: 12,
          fontWeight: 600,
        },
      },
    }),
    [isDark],
  );

  const sankeyData = useMemo<SankeyData>(() => {
    const sourceData = data || fallbackData;
    const nodeColorMap = new Map<string, string>();
    
    sourceData.nodes.forEach((node) => {
      if (node.nodeColor) nodeColorMap.set(node.id, node.nodeColor);
    });

    return {
      nodes: sourceData.nodes.map(n => ({ ...n, nodeColor: n.nodeColor || nodeColorFallback })),
      links: sourceData.links.map((link) => {
        const sourceColor = nodeColorMap.get(link.source) || nodeColorFallback;
        return {
          ...link,
          startColor: sourceColor,
          endColor: sourceColor,
        };
      }),
    };
  }, [data, nodeColorFallback]);

  const chartShellClass = isWidget
    ? 'relative h-full rounded-3xl border overflow-hidden'
    : 'relative flex-1 min-h-[520px] rounded-3xl border';
  const chartShellStyle = {
    backgroundColor: 'var(--bg-base)',
    borderColor: 'var(--border-default)',
    boxShadow: isWidget ? 'var(--shadow-lg)' : 'var(--shadow-xl)',
  };
  const closeButtonClass = isDark
    ? 'bg-slate-800/40 text-slate-300 hover:bg-slate-700/70'
    : 'bg-slate-100 text-slate-500 hover:bg-slate-200';
  const overviewCopyClass = isDark ? 'text-slate-400' : 'text-slate-600';
  const symbolBadgeClass = isDark ? 'bg-slate-800 text-slate-50' : 'bg-slate-200 text-slate-900';
  const allocationClass = isDark ? 'text-indigo-300' : 'text-indigo-600';

  const handleNodeClick = (node: any) => {
    if (isWidget) return;
    setActiveNode(node);
  };

  const handleNavigate = () => {
    if (!activeNode) return;
    const ticker = getTicker(activeNode.id, activeNode);
    navigate(`/stock/${ticker}`);
  };

  return (
    <Container {...containerProps}>
      {!isWidget && (
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.3em] text-brand-yellow">Capital Flow</p>
          <h2 className="text-2xl font-bold">{title || "D. Investment Portfolio (Sankey)"}</h2>
          <p className="text-base text-slate-500 dark:text-slate-400">
            {description || "Visualizing capital allocation magnitude. Line width equals investment size."}
          </p>
        </div>
      )}

      <div className={chartShellClass} style={chartShellStyle}>
        <div className="absolute inset-0">
          <ResponsiveSankey
            data={sankeyData}
            margin={{ top: 24, right: isWidget ? 120 : 180, bottom: 24, left: 140 }}
            align="justify"
            colors={(node: any) => node.nodeColor || nodeColorFallback}
            nodeOpacity={1}
            nodeHoverOthersOpacity={0.35}
            nodeThickness={18}
            nodeSpacing={24}
            nodeBorderWidth={isDark ? 1 : 0}
            nodeBorderColor={isDark ? '#020617' : '#ffffff'}
            nodeBorderRadius={4}
            linkOpacity={isDark ? 0.42 : 0.55}
            linkHoverOthersOpacity={0.12}
            linkContract={3}
            linkBlendMode={isDark ? 'screen' : 'multiply'}
            enableLinkGradient
            labelPosition="outside"
            labelOrientation="horizontal"
            labelPadding={14}
            labelTextColor={{
              from: 'color',
              modifiers: [['darker', isDark ? 0.4 : 1]],
            }}
            theme={{ ...sankeyTheme, background: 'transparent' }}
            onClick={(item) => {
               // Nivo passes the node object
               handleNodeClick(item);
            }}
            nodeTooltip={({ node }) => (
              <div className="max-w-xs space-y-1">
                <p className="text-2xs font-semibold uppercase tracking-[0.2em] text-slate-400">Node</p>
                <p className="text-base font-bold">{String(node.id)}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{Math.round(Number(node.value))} allocation points</p>
              </div>
            )}
            linkTooltip={({ link }: any) => (
                <div className="p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg text-xs">
                    <strong>{link.source.id}</strong> → <strong>{link.target.id}</strong>
                    <div className="mt-1">
                        {link.customLabel ? (
                            <span className="font-semibold text-indigo-600 dark:text-indigo-400">{link.customLabel}</span>
                        ) : (
                            <span>Value: {link.value}</span>
                        )}
                    </div>
                </div>
            )}
          />
        </div>

        {!isWidget && activeNode && (
          <div
            className={`absolute top-6 right-6 w-80 rounded-3xl border p-5 shadow-2xl ${
              isDark ? 'bg-slate-950/90 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-2xs font-semibold uppercase tracking-[0.2em] text-slate-400">Node Overview</p>
                <h3 className="text-xl font-bold mt-1">{activeNode.id}</h3>
                <div className="mt-1 flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-md text-xs font-mono ${symbolBadgeClass}`}>
                    {getTicker(activeNode.id, activeNode)}
                  </span>
                  <span className={`text-xs font-semibold ${allocationClass}`}>
                    Value: {Math.round(activeNode.value)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveNode(null)}
                className={`p-1.5 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${closeButtonClass}`}
                aria-label="Close company overview"
              >
                <X size={14} />
              </button>
            </div>
            
            {/* Simplified dynamic content since hardcoded profiles are removed */}
            <p className={`mt-4 text-base ${overviewCopyClass}`}>
               {activeNode.overview || `Investment flow analysis for ${activeNode.id}.`}
            </p>
            
            <button
              type="button"
              onClick={handleNavigate}
              className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-600 px-4 py-2 text-base font-semibold text-slate-50 shadow-lg hover:bg-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Dashboard
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}
      </div>
    </Container>
  );
};

export default SankeyGraph;
