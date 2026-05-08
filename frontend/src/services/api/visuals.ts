import { apiClient } from './client';
import type { GraphData } from '../types';
import { GraphResponseSchema, InteractiveModelsResponseSchema, parseResponse } from '../../validation/schemas';


function processGraphDataResponse(data: any): GraphData {
  if (!data) {
    console.error('[API] processGraphDataResponse - data is null/undefined');
    throw new Error('API returned empty response');
  }
  if (import.meta.env.DEV) {
    console.log('[API] processGraphDataResponse - Raw data structure:', {
      hasData: !!data,
      hasDataData: !!(data && data.data),
      hasNodes: !!(data && data.nodes),
      hasEdges: !!(data && data.edges),
      dataKeys: data ? Object.keys(data) : [],
      dataDataKeys: data?.data ? Object.keys(data.data) : [],
      dataDataNodes: Array.isArray(data?.data?.nodes) ? data.data.nodes.length : 'not array',
      dataDataEdges: Array.isArray(data?.data?.edges) ? data.data.edges.length : 'not array',
    });
  }
  // Wrapped: { data: { nodes: [...], edges: [...] }, timestamp: "..." }
  if (data.data && typeof data.data === 'object' && !Array.isArray(data.data)) {
    if (Array.isArray(data.data.nodes) && Array.isArray(data.data.edges)) {
      try {
        const validated = parseResponse(GraphResponseSchema, data);
        if (import.meta.env.DEV) {
          console.log('[API] processGraphDataResponse - Using wrapped format (validated), nodes:', validated.data.nodes.length, 'edges:', validated.data.edges.length);
        }
        return validated.data;
      } catch (error) {
        console.warn('[API] Schema validation failed, but data structure looks correct, using direct access:', error);
        if (import.meta.env.DEV) {
          console.log('[API] processGraphDataResponse - Using wrapped format (direct access), nodes:', data.data.nodes.length, 'edges:', data.data.edges.length);
        }
        return { nodes: data.data.nodes, edges: data.data.edges } as GraphData;
      }
    }
  }
  // Direct: { nodes: [...], edges: [...] }
  if (Array.isArray(data.nodes) && Array.isArray(data.edges)) {
    if (import.meta.env.DEV) {
      console.log('[API] processGraphDataResponse - Using direct format, nodes:', data.nodes.length, 'edges:', data.edges.length);
    }
    return { nodes: data.nodes, edges: data.edges } as GraphData;
  }
  console.error('[API] Unexpected response format:', {
    data, hasData: !!data, hasDataData: !!(data && data.data),
    hasNodes: !!(data && data.nodes), hasEdges: !!(data && data.edges),
    dataDataHasNodes: !!(data?.data?.nodes), dataDataHasEdges: !!(data?.data?.edges),
    dataDataNodesIsArray: Array.isArray(data?.data?.nodes),
    dataDataEdgesIsArray: Array.isArray(data?.data?.edges),
    nodesIsArray: Array.isArray(data?.nodes), edgesIsArray: Array.isArray(data?.edges),
  });
  throw new Error('Invalid response format: expected GraphData with nodes and edges');
}

export async function getSupplyChainVisual(): Promise<GraphData> {
  try {
    const response = await apiClient.get('/api/visuals/supply-chain', { timeout: 30000 });
    if (import.meta.env.DEV) {
      console.log('[API] getSupplyChainVisual - Full response object:', {
        status: response.status, statusText: response.statusText,
        headers: response.headers, data: response.data,
        dataType: typeof response.data, isArray: Array.isArray(response.data),
        dataKeys: response.data ? Object.keys(response.data) : 'null/undefined',
      });
    }
    return processGraphDataResponse(response.data);
  } catch (error: any) {
    if (error.response && error.response.data) {
      if (import.meta.env.DEV) {
        console.warn('[API] getSupplyChainVisual - Error but found data in error.response.data:', error.response.data);
      }
      return processGraphDataResponse(error.response.data);
    }
    if (error.request && error.request.response) {
      try {
        const responseData = JSON.parse(error.request.response);
        if (import.meta.env.DEV) {
          console.warn('[API] getSupplyChainVisual - Found data in error.request.response:', responseData);
        }
        return processGraphDataResponse(responseData);
      } catch (_) { /* Not JSON */ }
    }
    throw error;
  }
}

export async function getOwnershipVisual(): Promise<GraphData> {
  try {
    const response = await apiClient.get('/api/visuals/ownership', { timeout: 30000 });
    if (import.meta.env.DEV) {
      console.log('[API] getOwnershipVisual response:', response.data);
    }
    return processGraphDataResponse(response.data);
  } catch (error: any) {
    if (error.response && error.response.data) {
      if (import.meta.env.DEV) {
        console.warn('[API] getOwnershipVisual - Error but found data in error.response.data:', error.response.data);
      }
      return processGraphDataResponse(error.response.data);
    }
    if (error.request && error.request.response) {
      try {
        const responseData = JSON.parse(error.request.response);
        if (import.meta.env.DEV) {
          console.warn('[API] getOwnershipVisual - Found data in error.request.response:', responseData);
        }
        return processGraphDataResponse(responseData);
      } catch (_) { /* Not JSON */ }
    }
    throw error;
  }
}

export async function getClusterVisual(): Promise<GraphData> {
  try {
    const response = await apiClient.get('/api/visuals/cluster', { timeout: 30000 });
    if (import.meta.env.DEV) {
      console.log('[API] getClusterVisual response:', response.data);
    }
    return processGraphDataResponse(response.data);
  } catch (error: any) {
    if (error.response && error.response.data) {
      if (import.meta.env.DEV) {
        console.warn('[API] getClusterVisual - Error but found data in error.response.data:', error.response.data);
      }
      return processGraphDataResponse(error.response.data);
    }
    if (error.request && error.request.response) {
      try {
        const responseData = JSON.parse(error.request.response);
        if (import.meta.env.DEV) {
          console.warn('[API] getClusterVisual - Found data in error.request.response:', responseData);
        }
        return processGraphDataResponse(responseData);
      } catch (_) { /* Not JSON */ }
    }
    throw error;
  }
}

export async function getInteractiveModels(): Promise<any[]> {
  const response = await apiClient.get('/api/visuals/interactive-models');
  if (response.data.data) {
    const validated = parseResponse(InteractiveModelsResponseSchema, response.data);
    return validated.data;
  }
  if (Array.isArray(response.data)) {
    return response.data;
  }
  return [];
}
