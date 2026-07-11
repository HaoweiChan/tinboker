// Core company data interface
export interface Company {
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
  icon_url?: string;
}

// Node display modes
export type NodeDisplayMode = 'default' | 'marketCap' | 'revenue';

// React Flow node structure
// `type` is intentionally a free string: the backend emits node kinds beyond the
// canonical set (e.g. 'person', 'Investor'), so validation/schemas.ts keeps it loose.
export interface GraphNode {
  id: string;
  type: string;
  data: ({
    label: string;
    ticker?: string;
    marketCapTier?: 'large' | 'medium' | 'small';
    marketCap?: number;
    revenue?: number;
  } & Partial<StockNodeData>);
  position?: { x: number; y: number };
}

// Stock node data for new circular design with sparklines
export interface StockNodeData {
  ticker: string;
  name: string;
  price: number;
  changePct: number; // e.g. 0.0344 for +3.44%
  history: number[]; // normalized 0-1 values for sparkline
  category?: 'aiChips' | 'automation' | 'components';
  status?: string;
  type?: string;
  marketCapTier?: 'large' | 'medium' | 'small';
  marketCap?: number | string;
  revenue?: number | string;
  marketCapVal?: number;
  revenueVal?: number;
  theme?: 'dark' | 'light'; // injected at runtime
  logoUrl?: string; // optional for future
  label?: string; // company label (for compatibility)
  isCustom?: boolean;
  customColor?: string;
  customMarketCap?: number;
  customRevenue?: number;
  displayMode?: DisplayMode;
  nodeStyle?: NodeStyle;

  // New fields for archetypes
  layerLabel?: string; // For LAYERED_DAG
  rank?: number; // For LAYERED_DAG
  isRoot?: boolean; // For TREE
  ownership?: string; // For TREE (often on edge, but sometimes on node)
  group?: string; // For CLUSTER
}

// Custom node data extends StockNodeData
export interface CustomNodeData extends StockNodeData {
  isCustom: boolean;
  customColor?: string;
  customMarketCap?: number;
  customRevenue?: number;
}

// Cluster node data for ETFs and portfolios
export interface ClusterNodeData extends StockNodeData {
  clusterType: 'etf' | 'portfolio' | 'custom';
  holdings: Array<{
    ticker: string;
    weight: number;
    name?: string;
  }>;
  totalValue?: number;
}

// React Flow edge structure
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type?: string;
  data?: {
    category?: 'aiChips' | 'automation' | 'components';
  };
  animated?: boolean;
}

// Complete graph data
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// Chart data point - supports both simple price data and OHLCV data
export interface ChartDataPoint {
  timestamp: number;
  price: number; // For backward compatibility
  date?: string; // Formatted date for display
  // OHLCV data (optional, for candlestick charts)
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
}

// Extended company details with stats and chart data
export interface CompanyDetail extends Company {
  stats: {
    volume: number;
    beta: number;
    volatility: number;
  };
  chartData: ChartDataPoint[];
}

// Concept metadata - fetched from backend
export interface ConceptMetadata {
  id: string;              // URL-friendly ID (e.g., 'robotics', 'ai', 'quantum')
  title: string;           // Display title (e.g., 'Robotics & Automation')
  description: string;     // Short description for card display
  icon: string;            // Icon/emoji representation
  gradient: string;        // Tailwind gradient classes for styling
}

// Available concept types - now dynamic string instead of fixed union
export type ConceptType = string;

// Top movers data
export interface TopMover extends Pick<Company, 'ticker' | 'name' | 'change' | 'changePercent' | 'price' | 'icon_url'> { }

// Tag data
export interface Tag {
  id: string;
  name: string;
  episode_count: number;
}

// Tags response
export interface TagsResponse {
  tags: Tag[];
}

// Episodes by tag response
export interface EpisodesByTagResponse {
  tag: string;
  episodes: any[]; // Episode[] - using any to avoid circular dependency
  total: number;
}

// Market index data
export interface MarketIndex {
  id: string;
  name: string;
  ticker: string;
  value: string;
  change: string;
  isPositive: boolean;
}


// Stock Overlay View Types

// Event types for stock events
export type StockEventType = 'conference' | 'earnings' | 'news' | 'dividend' | 'custom';

// Stock event data structure
export interface StockEvent {
  id: string;
  type: StockEventType;
  date: number; // timestamp
  title: string;
  description: string;
  relatedTickers: string[]; // stocks affected by this event
  icon?: string; // optional custom icon
}

// Event movement indicator (price change after event)
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

// Timeframe options for chart
export type TimeframeOption = '1H' | '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | 'YTD' | 'ALL';

// Multi-stock overlay data
export interface StockOverlayData {
  ticker: string;
  name: string;
  priceData: ChartDataPoint[];
  events: StockEvent[];
  currentPrice: number;
  color: string; // chart color for this stock
}

// Custom graph metadata and data
export interface CustomGraph {
  id: string;
  title: string;
  description: string;
  icon?: string;
  thumbnail?: string;
  isSystem: boolean;
  isPinned: boolean;
  createdAt: number;
  updatedAt: number;
  createdBy?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata?: {
    tags?: string[];
    category?: string;
  };
}

// Company search result
export interface CompanySearchResult {
  ticker: string;
  name: string;
  marketCap?: number;
  revenue?: number;
  logoUrl?: string;
}

// --- Merged Visual Archetypes Types ---

export const GraphType = {
  HOME: 'HOME',
  DASHBOARD: 'DASHBOARD',
  DAG: 'DAG',
  TREE: 'TREE',
  CLUSTER: 'CLUSTER',
  SANKEY: 'SANKEY',
  SECTOR_BUBBLE: 'SECTOR_BUBBLE',
  TREEMAP: 'TREEMAP',
  PERFORMANCE_BARS: 'PERFORMANCE_BARS',
  NEWS: 'NEWS'
} as const;

export type GraphType = typeof GraphType[keyof typeof GraphType];

export type VisualizationType = 'LAYERED_DAG' | 'TREE' | 'CLUSTER' | 'SANKEY';

export interface UnifiedGraphResponse {
  graph_id: string;
  title: string;
  description: string;
  visualization_type: VisualizationType;
  timestamp: string;
  data: any; // Payload varies by visualization_type
}

export const DisplayMode = {
  PRICE: 'PRICE',
  MARKET_CAP: 'MARKET_CAP',
  REVENUE: 'REVENUE'
} as const;

export type DisplayMode = typeof DisplayMode[keyof typeof DisplayMode];

export const NodeStyle = {
  GHOST: 'GHOST',
  SOLID: 'SOLID'
} as const;

export type NodeStyle = typeof NodeStyle[keyof typeof NodeStyle];

export interface CompanyData {
  label: string;
  ticker?: string;
  status: 'Active' | 'Pending' | 'Risk' | 'Stable';
  type?: 'Supplier' | 'Manufacturer' | 'Distributor' | 'Holding' | 'Subsidiary' | 'Investor' | 'Board';

  // Financial Data
  price?: string;
  change?: string;
  changeVal?: number; // Numeric for coloring
  marketCap?: string;
  marketCapVal?: number; // For scaling
  revenue?: string;
  revenueVal?: number; // For scaling
  history?: number[]; // Sparkline data points (0-1 normalized or raw)

  // UI State (passed from parent)
  displayMode?: DisplayMode;
  nodeStyle?: NodeStyle;
  value?: string; // Legacy
}

export interface SectorBubbleData {
  id: string;
  name: string;
  value: number; // Market Cap
  return: number | null; // Percentage Return
  x?: number;
  y?: number;
  r?: number;
  volume?: number;
  marketCap?: number;
  returnRate?: number | null;
  label?: string;
}

export interface TreeMapItem {
  id: string;
  name: string;
  value: number; // Market Cap
  change: number; // Performance %
  children?: TreeMapItem[];
  ticker?: string;
  price?: string;
  history?: number[];
}

export interface SectorStat {
  label: string;
  value: number;
}

export interface SankeyData {
  nodes: { id: string; nodeColor?: string }[];
  links: {
    source: string;
    target: string;
    value: number;
    startColor?: string;
    endColor?: string;
    customLabel?: string; // NEW: Custom label for the link
  }[];
}

export interface ContentIndexResponse {
  tickers: string[];
}

export interface ContentAsset {
  ticker: string;
  svg_url: string;
  article_url: string;
  ttl_seconds: number;
}

// ============================================
// WebSocket Message Types
// ============================================

// Real-time price update from WebSocket
export interface RealTimePriceUpdate {
  type: 'price_update';
  ticker: string;
  price: number;              // Current price
  change: number;             // Absolute change from previous close
  changePercent: number;      // Percentage change (e.g., 2.5 for +2.5%)
  volume?: number;            // Trading volume
  timestamp: number;          // Unix timestamp (milliseconds)
  marketStatus?: 'open' | 'closed' | 'pre-market' | 'after-hours';

  // Optional extended data
  bid?: number;              // Bid price
  ask?: number;              // Ask price
  high?: number;             // Day's high
  low?: number;              // Day's low
  open?: number;             // Opening price
  previousClose?: number;    // Previous day's close
}

// Client → Server Messages
export interface SubscribeMessage {
  type: 'subscribe';
  tickers: string[];  // Array of ticker symbols to subscribe to
}

export interface UnsubscribeMessage {
  type: 'unsubscribe';
  tickers: string[];  // Array of ticker symbols to unsubscribe from
}

export interface HeartbeatMessage {
  type: 'ping';
}

// Server → Client Messages
export interface PriceUpdateMessage {
  type: 'price_update';
  data: RealTimePriceUpdate;
}

export interface SubscriptionConfirmation {
  type: 'subscribed';
  tickers: string[];
}

export interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
}

export interface HeartbeatResponse {
  type: 'pong';
}

export type WebSocketMessage =
  | SubscribeMessage
  | UnsubscribeMessage
  | HeartbeatMessage
  | PriceUpdateMessage
  | SubscriptionConfirmation
  | ErrorMessage
  | HeartbeatResponse;

// ============================================
// Ticker Recommendation Types
// ============================================

export interface Reason {
  title: string;
  category?: string;
  description: string;
  start_time: number;
  end_time: number;
  start_index: number;
  end_index: number;
}

// Spec § 4.3 — was a free string under the legacy Postgres path; tightened to
// the enum the agents pipeline emits.
export type Severity = 'HIGH' | 'MEDIUM' | 'LOW';

export interface Risk {
  title: string;
  severity?: Severity;
  description: string;
  start_time: number;
  end_time: number;
  start_index: number;
  end_index: number;
}

// Shape per docs/firestore-contract.md § 4.2 / § 5.3.
export type SentimentLabel =
  | 'STRONG_BULLISH'
  | 'BULLISH'
  | 'NEUTRAL'
  | 'BEARISH'
  | 'STRONG_BEARISH';

export interface TickerTrending {
  ticker: string;
  /** zh-TW display name (台積電, 輝達, …) when available — buzz endpoint only. */
  name?: string | null;
  count: number;
  sentiment_label: SentimentLabel;
  sentiment_counts?: {
    bull: number;
    neutral: number;
    bear: number;
  };
  last_mentioned: string;
}

// Spec § 4.3. No `id` (composite path {episode_id}/tickers/{ticker} is the
// identity); no `sentiment_score` (internal-only, never returned by the API).
export interface TickerInsight {
  episode_id: string;
  podcaster?: string;
  podcast_launch_time: string;
  ticker: string;
  bluf_thesis: string;
  time_horizon: string;
  sentiment_label: SentimentLabel;
  reasons: Reason[];
  risks: Risk[];
  created_at: string;
  /** Source episode title — populated by /recent (blended feed) so the card can
   *  show which episode mentioned the ticker. */
  episode_title?: string;
}

// Forward price return per pick, from /api/stocks/batch-prices-windows.
// Each window is the % move from the mention-date close to the close N calendar
// days later; `null` until the window has fully elapsed (UI renders "—"). `since`
// is the mention→today move. Keyed in responses by `"{TICKER}:{reference_ms}"`.
export interface PickWindowReturns {
  baseline: number | null;
  d7: number | null;
  d30: number | null;
  d90: number | null;
  since: number | null;
}
