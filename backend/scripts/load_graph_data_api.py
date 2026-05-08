"""
Script to load graph data to production API using HTTP requests.

This script loads the three concept graphs (robotics, ai, energy) with their
nodes and edges into the production database via API.

Usage:
    python scripts/load_graph_data_api.py [--url https://api.tinboker.com]
"""
import sys
import os
import argparse
import requests
from typing import List, Dict, Any

# Hardcoded graph data from mockData.ts
ROBOTICS_GRAPH = {
    "conceptId": "robotics",
    "nodes": [
        {
            "id": "TSLA",
            "type": "stock",
            "label": "Tesla",
            "ticker": "TSLA",
            "marketCapTier": "large",
            "positionX": 0,
            "positionY": 0
        },
        {
            "id": "NVDA",
            "type": "stock",
            "label": "NVIDIA",
            "ticker": "NVDA",
            "marketCapTier": "large",
            "positionX": -100,
            "positionY": 200
        },
        {
            "id": "ABB",
            "type": "stock",
            "label": "ABB Ltd",
            "ticker": "ABB",
            "marketCapTier": "medium",
            "positionX": 0,
            "positionY": 320
        },
        {
            "id": "ROK",
            "type": "stock",
            "label": "Rockwell",
            "ticker": "ROK",
            "marketCapTier": "medium",
            "positionX": 0,
            "positionY": 120
        },
        {
            "id": "IRBT",
            "type": "stock",
            "label": "iRobot",
            "ticker": "IRBT",
            "marketCapTier": "small",
            "positionX": 260,
            "positionY": 40
        },
        {
            "id": "INTC",
            "type": "stock",
            "label": "Intel",
            "ticker": "INTC",
            "marketCapTier": "large",
            "positionX": 260,
            "positionY": 380
        },
    ],
    "edges": [
        {
            "id": "e1",
            "source": "TSLA",
            "target": "ROK",
            "label": "AI Chips",
            "category": "aiChips"
        },
        {
            "id": "e2",
            "source": "TSLA",
            "target": "NVDA",
            "label": "Automation",
            "category": "automation"
        },
        {
            "id": "e3",
            "source": "NVDA",
            "target": "INTC",
            "label": "Semiconductors",
            "category": "components"
        },
        {
            "id": "e4",
            "source": "ROK",
            "target": "ABB",
            "label": "Components",
            "category": "components"
        },
        {
            "id": "e5",
            "source": "IRBT",
            "target": "ABB",
            "label": "Components",
            "category": "components"
        },
        {
            "id": "e6",
            "source": "ROK",
            "target": "ABB",
            "label": "AI/ML",
            "category": "automation"
        },
        {
            "id": "e7",
            "source": "ABB",
            "target": "INTC",
            "label": "Components",
            "category": "components"
        },
    ]
}

AI_GRAPH = {
    "conceptId": "ai",
    "nodes": [
        {
            "id": "NVDA",
            "type": "stock",
            "label": "NVIDIA",
            "ticker": "NVDA",
            "marketCapTier": "large",
            "positionX": 300,
            "positionY": 50
        },
        {
            "id": "MSFT",
            "type": "stock",
            "label": "Microsoft",
            "ticker": "MSFT",
            "marketCapTier": "large",
            "positionX": 100,
            "positionY": 200
        },
        {
            "id": "GOOGL",
            "type": "stock",
            "label": "Google",
            "ticker": "GOOGL",
            "marketCapTier": "large",
            "positionX": 500,
            "positionY": 200
        },
        {
            "id": "AMD",
            "type": "stock",
            "label": "AMD",
            "ticker": "AMD",
            "marketCapTier": "large",
            "positionX": 300,
            "positionY": 350
        },
        {
            "id": "PLTR",
            "type": "stock",
            "label": "Palantir",
            "ticker": "PLTR",
            "marketCapTier": "medium",
            "positionX": 150,
            "positionY": 450
        },
        {
            "id": "SNOW",
            "type": "stock",
            "label": "Snowflake",
            "ticker": "SNOW",
            "marketCapTier": "medium",
            "positionX": 450,
            "positionY": 450
        },
    ],
    "edges": [
        {
            "id": "e1",
            "source": "NVDA",
            "target": "MSFT",
            "label": "GPUs",
            "category": "aiChips"
        },
        {
            "id": "e2",
            "source": "NVDA",
            "target": "GOOGL",
            "label": "AI Hardware",
            "category": "aiChips"
        },
        {
            "id": "e3",
            "source": "NVDA",
            "target": "AMD",
            "label": "Competition",
            "category": "components"
        },
        {
            "id": "e4",
            "source": "MSFT",
            "target": "PLTR",
            "label": "Cloud Services",
            "category": "automation"
        },
        {
            "id": "e5",
            "source": "GOOGL",
            "target": "SNOW",
            "label": "Data Analytics",
            "category": "automation"
        },
        {
            "id": "e6",
            "source": "AMD",
            "target": "PLTR",
            "label": "Processing",
            "category": "components"
        },
    ]
}

ENERGY_GRAPH = {
    "conceptId": "energy",
    "nodes": [
        {
            "id": "TSLA",
            "type": "stock",
            "label": "Tesla",
            "ticker": "TSLA",
            "marketCapTier": "large",
            "positionX": 300,
            "positionY": 100
        },
        {
            "id": "ENPH",
            "type": "stock",
            "label": "Enphase",
            "ticker": "ENPH",
            "marketCapTier": "medium",
            "positionX": 150,
            "positionY": 250
        },
        {
            "id": "FSLR",
            "type": "stock",
            "label": "First Solar",
            "ticker": "FSLR",
            "marketCapTier": "medium",
            "positionX": 450,
            "positionY": 250
        },
        {
            "id": "NEE",
            "type": "stock",
            "label": "NextEra Energy",
            "ticker": "NEE",
            "marketCapTier": "large",
            "positionX": 300,
            "positionY": 400
        },
        {
            "id": "PLUG",
            "type": "stock",
            "label": "Plug Power",
            "ticker": "PLUG",
            "marketCapTier": "small",
            "positionX": 100,
            "positionY": 450
        },
        {
            "id": "SEDG",
            "type": "stock",
            "label": "SolarEdge",
            "ticker": "SEDG",
            "marketCapTier": "small",
            "positionX": 500,
            "positionY": 450
        },
    ],
    "edges": [
        {
            "id": "e1",
            "source": "TSLA",
            "target": "ENPH",
            "label": "Solar",
            "category": "components"
        },
        {
            "id": "e2",
            "source": "TSLA",
            "target": "FSLR",
            "label": "Solar Panels",
            "category": "components"
        },
        {
            "id": "e3",
            "source": "ENPH",
            "target": "NEE",
            "label": "Grid Integration",
            "category": "automation"
        },
        {
            "id": "e4",
            "source": "FSLR",
            "target": "NEE",
            "label": "Utility Scale",
            "category": "automation"
        },
        {
            "id": "e5",
            "source": "NEE",
            "target": "PLUG",
            "label": "Hydrogen",
            "category": "automation"
        },
        {
            "id": "e6",
            "source": "ENPH",
            "target": "SEDG",
            "label": "Inverters",
            "category": "components"
        },
    ]
}


def check_existing_graphs(base_url: str, concept_id: str) -> bool:
    """Check if a graph already exists for the given concept_id"""
    try:
        response = requests.get(f"{base_url}/api/graphs?sort_by=concept_id", timeout=10)
        if response.status_code == 200:
            graphs = response.json()
            existing = [g for g in graphs if g.get("concept_id") == concept_id]
            return len(existing) > 0
    except Exception as e:
        print(f"  ⚠️  Error checking existing graphs: {e}")
    return False


def load_graph_via_api(base_url: str, graph_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Load a graph via API
    
    Returns:
        (success: bool, message: str)
    """
    try:
        response = requests.post(
            f"{base_url}/api/graphs",
            json=graph_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 201:
            result = response.json()
            graph_id = result.get("id", "unknown")
            return True, graph_id
        else:
            error_detail = response.json().get("detail", "Unknown error")
            return False, f"API error: {error_detail}"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def load_graphs(base_url: str = "https://api.tinboker.com", force: bool = False):
    """Load all graph data into the database via API"""
    print(f"Loading graph data to: {base_url}")
    print("=" * 50)
    
    # Test connection
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code != 200:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
        print("✅ Server connection successful")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False
    
    graphs_to_load = [
        ("robotics", ROBOTICS_GRAPH),
        ("ai", AI_GRAPH),
        ("energy", ENERGY_GRAPH),
    ]
    
    loaded_count = 0
    skipped_count = 0
    failed_count = 0
    
    for concept_id, graph_data in graphs_to_load:
        print(f"\nLoading {concept_id} graph...")
        print(f"  Nodes: {len(graph_data['nodes'])}")
        print(f"  Edges: {len(graph_data['edges'])}")
        
        # Check if graph already exists
        if not force and check_existing_graphs(base_url, concept_id):
            print(f"  ⚠️  Graph for concept '{concept_id}' already exists. Use --force to overwrite.")
            skipped_count += 1
            continue
        
        # Load graph via API
        success, message = load_graph_via_api(base_url, graph_data)
        
        if success:
            print(f"  ✅ Successfully loaded graph: {message}")
            loaded_count += 1
        else:
            print(f"  ❌ Failed to load graph: {message}")
            failed_count += 1
    
    print("\n" + "=" * 50)
    print(f"Summary:")
    print(f"  ✅ Loaded: {loaded_count} graphs")
    print(f"  ⏭️  Skipped: {skipped_count} graphs (already exist)")
    print(f"  ❌ Failed: {failed_count} graphs")
    print("=" * 50)
    
    return failed_count == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load graph data to production API")
    parser.add_argument(
        "--url",
        default="https://api.tinboker.com",
        help="Base URL of the API (default: https://api.tinboker.com)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload even if graphs already exist"
    )
    
    args = parser.parse_args()
    
    try:
        success = load_graphs(base_url=args.url, force=args.force)
        if success:
            print("\n✅ Graph data loading completed successfully!")
            sys.exit(0)
        else:
            print("\n⚠️  Graph data loading completed with some failures.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n❌ Loading interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error loading graph data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


