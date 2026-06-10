"""
Graph API router
"""
from fastapi import APIRouter, HTTPException, Path, Depends
from typing import List
from src.services.graph import GraphService
from src.models.graph import GraphData, GraphCreate, NodeUpdate, EdgeUpdate
from src.auth.admin_auth import get_content_write_access, AdminAccess

router = APIRouter(prefix="/api/graphs", tags=["graphs"])

# Initialize service
graph_service = GraphService()


@router.get("", response_model=List[dict])
async def get_sorted_graphs(sort_by: str = "concept_id"):
    """
    Get sorted graphs list
    
    Query params:
    - sort_by: Sort field (concept_id, created_at, updated_at)
    """
    graphs = await graph_service.get_sorted_graphs(sort_by=sort_by)
    return graphs


@router.get("/{graph_id}", response_model=GraphData)
async def get_graph_by_id(graph_id: str = Path(..., description="Graph ID")):
    """
    Get graph by ID
    
    Returns complete graph with nodes and edges
    """
    graph = await graph_service.get_graph_by_id(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph {graph_id} not found")
    return graph


@router.post("", status_code=201)
async def create_graph(
    graph_create: GraphCreate,
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Create new graph
    
    Creates a graph with nodes and edges. Stock information will be fetched for nodes.
    """
    graph_id = await graph_service.create_graph(graph_create)
    if not graph_id:
        raise HTTPException(status_code=400, detail="Failed to create graph")
    return {"id": graph_id, "message": "Graph created successfully"}


@router.put("/{graph_id}/nodes/{node_id}")
async def modify_node(
    graph_id: str = Path(..., description="Graph ID"),
    node_id: str = Path(..., description="Node ID"),
    node_update: NodeUpdate = ...,
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Modify node in graph
    
    Updates node position and/or data
    """
    success = await graph_service.update_node(graph_id, node_id, node_update)
    if not success:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found in graph {graph_id}")
    return {"message": "Node updated successfully"}


@router.put("/{graph_id}/edges/{edge_id}")
async def modify_edge(
    graph_id: str = Path(..., description="Graph ID"),
    edge_id: str = Path(..., description="Edge ID"),
    edge_update: EdgeUpdate = ...,
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Modify edge in graph
    
    Updates edge data
    """
    success = await graph_service.update_edge(graph_id, edge_id, edge_update)
    if not success:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found in graph {graph_id}")
    return {"message": "Edge updated successfully"}


@router.delete("/{graph_id}")
async def delete_graph(
    graph_id: str = Path(..., description="Graph ID"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Delete graph
    
    Deletes graph and all its nodes and edges
    """
    success = await graph_service.delete_graph(graph_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Graph {graph_id} not found")
    return {"message": "Graph deleted successfully"}


@router.delete("/{graph_id}/nodes/{node_id}")
async def delete_node(
    graph_id: str = Path(..., description="Graph ID"),
    node_id: str = Path(..., description="Node ID"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Delete node from graph
    
    Deletes node and all connected edges
    """
    success = await graph_service.delete_node(graph_id, node_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found in graph {graph_id}")
    return {"message": "Node deleted successfully"}


@router.delete("/{graph_id}/edges/{edge_id}")
async def delete_edge(
    graph_id: str = Path(..., description="Graph ID"),
    edge_id: str = Path(..., description="Edge ID"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Delete edge from graph
    """
    success = await graph_service.delete_edge(graph_id, edge_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found in graph {graph_id}")
    return {"message": "Edge deleted successfully"}

