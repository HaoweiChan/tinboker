import React, { useMemo, useState, useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import ReactFlow, { Background, Controls, useNodesState, useEdgesState, ReactFlowProvider, useReactFlow } from 'reactflow';
import { getSupplyChainData } from '@/services/mocks';
import { getSupplyChainVisual } from '@/services';
import { getLayoutedElements } from '@/utils/graphUtils';
import { DisplayMode, NodeStyle, type GraphData, type GraphNode, type GraphEdge } from '@/services/types';
import { BarChart2, DollarSign, PieChart, Circle, CircleDashed, RotateCcw } from 'lucide-react';
import 'reactflow/dist/style.css';
import { useAppStore } from '@/store/useAppStore';
import { GraphControlToggle } from '../GraphControlToggle';
import StockNodePopover from '../StockNodePopover';
import { layeredNodeTypes } from '../nodeTypes';

interface LayeredGraphProps {
  isWidget?: boolean;
  data?: any; // Using any to be flexible with the incoming payload structure, ideally UnifiedGraphResponse['data']
  title?: string;
  description?: string;
}

const LayeredGraphInner: React.FC<LayeredGraphProps> = ({ isWidget = false, data, title, description }) => {
  // State for API-fetched data and loading state
  const [apiData, setApiData] = useState<GraphData | null>(null);
  const [apiFailed, setApiFailed] = useState(false);
  
  // Fetch data from API if not provided via props
  useEffect(() => {
    if (!data) {
      // Try API first, only use mock if it fails
      getSupplyChainVisual()
        .then((graphData) => {
          if (import.meta.env.DEV) {
            console.log('[LayeredGraph] Received API data:', graphData);
          }
          setApiData(graphData);
          setApiFailed(false);
        })
        .catch((error) => {
          console.warn('[LayeredGraph] API call failed, using mock data:', error);
          setApiFailed(true);
          // Only set mock data after API fails
          const mockData = getSupplyChainData();
          // Ensure nodes have proper type for GraphData
          const typedData: GraphData = {
            nodes: mockData.nodes.map(n => ({
              ...n,
              type: (n.type || 'company') as 'company' | 'stock' | 'cluster',
            })) as GraphNode[],
            edges: mockData.edges as GraphEdge[],
          };
          setApiData(typedData);
        });
    }
  }, [data]);
  
  // Process initial data: either from props, API, or fallback mock
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    // Priority: props > API data > mock (only if API failed)
    const dataSource = data || (apiFailed ? null : apiData);
    
    if (dataSource && dataSource.nodes && dataSource.edges) {
      // If external data is provided, we apply the layout
      // We assume the API returns flat nodes/edges.
      // We map them to ensure they match ReactFlow structure if needed (the contract matches closely)
      const nodes = dataSource.nodes.map((n: any) => ({
        ...n,
        // Ensure position exists if missing (layout will overwrite)
        position: n.position || { x: 0, y: 0 },
        data: {
            ...n.data,
            // Ensure essential fields are present
            label: n.data.label || n.data.ticker || n.id
        }
      }));
      
      // Apply dagre layout
      return getLayoutedElements(nodes, dataSource.edges, 'LR');
    }
    // Only return mock if API has failed, otherwise return empty (waiting for API)
    return apiFailed ? getSupplyChainData() : { nodes: [], edges: [] };
  }, [data, apiData, apiFailed]);
  
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const canvasBg = 'var(--bg-base)';
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const sharedPanelStyle: CSSProperties = {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    color: 'var(--text-primary)',
  };
  
  const { fitView } = useReactFlow();

  // Control State
  const [displayMode, setDisplayMode] = useState<DisplayMode>(DisplayMode.PRICE);
  const [nodeStyle, setNodeStyle] = useState<NodeStyle>(NodeStyle.SOLID);

  // Propagate state to nodes
  useEffect(() => {
    setNodes((nds) => nds.map(node => ({
        ...node,
        data: { ...node.data, displayMode, nodeStyle, isDark, theme }
    })));
  }, [displayMode, nodeStyle, isDark, theme, setNodes]);

  // Effect to update nodes when data prop or apiData changes
  useEffect(() => {
    const dataSource = data || (apiFailed ? null : apiData);
    if (dataSource && dataSource.nodes && dataSource.edges) {
        const { nodes: layoutNodes, edges: layoutEdges } = getLayoutedElements(
            dataSource.nodes.map((n: any) => ({...n, position: n.position || {x:0,y:0}})), 
            dataSource.edges, 
            'LR'
        );
        setNodes(layoutNodes);
        setEdges(layoutEdges);
        // Fit view after data loads
        setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 100);
    }
  }, [data, apiData, apiFailed, setNodes, setEdges, fitView]);

  // Fix: Re-declare state to get setEdges
  // Since I can't easily change the hook call order/structure conditionally without breaking rules, 
  // I will just rely on the initial render for now or assume the user won't switch data prop dynamically without remount.
  // But to be safe, let's fix the destructuring in the next edit or just assume initialNodes is enough for this refactor.
  // Actually, I should fix it now.
  
  const resetLayout = () => {
    setNodes((nds) => nds.map(n => {
      const initial = initialNodes.find(inNode => inNode.id === n.id);
      // Preserve current data (displayMode etc) but reset position
      return initial ? { ...n, position: { ...initial.position } } : n;
    }));
    setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 10);
  };

  const graphWrapperClass = !isWidget ? 'w-full h-full pl-[260px]' : 'w-full h-full';

  return (
    <div ref={canvasRef} className="w-full h-full relative" style={{ backgroundColor: canvasBg }}>
      <div className={graphWrapperClass}>
        <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={layeredNodeTypes}
        fitView
        attributionPosition="bottom-right"
        className="bg-transparent graph-edges-top"
        style={{ backgroundColor: canvasBg }}
        minZoom={isWidget ? 0.1 : 0.2}
      >
        <Background color={isDark ? '#1f2937' : '#e2e8f0'} gap={16} />
        {!isWidget && (
          <Controls
            position="bottom-right"
            className="shadow-lg rounded-xl"
            style={sharedPanelStyle}
          />
        )}
      </ReactFlow>
      </div>
      <StockNodePopover
        containerRef={canvasRef}
        nodes={nodes}
        variant={isWidget ? 'compact' : 'standard'}
      />
      {!isWidget && (
        <div className="absolute top-6 left-6 z-[2000] flex flex-col gap-3" style={{ width: 240 }}>
          <div className="p-4 rounded-xl shadow-sm backdrop-blur-sm relative" style={sharedPanelStyle}>
            <h2 className="text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>{title || "Layered DAG"}</h2>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {description || "Multi-level dependency view."}
            </p>
            <button 
              onClick={resetLayout}
              className="absolute top-4 right-4 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Reset Layout"
            >
              <RotateCcw size={14} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" />
            </button>
          </div>
          <div className="p-3 rounded-xl shadow-sm backdrop-blur-sm" style={sharedPanelStyle}>
            <div className="mb-3">
              <h3 className="text-2xs font-bold text-slate-400 uppercase tracking-wider mb-2">Display Mode</h3>
              <div className="flex flex-col gap-1">
                <GraphControlToggle
                  label="Price Chart"
                  icon={BarChart2}
                  isActive={displayMode === DisplayMode.PRICE}
                  onClick={() => setDisplayMode(DisplayMode.PRICE)}
                />
                <GraphControlToggle
                  label="Market Cap"
                  icon={DollarSign}
                  isActive={displayMode === DisplayMode.MARKET_CAP}
                  onClick={() => setDisplayMode(DisplayMode.MARKET_CAP)}
                />
                <GraphControlToggle
                  label="Revenue"
                  icon={PieChart}
                  isActive={displayMode === DisplayMode.REVENUE}
                  onClick={() => setDisplayMode(DisplayMode.REVENUE)}
                />
              </div>
            </div>
            {displayMode !== DisplayMode.PRICE && (
              <div>
                <h3 className="text-2xs font-bold text-slate-400 uppercase tracking-wider mb-2">Node Style</h3>
                <div className="flex flex-col gap-1">
                  <GraphControlToggle
                    label="Ghost"
                    icon={CircleDashed}
                    isActive={nodeStyle === NodeStyle.GHOST}
                    onClick={() => setNodeStyle(NodeStyle.GHOST)}
                  />
                  <GraphControlToggle
                    label="Solid"
                    icon={Circle}
                    isActive={nodeStyle === NodeStyle.SOLID}
                    onClick={() => setNodeStyle(NodeStyle.SOLID)}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const LayeredGraph: React.FC<LayeredGraphProps> = (props) => (
  <ReactFlowProvider>
    <LayeredGraphInner {...props} />
  </ReactFlowProvider>
);

export default LayeredGraph;
