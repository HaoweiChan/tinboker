/**
 * Data Transformers
 * 
 * Transform backend API responses to match frontend type expectations.
 * Handles field mapping, type conversions, and missing data generation.
 */

import type {
  GraphNode,
  GraphEdge,
  GraphData,
  CompanyDetail,
  StockEvent,
  StockNodeData,
  ChartDataPoint,
} from '../types';

import type { Episode as MockEpisode } from '../../data/mockData';
import type { Episode as ApiEpisode } from './index';

// Backend types (from OpenAPI schema)
interface BackendNode {
  id: string;
  type: string;
  data: {
    label: string;
    ticker: string;
    marketCapTier: 'large' | 'medium' | 'small';
  };
  position: { x: number; y: number };
}

interface BackendEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  data?: {
    category?: 'aiChips' | 'automation' | 'components';
  };
}

interface BackendCompanyDetail {
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
  stats: {
    volume: number;
    beta: number;
    volatility: number;
  };
  chartData: Array<{
    timestamp: number;
    price: number;
    date?: string;
    open?: number;
    high?: number;
    low?: number;
    close?: number;
    volume?: number;
  }>;
}

interface BackendStockEvent {
  id: string;
  type: 'earnings' | 'conference' | 'news' | 'dividend';
  date: number;
  title: string;
  description: string;
  content?: string | null;
  relatedTickers: string[];
}

// ============================================
// Graph Data Transformers
// ============================================

/**
 * Transform backend NodeData to frontend StockNodeData
 * Generates missing fields like history (sparkline data) from chartData if available
 */
function transformNodeData(
  backendData: BackendNode['data'],
  _ticker: string
): Partial<StockNodeData> {
  return {
    label: backendData.label,
    ticker: backendData.ticker,
    marketCapTier: backendData.marketCapTier,
    // Missing fields will need to be fetched separately or generated
    // history, name, price, changePct will be populated when node is hydrated with stock data
  };
}

/**
 * Transform backend Node to frontend GraphNode
 */
export function transformNode(backendNode: BackendNode): GraphNode {
  const nodeData = transformNodeData(backendNode.data, backendNode.data.ticker);
  // Extract marketCap and revenue separately to ensure they're numbers
  const { marketCap: rawMarketCap, revenue: rawRevenue, ...restNodeData } = nodeData;
  const marketCap = rawMarketCap !== undefined
    ? (typeof rawMarketCap === 'string' ? parseFloat(rawMarketCap) || 0 : rawMarketCap)
    : undefined;
  const revenue = rawRevenue !== undefined
    ? (typeof rawRevenue === 'string' ? parseFloat(rawRevenue) || 0 : rawRevenue)
    : undefined;

  return {
    id: backendNode.id,
    type: backendNode.type as 'company' | 'stock' | 'cluster',
    data: {
      label: backendNode.data.label,
      ticker: backendNode.data.ticker,
      marketCapTier: backendNode.data.marketCapTier,
      ...(marketCap !== undefined && { marketCap }),
      ...(revenue !== undefined && { revenue }),
      ...restNodeData,
    },
    position: backendNode.position,
  };
}

/**
 * Transform backend Edge to frontend GraphEdge
 */
export function transformEdge(backendEdge: BackendEdge): GraphEdge {
  return {
    id: backendEdge.id,
    source: backendEdge.source,
    target: backendEdge.target,
    label: backendEdge.label,
    data: backendEdge.data,
    type: undefined, // Not in backend schema
    animated: undefined, // Not in backend schema
  };
}

/**
 * Transform backend GraphData to frontend GraphData
 */
export function transformGraphData(backendData: {
  nodes: BackendNode[];
  edges: BackendEdge[];
}): GraphData {
  return {
    nodes: backendData.nodes.map(transformNode),
    edges: backendData.edges.map(transformEdge),
  };
}

// ============================================
// Company Detail Transformers
// ============================================

/**
 * Transform backend ChartDataPoint to frontend ChartDataPoint
 */
function transformChartDataPoint(
  backendPoint: BackendCompanyDetail['chartData'][0]
): ChartDataPoint {
  return {
    timestamp: backendPoint.timestamp,
    price: backendPoint.price,
    date: backendPoint.date,
    open: backendPoint.open,
    high: backendPoint.high,
    low: backendPoint.low,
    close: backendPoint.close ?? backendPoint.price, // Fallback to price if close not available
    volume: backendPoint.volume,
  };
}

/**
 * Transform backend CompanyDetail to frontend CompanyDetail
 */
export function transformCompanyDetail(backend: BackendCompanyDetail): CompanyDetail {
  return {
    ticker: backend.ticker,
    name: backend.name,
    price: backend.price,
    change: backend.change,
    changePercent: backend.changePercent,
    marketCap: backend.marketCap,
    revenue: backend.revenue,
    pe: backend.pe,
    dividendYield: backend.dividendYield,
    about: backend.about,
    stats: backend.stats,
    chartData: backend.chartData.map(transformChartDataPoint),
  };
}

// ============================================
// Stock Event Transformers
// ============================================

/**
 * Transform backend StockEvent to frontend StockEvent
 */
export function transformStockEvent(backend: BackendStockEvent): StockEvent {
  return {
    id: backend.id,
    type: backend.type as StockEvent['type'],
    date: backend.date,
    title: backend.title,
    description: backend.description,
    relatedTickers: backend.relatedTickers,
    // content field exists in backend but not used in frontend
    // icon field is optional in frontend, not in backend
  };
}

// ============================================
// Helper: Generate Sparkline History
// ============================================

/**
 * Generate normalized sparkline history (0-1 values) from chart data
 * Used when backend doesn't provide history field
 */
export function generateSparklineHistory(chartData: ChartDataPoint[]): number[] {
  if (chartData.length === 0) {
    return [];
  }

  const prices = chartData.map((point) => point.close ?? point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min;

  if (range === 0) {
    return prices.map(() => 0.5); // All same price, return middle value
  }

  // Normalize to 0-1 range
  return prices.map((price) => (price - min) / range);
}

/**
 * Hydrate node with stock data to populate missing fields
 * This is used when we need to enrich graph nodes with company details
 */
export function hydrateNodeWithStockData(
  node: GraphNode,
  companyDetail: CompanyDetail
): GraphNode {
  const history = generateSparklineHistory(companyDetail.chartData);

  return {
    ...node,
    data: {
      ...node.data,
      name: companyDetail.name,
      price: companyDetail.price,
      changePct: companyDetail.changePercent / 100, // Convert percentage to decimal
      history,
      marketCap: companyDetail.marketCap,
      revenue: companyDetail.revenue,
      marketCapVal: companyDetail.marketCap,
      revenueVal: companyDetail.revenue,
    },
  };
}


// ============================================
// Episode Transformers
// ============================================

/**
 * Transform API episode to mock episode format for EpisodeCard compatibility
 */
export function transformApiEpisodeToMock(apiEpisode: ApiEpisode): MockEpisode | null {
  if (!apiEpisode.id || !apiEpisode.podcast_name) return null;

  const summaryText = apiEpisode.summary_content || '';

  const summary: MockEpisode['summary'] = [{
    text: summaryText,
    highlights: [],
  }];

  // Calculate time ago
  const now = Date.now();
  const releaseDate = apiEpisode.spotify_release_date || apiEpisode.created_time;
  const releaseTime = typeof releaseDate === 'string'
    ? new Date(releaseDate).getTime()
    : releaseDate;
  const diffMs = now - releaseTime;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);
  let timeAgo = '';
  if (diffDays > 0) {
    timeAgo = `${diffDays}天前`;
  } else if (diffHours > 0) {
    timeAgo = `${diffHours}小時前`;
  } else {
    timeAgo = '剛剛';
  }

  // Determine styling
  const podcastName = apiEpisode.podcast_name || '';
  // Default to using the first character of the podcast name as avatar if no image
  const showAvatar = podcastName.charAt(0) || 'P';
  // Use a default neutral color class
  const showColorClass = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';

  // Get Spotify image (use first/smallest image from array, or null if not available)
  const imageUrl = apiEpisode.spotify_images && apiEpisode.spotify_images.length > 0
    ? apiEpisode.spotify_images[0] // First image is typically the smallest
    : undefined;

  // Get Spotify URI
  let spotifyUri: string | undefined = undefined;
  if (apiEpisode.spotify_id) {
    spotifyUri = `spotify:episode:${apiEpisode.spotify_id}`;
  } else if (apiEpisode.spotify_url) {
    const match = apiEpisode.spotify_url.match(/episode\/([a-zA-Z0-9]+)/);
    if (match && match[1]) {
      spotifyUri = `spotify:episode:${match[1]}`;
    } else if (apiEpisode.spotify_url.startsWith('spotify:episode:')) {
      spotifyUri = apiEpisode.spotify_url;
    }
  }

  return {
    id: apiEpisode.id,
    showName: podcastName,
    showAvatar,
    showColorClass,
    title: apiEpisode.episode_title || `EP${apiEpisode.episode_number || ''}`,
    timeAgo,
    isHot: false, // Could determine based on number_click or num_likes
    tags: apiEpisode.tags || [],
    summary,
    imageUrl,
    spotifyUri,
    keyInsights: apiEpisode.key_insights || [],
  };
}
