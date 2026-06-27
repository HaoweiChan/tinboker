/**
 * Temporary type definitions for mock data
 * These will be replaced by generated types from OpenAPI spec
 * 
 * SOURCE: Extracted from src/services/mockData.ts
 */

// ============================================
// Concept Types
// ============================================

export interface ConceptMetadata {
  id: string;
  title: string;
  description: string;
  icon: string;
  gradient: string;
}

export type ConceptType = string;

// ============================================
// Graph Types
// ============================================

export interface GraphNode {
  id: string;
  type: 'company' | 'stock' | 'cluster';
  data: {
    label: string;
    ticker: string;
    marketCapTier: 'large' | 'medium' | 'small';
  };
  position: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  data?: {
    category?: 'aiChips' | 'automation' | 'components';
  };
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ============================================
// Chart Data Types
// ============================================

export interface ChartDataPoint {
  timestamp: number;
  price: number;
  date?: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
}

// ============================================
// Company Types
// ============================================

export interface CompanyStats {
  volume: number;
  beta: number;
  volatility: number;
}

export interface CompanyDetail {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  marketCap: number;
  revenue?: number;
  pe?: number;
  dividendYield?: number;
  about: string;
  stats: CompanyStats;
  chartData: ChartDataPoint[];
}

// ============================================
// Top Mover Types
// ============================================

export interface TopMover {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

// ============================================
// Stock Event Types
// ============================================

export type StockEventType = 'conference' | 'earnings' | 'news' | 'dividend' | 'custom';

export interface StockEvent {
  id: string;
  type: StockEventType;
  date: number;
  title: string;
  description: string;
  relatedTickers: string[];
  icon?: string;
}

export interface EventMovementIndicator {
  eventId: string;
  ticker: string;
  priceAtEvent: number;
  priceAfter1d?: number;
  priceAfter1w?: number;
  priceAfter1m?: number;
  changePercent1d?: number;
  changePercent1w?: number;
  changePercent1m?: number;
}

// ============================================
// Sector/Industry Data Types
// ============================================

export interface SectorBubbleData {
  id: string;
  name: string;
  label?: string;
  value: number;
  marketCap?: number;
  return: number;
  returnRate?: number;
  volume?: number;
  subLabel?: string; // optional muted line in the hover card (e.g. raw episode count)
}

export interface SectorStat {
  label: string;
  value: number;
}

export interface TreeMapItem {
  id: string;
  name: string;
  value: number;
  change: number;
  children?: TreeMapItem[];
  ticker?: string;
  price?: string;
  history?: number[];
}

// ============================================
// Extended Stock Node Data (for visual archetypes)
// ============================================

export interface StockNodeData {
  ticker?: string;
  name?: string;
  label?: string;
  price?: number;
  changePct?: number;
  history?: number[];
  category?: 'aiChips' | 'automation' | 'components';
  status?: string;
  type?: string;
  marketCapTier?: 'large' | 'medium' | 'small';
  marketCap?: number | string;
  revenue?: number | string;
  marketCapVal?: number;
  revenueVal?: number;
  // Archetype-specific fields
  layerLabel?: string;
  rank?: number;
  isRoot?: boolean;
  ownership?: string;
  group?: string;
}

