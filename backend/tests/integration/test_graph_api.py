"""
Integration tests for graph API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.auth.admin_auth import get_content_write_access, AdminAccess
from src.routers.graph import graph_service


@pytest.fixture(autouse=True)
def _stub_node_stock_fetch(monkeypatch):
    """create_graph enriches every node via the live stock API. Stub it so these
    integration tests never make a real external HTTP call — that call has no hard
    timeout on all paths and hangs on CI's network (the job ran for 30+ min before
    this stub), and integration tests must not depend on third-party APIs anyway.
    """
    async def _no_stock(_ticker):
        return None
    monkeypatch.setattr(graph_service, "_fetch_node_stock_info_async", _no_stock)


@pytest.fixture
def client(test_db):
    """Create test client.

    Graph mutations (POST/PUT/DELETE) require content-write access; override the
    dependency so these functional tests can exercise them. Auth enforcement itself
    is covered by test_create_graph_requires_auth (which uses an un-overridden client).
    """
    app.dependency_overrides[get_content_write_access] = lambda: AdminAccess(
        email="test-admin@tinboker.local", user_id="test-admin"
    )
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.pop(get_content_write_access, None)


@pytest.fixture
def sample_graph_create():
    """Sample graph creation data"""
    return {
        "conceptId": "ai",
        "nodes": [
            {
                "id": "NVDA",
                "type": "stock",
                "label": "NVIDIA",
                "ticker": "NVDA",
                "marketCapTier": "large",
                "positionX": 100.0,
                "positionY": 200.0,
            },
            {
                "id": "MSFT",
                "type": "stock",
                "label": "Microsoft",
                "ticker": "MSFT",
                "marketCapTier": "large",
                "positionX": 300.0,
                "positionY": 400.0,
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "NVDA",
                "target": "MSFT",
                "label": "Partnership",
                "category": "automation",
            },
        ],
    }


class TestGraphAPI:
    """Test graph API endpoints"""
    
    def test_get_sorted_graphs(self, client, test_db, sample_graph_create):
        """Test GET /api/graphs"""
        # Create test graph via API
        response = client.post("/api/graphs", json=sample_graph_create)
        assert response.status_code == 201
        
        response = client.get("/api/graphs?sort_by=concept_id")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
    
    def test_get_graph_by_id(self, client, test_db, sample_graph_create):
        """Test GET /api/graphs/{graph_id}"""
        # Create graph via API
        create_response = client.post("/api/graphs", json=sample_graph_create)
        assert create_response.status_code == 201
        graph_id = create_response.json()["id"]
        
        response = client.get(f"/api/graphs/{graph_id}")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
    
    def test_get_graph_not_found(self, client, test_db):
        """Test GET /api/graphs/{graph_id} with non-existent ID"""
        response = client.get("/api/graphs/nonexistent")
        assert response.status_code == 404

    def test_create_graph_requires_auth(self, test_db, sample_graph_create):
        """Graph mutations must reject anonymous callers (no content-write override)."""
        anon = TestClient(app)
        assert anon.post("/api/graphs", json=sample_graph_create).status_code in (401, 403)
        assert anon.delete("/api/graphs/whatever").status_code in (401, 403)
        # Reads stay public.
        assert anon.get("/api/graphs").status_code == 200
    
    def test_create_graph(self, client, test_db, sample_graph_create):
        """Test POST /api/graphs"""
        response = client.post("/api/graphs", json=sample_graph_create)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Graph created successfully"
    
    def test_modify_node(self, client, test_db, sample_graph_create):
        """Test PUT /api/graphs/{graph_id}/nodes/{node_id}"""
        create_response = client.post("/api/graphs", json=sample_graph_create)
        graph_id = create_response.json()["id"]
        
        node_update = {
            "positionX": 150.0,
            "positionY": 250.0,
        }
        
        response = client.put(f"/api/graphs/{graph_id}/nodes/NVDA", json=node_update)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Node updated successfully"
    
    def test_modify_edge(self, client, test_db, sample_graph_create):
        """Test PUT /api/graphs/{graph_id}/edges/{edge_id}"""
        create_response = client.post("/api/graphs", json=sample_graph_create)
        graph_id = create_response.json()["id"]
        
        edge_update = {
            "label": "Updated Label",
            "category": "updated_category",
        }
        
        response = client.put(f"/api/graphs/{graph_id}/edges/e1", json=edge_update)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Edge updated successfully"
    
    def test_delete_graph(self, client, test_db, sample_graph_create):
        """Test DELETE /api/graphs/{graph_id}"""
        create_response = client.post("/api/graphs", json=sample_graph_create)
        graph_id = create_response.json()["id"]
        
        response = client.delete(f"/api/graphs/{graph_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Graph deleted successfully"
        
        # Verify graph is deleted
        get_response = client.get(f"/api/graphs/{graph_id}")
        assert get_response.status_code == 404
    
    def test_delete_node(self, client, test_db, sample_graph_create):
        """Test DELETE /api/graphs/{graph_id}/nodes/{node_id}"""
        create_response = client.post("/api/graphs", json=sample_graph_create)
        graph_id = create_response.json()["id"]
        
        response = client.delete(f"/api/graphs/{graph_id}/nodes/NVDA")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Node deleted successfully"
        
        # Verify node is deleted
        get_response = client.get(f"/api/graphs/{graph_id}")
        assert get_response.status_code == 200
        graph_data = get_response.json()
        assert len(graph_data["nodes"]) == 1
        assert not any(node["id"] == "NVDA" for node in graph_data["nodes"])
    
    def test_delete_edge(self, client, test_db, sample_graph_create):
        """Test DELETE /api/graphs/{graph_id}/edges/{edge_id}"""
        create_response = client.post("/api/graphs", json=sample_graph_create)
        graph_id = create_response.json()["id"]
        
        response = client.delete(f"/api/graphs/{graph_id}/edges/e1")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Edge deleted successfully"
        
        # Verify edge is deleted
        get_response = client.get(f"/api/graphs/{graph_id}")
        assert get_response.status_code == 200
        graph_data = get_response.json()
        assert len(graph_data["edges"]) == 0

