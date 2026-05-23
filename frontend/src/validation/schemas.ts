/**
 * Zod validation schemas matching OpenAPI specification
 * 
 * These schemas provide runtime validation for API responses.
 * They are derived from the OpenAPI spec in schemas/openapi.yaml
 * 
 * Usage:
 *   import { CompanyDetailSchema } from './validation/schemas';
 *   const validated = CompanyDetailSchema.parse(apiResponse);
 * 
 * @see docs/openapi-zod-integration.md
 */

import { z, ZodError } from 'zod';

// ============================================
// Concept Schemas
// ============================================

export const ConceptMetadataSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  icon: z.string(),
  gradient: z.string(),
});

export const ConceptsResponseSchema = z.object({
  data: z.array(ConceptMetadataSchema),
  timestamp: z.string().datetime(),
});

export type ConceptMetadata = z.infer<typeof ConceptMetadataSchema>;
export type ConceptsResponse = z.infer<typeof ConceptsResponseSchema>;

// ============================================
// Graph Schemas
// ============================================

export const PositionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

export const GraphNodeDataSchema = z.object({
  label: z.string(),
  ticker: z.string().optional(),
  marketCapTier: z.enum(['large', 'medium', 'small']).optional().catch(undefined),
});

export const GraphNodeSchema = z.object({
  id: z.string(),
  type: z.string(),
  data: GraphNodeDataSchema,
  position: PositionSchema.optional(),
});

export const GraphEdgeDataSchema = z.object({
  category: z.enum(['aiChips', 'automation', 'components']).optional().catch(undefined),
});

export const GraphEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  label: z.string().optional(),
  data: GraphEdgeDataSchema.optional(),
});

export const GraphDataSchema = z.object({
  nodes: z.array(GraphNodeSchema),
  edges: z.array(GraphEdgeSchema),
});

export const GraphResponseSchema = z.object({
  data: GraphDataSchema,
  timestamp: z.string().datetime(),
});

export type Position = z.infer<typeof PositionSchema>;
export type GraphNodeData = z.infer<typeof GraphNodeDataSchema>;
export type GraphNode = z.infer<typeof GraphNodeSchema>;
export type GraphEdgeData = z.infer<typeof GraphEdgeDataSchema>;
export type GraphEdge = z.infer<typeof GraphEdgeSchema>;
export type GraphData = z.infer<typeof GraphDataSchema>;
export type GraphResponse = z.infer<typeof GraphResponseSchema>;

// ============================================
// Visual Graph Schemas
// ============================================

const numberOrString = z.union([z.number(), z.string()]);

export const VisualGraphNodeDataSchema = z.object({
  label: z.string(),
  ticker: z.string().optional(),
  status: z.string().optional(),
  layerLabel: z.string().optional(),
  ownership: z.string().optional(),
  group: z.string().optional(),
  price: z.number().optional(),
  changePct: z.number().optional(),
  marketCap: numberOrString.optional(),
  revenue: numberOrString.optional(),
  marketCapVal: z.number().optional(),
  revenueVal: z.number().optional(),
  history: z.array(z.number()).optional(),
  isRoot: z.boolean().optional(),
});

export const VisualGraphNodeSchema = z
  .object({
    id: z.string(),
    type: z.string(),
    data: VisualGraphNodeDataSchema,
    position: PositionSchema,
  })
  .passthrough();

export const VisualGraphEdgeSchema = z
  .object({
    id: z.string(),
    source: z.string(),
    target: z.string(),
    label: z.string().optional(),
    type: z.string().optional(),
    animated: z.boolean().optional(),
    data: GraphEdgeDataSchema.optional(),
  })
  .passthrough();

export const VisualGraphDataSchema = z.object({
  nodes: z.array(VisualGraphNodeSchema),
  edges: z.array(VisualGraphEdgeSchema),
});

export const VisualGraphResponseSchema = z.object({
  data: VisualGraphDataSchema,
  timestamp: z.string().datetime(),
});

export type VisualGraphNodeData = z.infer<typeof VisualGraphNodeDataSchema>;
export type VisualGraphNode = z.infer<typeof VisualGraphNodeSchema>;
export type VisualGraphEdge = z.infer<typeof VisualGraphEdgeSchema>;
export type VisualGraphData = z.infer<typeof VisualGraphDataSchema>;
export type VisualGraphResponse = z.infer<typeof VisualGraphResponseSchema>;

// ============================================
// Company Schemas
// ============================================

export const ChartDataPointSchema = z.object({
  timestamp: z.number().int(),
  price: z.number(),
  date: z.string().optional(),
  open: z.number().optional(),
  high: z.number().optional(),
  low: z.number().optional(),
  close: z.number().optional(),
  volume: z.number().int().optional(),
});

export const CompanyStatsSchema = z.object({
  volume: z.number().int().catch(0),
  beta: z.number().catch(0),
  volatility: z.number().catch(0),
});

export const CompanyDetailSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  price: z.number().catch(0),
  change: z.number().catch(0),
  changePercent: z.number().catch(0),
  marketCap: z.number().int().catch(0),
  revenue: z.number().int().optional(),
  pe: z.number().optional(),
  dividendYield: z.number().optional(),
  about: z.string().catch(''),
  stats: CompanyStatsSchema,
  chartData: z.array(ChartDataPointSchema),
});

export const CompanyResponseSchema = z.object({
  data: CompanyDetailSchema,
  timestamp: z.string().datetime(),
});

export type ChartDataPoint = z.infer<typeof ChartDataPointSchema>;
export type CompanyStats = z.infer<typeof CompanyStatsSchema>;
export type CompanyDetail = z.infer<typeof CompanyDetailSchema>;
export type CompanyResponse = z.infer<typeof CompanyResponseSchema>;

// ============================================
// Top Mover Schemas
// ============================================

export const TopMoverSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  price: z.number(),
  change: z.number(),
  changePercent: z.number(),
});

export const TopMoversResponseSchema = z.object({
  data: z.array(TopMoverSchema),
  timestamp: z.string().datetime(),
});

export type TopMover = z.infer<typeof TopMoverSchema>;
export type TopMoversResponse = z.infer<typeof TopMoversResponseSchema>;

// ============================================
// Stock Event Schemas
// ============================================

export const StockEventTypeSchema = z.enum([
  'conference',
  'earnings',
  'news',
  'dividend',
  'custom',
]);

export const StockEventSchema = z.object({
  id: z.string(),
  type: StockEventTypeSchema,
  date: z.number().int(),
  title: z.string(),
  description: z.string(),
  relatedTickers: z.array(z.string()),
  icon: z.string().optional(),
});

export const EventsResponseSchema = z.object({
  data: z.array(StockEventSchema),
  timestamp: z.string().datetime(),
});

export const EventMovementIndicatorSchema = z.object({
  eventId: z.string(),
  ticker: z.string(),
  priceAtEvent: z.number(),
  priceAfter1d: z.number().optional(),
  priceAfter1w: z.number().optional(),
  priceAfter1m: z.number().optional(),
  changePercent1d: z.number().optional(),
  changePercent1w: z.number().optional(),
  changePercent1m: z.number().optional(),
});

export type StockEventType = z.infer<typeof StockEventTypeSchema>;
export type StockEvent = z.infer<typeof StockEventSchema>;
export type EventsResponse = z.infer<typeof EventsResponseSchema>;
export type EventMovementIndicator = z.infer<typeof EventMovementIndicatorSchema>;

// ============================================
// Error Schema
// ============================================

export const ErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});

export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;

// ============================================
// Sector/Industry Schemas
// ============================================

export const SectorBubbleDataSchema = z.object({
  id: z.string(),
  name: z.string(),
  label: z.string().optional(),
  value: z.number(),
  marketCap: z.number().optional(),
  return: z.number(),
  returnRate: z.number().optional(),
  volume: z.number().optional(),
});

export const SectorStatSchema = z.object({
  label: z.string(),
  value: z.number(),
});

export const SectorPerformanceStatsSchema = z.object({
  day: z.array(SectorStatSchema),
  week: z.array(SectorStatSchema),
});

export const TreeMapItemSchema: z.ZodType<TreeMapItem> = z.lazy(() =>
  z.object({
    id: z.string(),
    name: z.string(),
    value: z.number(),
    change: z.number(),
    ticker: z.string().optional(),
    price: z.string().optional(),
    children: z.array(TreeMapItemSchema).optional(),
  })
);

export type SectorBubbleData = z.infer<typeof SectorBubbleDataSchema>;
export type SectorStat = z.infer<typeof SectorStatSchema>;
export type SectorPerformanceStats = z.infer<typeof SectorPerformanceStatsSchema>;
export type TreeMapItem = {
  id: string;
  name: string;
  value: number;
  change: number;
  ticker?: string;
  price?: string;
  children?: TreeMapItem[];
};

// ============================================
// Interactive Model Schemas
// ============================================

export const InteractiveEntitySchema = z.object({
  symbol: z.string(),
  price: z.string(),
  change: z.string(),
  isPositive: z.boolean(),
});

export const InteractiveModelDataSchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  date: z.string(),
  category: z.string(),
  summary: z.string(),
  graphTypeLabel: z.string(),
  graphType: z.enum(['layered', 'force', 'sankey', 'tree']).catch('force'),
  tickers: z.array(InteractiveEntitySchema),
  indices: z.array(InteractiveEntitySchema),
});

export type InteractiveEntity = z.infer<typeof InteractiveEntitySchema>;
export type InteractiveModelData = z.infer<typeof InteractiveModelDataSchema>;

export const InteractiveModelsResponseSchema = z.object({
  data: z.array(InteractiveModelDataSchema),
  timestamp: z.string().datetime(),
});

export type InteractiveModelsResponse = z.infer<typeof InteractiveModelsResponseSchema>;

// ============================================
// Price Series Schemas
// ============================================

export const PricePointSchema = z.object({
  time: z.string(),
  value: z.number(),
});

export type PricePoint = z.infer<typeof PricePointSchema>;

// ============================================
// Validation Helpers
// ============================================

/**
 * Safely parse API response with Zod schema
 * Returns success/error result instead of throwing
 */
export function safeParseResponse<T>(
  schema: z.ZodType<T>,
  data: unknown
): { success: true; data: T } | { success: false; error: string } {
  try {
    const result = schema.safeParse(data);
    if (result.success) {
      return { success: true, data: result.data };
    }
    // Handle ZodError - format validation errors
    if (result.error instanceof ZodError) {
      const issues = result.error.issues;
      if (issues && Array.isArray(issues) && issues.length > 0) {
        return {
          success: false,
          error: issues.map((e) => {
            const path = e.path && e.path.length > 0 ? e.path.join('.') : 'root';
            return `${path}: ${e.message}`;
          }).join(', '),
        };
      }
    }
    // Fallback for unexpected error structure
    return {
      success: false,
      error: result.error?.message || String(result.error) || 'Unknown validation error',
    };
  } catch (error) {
    // Safety net in case something unexpected happens
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Parse API response with Zod schema
 * Throws descriptive error on validation failure
 */
export function parseResponse<T>(schema: z.ZodType<T>, data: unknown): T {
  try {
    return schema.parse(data);
  } catch (error) {
    if (error instanceof z.ZodError) {
      const message = error.issues
        .map((e) => `${e.path.join('.')}: ${e.message}`)
        .join(', ');
      throw new Error(`API response validation failed: ${message}`);
    }
    throw error;
  }
}

