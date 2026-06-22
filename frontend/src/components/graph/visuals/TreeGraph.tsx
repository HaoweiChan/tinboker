import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Panel, 
  useNodesState, 
  useEdgesState,
  ReactFlowProvider,
  BackgroundVariant,
  useReactFlow
} from 'reactflow';
import type { Node } from 'reactflow';
import { getOwnershipData } from '@/services/mocks';
import { getOwnershipVisual } from '@/services';
import { getLayoutedElements } from '@/utils/graphUtils';
import { DisplayMode, NodeStyle } from '@/services/types';
import { GraphControlToggle } from '../GraphControlToggle';
import { useAppStore } from '@/store/useAppStore';
import { RotateCcw, BarChart2, DollarSign, PieChart, Circle, CircleDashed } from 'lucide-react';
import type { CSSProperties } from 'react';
import 'reactflow/dist/style.css';
import StockNodePopover from '../StockNodePopover';
import { standardNodeTypes } from '../nodeTypes';

interface TreeGraphProps {
  isWidget?: boolean;
  data?: any; // UnifiedGraphResponse['data']
  title?: string;
  description?: string;
}

const TreeGraphContent: React.FC<TreeGraphProps> = ({ isWidget = false, data, title, description }) => {
  // State for API-fetched data and loading state
  const [apiData, setApiData] = useState<any>(null);
  const [apiFailed, setApiFailed] = useState(false);
  
  // Fetch data from API if not provided via props
  useEffect(() => {
    if (!data) {
      // Try API first, only use mock if it fails
      getOwnershipVisual()
        .then((graphData) => {
          if (import.meta.env.DEV) {
            console.log('[TreeGraph] Received API data:', graphData);
          }
          setApiData(graphData);
          setApiFailed(false);
        })
        .catch((error) => {
          console.warn('[TreeGraph] API call failed, using mock data:', error);
          setApiFailed(true);
          // Only set mock data after API fails
          setApiData(getOwnershipData());
        });
    }
  }, [data]);
  
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    // Priority: props > API data > mock (only if API failed)
    const dataSource = data || (apiFailed ? null : apiData);
    
    if (dataSource && dataSource.nodes && dataSource.edges) {
      const nodes = dataSource.nodes.map((n: any) => ({
        ...n,
        position: n.position || { x: 0, y: 0 },
        data: {
            ...n.data,
            label: n.data.label || n.data.ticker || n.id
        }
      }));
      return getLayoutedElements(nodes, dataSource.edges, 'TB');
    }
    // Only return mock if API has failed, otherwise return empty (waiting for API)
    return apiFailed ? getOwnershipData() : { nodes: [], edges: [] };
  }, [data, apiData, apiFailed]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const { fitView } = useReactFlow();
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const sharedPanelStyle: CSSProperties = {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    color: 'var(--text-primary)',
  };

  const [displayMode, setDisplayMode] = useState<DisplayMode>(DisplayMode.PRICE);
  const [nodeStyle, setNodeStyle] = useState<NodeStyle>(NodeStyle.SOLID);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: { ...node.data, displayMode, nodeStyle, isDark, theme },
      }))
    );
  }, [displayMode, nodeStyle, isDark, theme, setNodes]);

  // Effect to update graph when prop data or apiData changes
  useEffect(() => {
    const dataSource = data || (apiFailed ? null : apiData);
    if (dataSource && dataSource.nodes && dataSource.edges) {
        const { nodes: layoutNodes, edges: layoutEdges } = getLayoutedElements(
            dataSource.nodes.map((n: any) => ({...n, position: n.position || {x:0,y:0}})), 
            dataSource.edges, 
            'TB'
        );
        setNodes(layoutNodes);
        setEdges(layoutEdges);
        setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 50);
    }
  }, [data, apiData, apiFailed, setNodes, setEdges, fitView]);

  const resetLayout = () => {
    // Reset to the initial state derived from props or mock
    // Note: This simple reset relies on the fact that we don't mutate initialNodes deeply in place without updating state
    // Ideally we would re-run the layout or use a saved snapshot. 
    // For now, triggering a re-layout or just fitView is often enough if positions haven't been messed up too much.
    // But since users drag nodes, we might want to restore original positions.
    if (data && data.nodes && data.edges) {
         const { nodes: layoutNodes } = getLayoutedElements(
            data.nodes.map((n: any) => ({...n, position: {x:0,y:0}})), 
            data.edges, 
            'TB'
        );
        setNodes(layoutNodes);
    } else {
        const { nodes: layoutNodes } = getOwnershipData();
        setNodes(layoutNodes);
    }
    setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 50);
  };

  const toggleChildrenVisibility = useCallback((nodeId: string) => {
    const childrenEdges = edges.filter((edge) => edge.source === nodeId);
    const childrenIds = childrenEdges.map((edge) => edge.target);
    if (!childrenIds.length) {
      return;
    }
    let shouldHide = false;
    setNodes((prevNodes) => {
      shouldHide = prevNodes.some((node) => childrenIds.includes(node.id) && !node.hidden);
      return prevNodes.map((node) =>
        childrenIds.includes(node.id) ? { ...node, hidden: shouldHide } : node
      );
    });
    setEdges((prevEdges) =>
      prevEdges.map((edge) =>
        childrenIds.includes(edge.target) ? { ...edge, hidden: shouldHide } : edge
      )
    );
  }, [edges, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (!(event.altKey || event.metaKey || event.shiftKey)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      toggleChildrenVisibility(node.id);
    },
    [toggleChildrenVisibility]
  );

  return (
    <div ref={canvasRef} className="relative w-full h-full" style={{ backgroundColor: 'var(--bg-base)' }}>
      <div className="w-full h-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={standardNodeTypes}
          fitView
          className="bg-transparent graph-edges-top"
          style={{ backgroundColor: 'var(--bg-base)' }}
          minZoom={isWidget ? 0.1 : 0.2}
        >
          <Background color={isDark ? '#1f2937' : '#e2e8f0'} variant={BackgroundVariant.Dots} gap={20} />
          {!isWidget && (
            <Controls
              position="bottom-right"
              className="shadow-lg rounded-xl"
              style={sharedPanelStyle}
            />
          )}
          {!isWidget && (
            <Panel position="top-left" className="flex flex-col gap-3 max-w-xs">
              <div className="p-4 rounded-xl shadow-sm backdrop-blur-sm relative" style={sharedPanelStyle}>
                <h2 className="text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>{title || "Hierarchical Tree"}</h2>
                <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
                  {description || "Ownership structures (Parent → Subsidiary)."}
                </p>
                <div className="p-2 rounded border text-xs font-medium text-center" style={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}>
                  Hold Alt/Option and click a parent node to toggle child visibility
                </div>
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
                  <h3 className="text-2xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                    Display Mode
                  </h3>
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
            </Panel>
          )}
          <StockNodePopover
            containerRef={canvasRef}
            nodes={nodes}
            variant={isWidget ? 'compact' : 'standard'}
          />
        </ReactFlow>
      </div>
    </div>
  );
};

const TreeGraph: React.FC<TreeGraphProps> = (props) => (
  <ReactFlowProvider>
    <TreeGraphContent {...props} />
  </ReactFlowProvider>
);

export default TreeGraph;
