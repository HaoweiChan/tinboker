import { apiClient } from './client';
import type { GraphData } from '../types';
import { GraphResponseSchema, parseResponse } from '../../validation/schemas';


export async function getSortedGraphs(sortBy: string = 'concept_id'): Promise<any[]> {
  const response = await apiClient.get('/api/graphs', {
    params: { sort_by: sortBy },
  });
  return Array.isArray(response.data) ? response.data : [];
}

export async function createGraph(data: {
  conceptId: string;
  nodes: Array<{
    id: string;
    type?: string;
    label: string;
    ticker: string;
    marketCapTier: string;
    positionX: number;
    positionY: number;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    label: string;
    category: string;
  }>;
}): Promise<void> {
  await apiClient.post('/api/graphs', data);
}

export async function getGraphById(graphId: string): Promise<GraphData> {
  const response = await apiClient.get(`/api/graphs/${graphId}`);
  const validated = parseResponse(GraphResponseSchema, response.data);
  return validated.data;
}

export async function deleteGraph(graphId: string): Promise<void> {
  await apiClient.delete(`/api/graphs/${graphId}`);
}

export async function modifyNode(
  graphId: string,
  nodeId: string,
  data: {
    label?: string | null;
    ticker?: string | null;
    marketCapTier?: string | null;
    positionX?: number | null;
    positionY?: number | null;
  }
): Promise<void> {
  await apiClient.put(`/api/graphs/${graphId}/nodes/${nodeId}`, data);
}

export async function deleteNode(graphId: string, nodeId: string): Promise<void> {
  await apiClient.delete(`/api/graphs/${graphId}/nodes/${nodeId}`);
}

export async function modifyEdge(
  graphId: string,
  edgeId: string,
  data: {
    source?: string | null;
    target?: string | null;
    label?: string | null;
    category?: string | null;
  }
): Promise<void> {
  await apiClient.put(`/api/graphs/${graphId}/edges/${edgeId}`, data);
}

export async function deleteEdge(graphId: string, edgeId: string): Promise<void> {
  await apiClient.delete(`/api/graphs/${graphId}/edges/${edgeId}`);
}
