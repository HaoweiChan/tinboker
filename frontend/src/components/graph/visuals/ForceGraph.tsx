import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Panel, 
  useNodesState, 
  useEdgesState,
  ReactFlowProvider,
  useReactFlow
} from 'reactflow';
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force';
import { getClusterData } from '@/services/mocks';
import { forceNodeTypes } from '../nodeTypes';
import { DisplayMode, NodeStyle } from '@/services/types';
import { BarChart2, DollarSign, PieChart, Circle, CircleDashed, RotateCcw } from 'lucide-react';
import 'reactflow/dist/style.css';
import { useAppStore } from '@/store/useAppStore';
import { GraphControlToggle } from '../GraphControlToggle';
import type { CSSProperties } from 'react';
import StockNodePopover from '../StockNodePopover';

interface ForceGraphProps {
  isWidget?: boolean;
  data?: any;
  title?: string;
  description?: string;
}

const ForceGraphInner: React.FC<ForceGraphProps> = ({ isWidget = false, data, title, description }) => {
  // Initialize data from props or mock
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    // Priority: props > mock data
    const dataSource = data || getClusterData();
    
    if (dataSource && dataSource.nodes && dataSource.edges) {
        const nodes = dataSource.nodes.map((n: any) => ({
            ...n,
            position: n.position || { x: 0, y: 0 },
            data: {
                ...n.data,
                label: n.data.label || n.data.ticker || n.id
            }
        }));
        return { nodes, edges: dataSource.edges };
    }
    return { nodes: [], edges: [] };
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const { theme } = useAppStore();
  const isDark = theme === 'dark';
  
  const sharedPanelStyle: CSSProperties = {
    backgroundColor: 'var(--color-card)',
    border: '1px solid var(--color-border)',
    color: 'var(--color-foreground)',
  };
  const canvasRef = useRef<HTMLDivElement | null>(null);
  
  // Control State
  const [displayMode, setDisplayMode] = useState<DisplayMode>(DisplayMode.PRICE);
  const [nodeStyle, setNodeStyle] = useState<NodeStyle>(NodeStyle.SOLID);

  const { fitView } = useReactFlow();
  const simulationRef = useRef<any>(null);

  // Update nodes when props data changes
  useEffect(() => {
    const dataSource = data || getClusterData();
    if (dataSource && dataSource.nodes && dataSource.edges) {
        // When data updates, we might want to reset nodes to initial positions or keep them
        // For now, just replacing them triggers the simulation effect below because 'nodes' state updates
        setNodes(dataSource.nodes.map((n: any) => ({
            ...n,
            position: n.position || { x: Math.random() * 500, y: Math.random() * 500 }, // Randomize if no pos to help force layout
            data: {
                ...n.data,
                label: n.data.label || n.data.ticker || n.id,
                displayMode, nodeStyle, isDark, theme
            }
        })));
        setEdges(dataSource.edges);
    }
  }, [data, setNodes, setEdges, displayMode, nodeStyle, isDark, theme]);

  // Update nodes when controls change (merge control state into existing nodes)
  useEffect(() => {
    setNodes((nds) => nds.map(node => {
        // Only update if type matches or if generic
        if (node.type === 'company' || node.type === 'stock') {
            return { ...node, data: { ...node.data, displayMode, nodeStyle, isDark, theme } };
        }
        return node;
    }));
  }, [displayMode, nodeStyle, isDark, theme, setNodes]);

  // D3 Force Simulation
  useEffect(() => {
    // Prepare simulation nodes (d3 mutates these)
    const simulationNodes = nodes.map((node) => ({ 
      ...node, 
      x: node.position.x || 0, 
      y: node.position.y || 0,
      // Determine radius based on type/mode for collision
      r: node.type === 'person'
        ? 60
        : displayMode === DisplayMode.PRICE
          ? 110
          : 150
    }));

    const simulationEdges = edges.map((edge) => ({ 
      ...edge, 
      source: edge.source, 
      target: edge.target 
    }));

    try {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }

      const simulation = forceSimulation(simulationNodes as any)
        .force('link', forceLink(simulationEdges).id((d: any) => d.id).distance(displayMode === DisplayMode.PRICE ? 200 : 280))
        .force('charge', forceManyBody().strength(-1100))
        .force('center', forceCenter(400, 300))
        .force('collide', forceCollide().radius((d: any) => d.r + 18).strength(1));

      simulationRef.current = simulation;

      simulation.on('tick', () => {
        setNodes((nds) =>
          nds.map((node) => {
            const simNode = simulationNodes.find((n) => n.id === node.id);
            if (simNode && typeof simNode.x === 'number' && typeof simNode.y === 'number') {
              return { ...node, position: { x: simNode.x, y: simNode.y } };
            }
            return node;
          })
        );
      });

      // Stop simulation after a few seconds to save resources
      setTimeout(() => {
          if (simulationRef.current) {
            simulationRef.current.stop();
            fitView({ duration: 800, padding: 0.2 });
          }
      }, 2500);

    } catch (e) {
      console.error("Error initializing force simulation:", e);
    }

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };
  }, [displayMode, data, initialNodes, initialEdges]); 
  // Added data dependencies to restart sim when data changes. 
  // Note: 'nodes' is not a dependency to avoid infinite loop (tick updates nodes).
  // Ideally we track 'initialNodes' or a version ID.

  const resetLayout = () => {
    // For force graph, reset means re-running simulation from initial or random positions
    if (data && data.nodes) {
         setNodes(data.nodes.map((n: any) => ({
            ...n,
            position: { x: Math.random() * 500, y: Math.random() * 500 },
            data: { ...n.data, displayMode, nodeStyle, isDark, theme }
         })));
    } else {
        const clusterData = getClusterData();
        setNodes(clusterData.nodes.map(n => ({...n, data: {...n.data, displayMode, nodeStyle, isDark, theme}})));
        setEdges(clusterData.edges);
    }
    // The useEffect will pick up the change and restart simulation
  };

  return (
    <div className="w-full h-full bg-slate-50 relative" style={{ backgroundColor: 'var(--color-background)' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={forceNodeTypes}
        fitView
        minZoom={0.1}
        className="bg-transparent graph-edges-top"
        style={{ backgroundColor: 'var(--color-background)' }}
        nodesDraggable={!isWidget}
        nodesConnectable={!isWidget}
        elementsSelectable={!isWidget}
      >
        <Background color="var(--color-border)" gap={16} />
        {!isWidget && (
          <Controls
            position="bottom-right"
            className="shadow-lg rounded-xl"
            style={sharedPanelStyle}
          />
        )}
        
        {!isWidget && (
           <Panel position="top-left" className="flex flex-col gap-3">
             {/* Description Panel */}
             <div className="p-4 rounded-xl shadow-sm backdrop-blur-sm max-w-xs relative" style={sharedPanelStyle}>
                <h2 className="text-xl font-bold mb-1" style={{ color: 'var(--color-foreground)' }}>{title || "Ecosystem Cluster"}</h2>
                <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                  {description || "Visualizing soft connections (Shared Board Members, Investors)."}
                </p>
                <button
                  onClick={resetLayout}
                  className="absolute top-4 right-4 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Reset Layout"
                >
                  <RotateCcw size={14} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" />
                </button>
             </div>

             {/* Controls Panel */}
            <div className="p-3 rounded-xl shadow-sm backdrop-blur-sm w-48" style={sharedPanelStyle}>
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

                {(displayMode !== DisplayMode.PRICE) && (
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
      </ReactFlow>
      <StockNodePopover
        containerRef={canvasRef}
        nodes={nodes}
        variant={isWidget ? 'compact' : 'standard'}
      />
    </div>
  );
};

const ForceGraph: React.FC<ForceGraphProps> = (props) => (
  <ReactFlowProvider>
    <ForceGraphInner {...props} />
  </ReactFlowProvider>
);

export default ForceGraph;
