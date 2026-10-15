/**
 * Mock graph data for visual archetypes (Supply Chain, Ownership, Cluster)
 * 
 * SOURCE: Extracted from src/utils/graphUtils.ts
 */

import type { GraphNode, GraphEdge, StockNodeData } from './types';
import type { Node, Edge } from 'reactflow';
import { getLayoutedElements } from '@/utils/graphUtils';

// --- Financial Data Generator ---
const generateFinancials = (): Partial<StockNodeData> => {
  const price = Number((Math.random() * 200 + 50).toFixed(2));
  const changeVal = Math.random() * 10 - 5;
  
  // Market Cap between 1B and 3000B
  const marketCapVal = Math.random() * 2000 + 10;
  const marketCap = marketCapVal > 1000
    ? (marketCapVal / 1000).toFixed(2) + 'T'
    : marketCapVal.toFixed(1) + 'B';

  // Revenue between 0.1B and 500B
  const revenueVal = Math.random() * 400 + 5;
  const revenue = revenueVal.toFixed(1) + 'B';

  // Generate 20 points for sparkline
  const history = Array.from({ length: 20 }, () => Math.random() * 100 + Math.random() * 20);

  return {
    price,
    changePct: changeVal / 100,
    marketCapVal,
    marketCap,
    revenueVal,
    revenue,
    history,
  };
};

const mergeFinancials = (data: Partial<StockNodeData>): Partial<StockNodeData> => ({
  ...data,
  ...generateFinancials(),
});

// ============================================
// 1. Layered DAG (Supply Chain)
// ============================================

export interface SupplyChainEntity {
  id: string;
  label: string;
  ticker: string;
  status: string;
  layerLabel: string;
}

export const supplyChainEntities: SupplyChainEntity[] = [
  // Tier 2: Battery Suppliers
  { id: 'catl', label: 'CATL', ticker: '300750', status: 'Active', layerLabel: 'Tier 2: Battery' },
  { id: 'byd', label: 'BYD Company', ticker: '1211', status: 'Active', layerLabel: 'Tier 2: Battery' },
  { id: 'lg', label: 'LG Energy_test', ticker: '373220', status: 'Active', layerLabel: 'Tier 2: Battery' },
  // OEM
  { id: 'tesla', label: 'Tesla', ticker: 'TSLA', status: 'Active', layerLabel: 'OEM' },
  { id: 'ford', label: 'Ford', ticker: 'F', status: 'Stable', layerLabel: 'OEM' },
  { id: 'gm', label: 'GM', ticker: 'GM', status: 'Stable', layerLabel: 'OEM' },
];

export const supplyChainEdges: Array<{ id: string; source: string; target: string }> = [
  { id: 'e1', source: 'catl', target: 'tesla' },
  { id: 'e2', source: 'byd', target: 'tesla' },
  { id: 'e3', source: 'lg', target: 'gm' },
  { id: 'e4', source: 'lg', target: 'ford' },
];

/**
 * Get supply chain data for layered DAG visualization
 * Applies layout using getLayoutedElements
 */
export const getSupplyChainData = () => {
  const nodes: GraphNode[] = supplyChainEntities.map((n) => ({
    id: n.id,
    type: 'company',
    data: mergeFinancials({
      label: n.label,
      ticker: n.ticker,
      status: n.status,
      layerLabel: n.layerLabel,
    }) as GraphNode['data'],
    position: { x: 0, y: 0 },
  }));

  const edges: GraphEdge[] = supplyChainEdges.map((e) => ({
    ...e,
    animated: true,
  }));

  // Apply layout (components expect layout to be applied)
  return getLayoutedElements(nodes as Node[], edges as Edge[], 'LR');
};

// ============================================
// 2. Hierarchical Tree (Ownership)
// ============================================

export interface OwnershipEntity {
  id: string;
  label: string;
  ticker?: string;
  isRoot?: boolean;
  ownership?: string;
}

export const ownershipEntities: OwnershipEntity[] = [
  { id: 'root', label: 'Siemens AG', ticker: 'SIE', isRoot: true },
  { id: 'sub1', label: 'Siemens Energy', ticker: 'ENR', ownership: 'Spin-off' },
  { id: 'sub2', label: 'Siemens Health', ticker: 'SHL', ownership: '75%' },
  { id: 'child1', label: 'Varian', ownership: '100%' },
];

export const ownershipEdges: Array<{ id: string; source: string; target: string; label?: string }> = [
  { id: 'e1', source: 'root', target: 'sub1', label: 'Spin-off' },
  { id: 'e2', source: 'root', target: 'sub2', label: '75%' },
  { id: 'e3', source: 'sub2', target: 'child1', label: '100%' },
];

/**
 * Get ownership data for hierarchical tree visualization
 * Applies layout using getLayoutedElements
 */
export const getOwnershipData = () => {
  const nodes: GraphNode[] = ownershipEntities.map((n) => ({
    id: n.id,
    type: 'company',
    data: mergeFinancials({
      label: n.label,
      ticker: n.ticker,
      isRoot: n.isRoot,
      ownership: n.ownership,
    }) as GraphNode['data'],
    position: { x: 0, y: 0 },
  }));

  const edges: GraphEdge[] = ownershipEdges;

  // Apply layout (components expect layout to be applied)
  return getLayoutedElements(nodes as Node[], edges as Edge[], 'TB');
};

// ============================================
// 3. Force-Directed Cluster (Competition)
// ============================================

export interface ClusterEntity {
  id: string;
  label: string;
  ticker: string;
  group: 'market_leader' | 'competitor' | 'partner';
}

export const clusterEntities: ClusterEntity[] = [
  { id: 'center', label: 'Tesla', ticker: 'TSLA', group: 'market_leader' },
  { id: 'c1', label: 'BYD', ticker: '1211', group: 'competitor' },
  { id: 'c2', label: 'Rivian', ticker: 'RIVN', group: 'competitor' },
  { id: 'c3', label: 'Lucid', ticker: 'LCID', group: 'competitor' },
  { id: 's1', label: 'Panasonic', ticker: '6752', group: 'partner' },
];

export const clusterEdges: Array<{ id: string; source: string; target: string }> = [
  { id: 'e1', source: 'center', target: 'c1' },
  { id: 'e2', source: 'center', target: 'c2' },
  { id: 'e3', source: 'center', target: 'c3' },
  { id: 'e4', source: 'center', target: 's1' },
];

/**
 * Get cluster data for force-directed graph visualization
 */
export const getClusterData = (): { nodes: GraphNode[]; edges: GraphEdge[] } => {
  const rand = () => Math.random() * 500;

  const nodes: GraphNode[] = clusterEntities.map((n, i) => ({
    id: n.id,
    type: 'company',
    data: mergeFinancials({
      label: n.label,
      ticker: n.ticker,
      group: n.group,
    }) as GraphNode['data'],
    position: i === 0 ? { x: 250, y: 250 } : { x: rand(), y: rand() },
  }));

  const edges: GraphEdge[] = clusterEdges.map((e) => ({
    ...e,
    type: 'default',
    data: { category: 'automation' },
  }));

  return { nodes, edges };
};

