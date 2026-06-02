"""
Script to load graph data from mockData.ts into the database.

This script loads the three concept graphs (robotics, ai, energy) with their
nodes and edges into the database.

Usage:
    python scripts/load_graph_data.py
"""
import sys
import os

# Add backend root to path to import src modules (scripts/seed/ -> backend/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database.db import init_db, get_connection
from src.database.graph_db import create_graph
from src.models.graph import GraphData, Node, Edge, Position, NodeData, EdgeData


# Hardcoded graph data from mockData.ts
ROBOTICS_GRAPH = GraphData(
    nodes=[
        Node(
            id="TSLA",
            type="stock",
            data=NodeData(label="Tesla", ticker="TSLA", marketCapTier="large"),
            position=Position(x=0, y=0)
        ),
        Node(
            id="NVDA",
            type="stock",
            data=NodeData(label="NVIDIA", ticker="NVDA", marketCapTier="large"),
            position=Position(x=-100, y=200)
        ),
        Node(
            id="ABB",
            type="stock",
            data=NodeData(label="ABB Ltd", ticker="ABB", marketCapTier="medium"),
            position=Position(x=0, y=320)
        ),
        Node(
            id="ROK",
            type="stock",
            data=NodeData(label="Rockwell", ticker="ROK", marketCapTier="medium"),
            position=Position(x=0, y=120)
        ),
        Node(
            id="IRBT",
            type="stock",
            data=NodeData(label="iRobot", ticker="IRBT", marketCapTier="small"),
            position=Position(x=260, y=40)
        ),
        Node(
            id="INTC",
            type="stock",
            data=NodeData(label="Intel", ticker="INTC", marketCapTier="large"),
            position=Position(x=260, y=380)
        ),
    ],
    edges=[
        Edge(
            id="e1",
            source="TSLA",
            target="ROK",
            label="AI Chips",
            data=EdgeData(category="aiChips")
        ),
        Edge(
            id="e2",
            source="TSLA",
            target="NVDA",
            label="Automation",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e3",
            source="NVDA",
            target="INTC",
            label="Semiconductors",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e4",
            source="ROK",
            target="ABB",
            label="Components",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e5",
            source="IRBT",
            target="ABB",
            label="Components",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e6",
            source="ROK",
            target="ABB",
            label="AI/ML",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e7",
            source="ABB",
            target="INTC",
            label="Components",
            data=EdgeData(category="components")
        ),
    ]
)

AI_GRAPH = GraphData(
    nodes=[
        Node(
            id="NVDA",
            type="stock",
            data=NodeData(label="NVIDIA", ticker="NVDA", marketCapTier="large"),
            position=Position(x=300, y=50)
        ),
        Node(
            id="MSFT",
            type="stock",
            data=NodeData(label="Microsoft", ticker="MSFT", marketCapTier="large"),
            position=Position(x=100, y=200)
        ),
        Node(
            id="GOOGL",
            type="stock",
            data=NodeData(label="Google", ticker="GOOGL", marketCapTier="large"),
            position=Position(x=500, y=200)
        ),
        Node(
            id="AMD",
            type="stock",
            data=NodeData(label="AMD", ticker="AMD", marketCapTier="large"),
            position=Position(x=300, y=350)
        ),
        Node(
            id="PLTR",
            type="stock",
            data=NodeData(label="Palantir", ticker="PLTR", marketCapTier="medium"),
            position=Position(x=150, y=450)
        ),
        Node(
            id="SNOW",
            type="stock",
            data=NodeData(label="Snowflake", ticker="SNOW", marketCapTier="medium"),
            position=Position(x=450, y=450)
        ),
    ],
    edges=[
        Edge(
            id="e1",
            source="NVDA",
            target="MSFT",
            label="GPUs",
            data=EdgeData(category="aiChips")
        ),
        Edge(
            id="e2",
            source="NVDA",
            target="GOOGL",
            label="AI Hardware",
            data=EdgeData(category="aiChips")
        ),
        Edge(
            id="e3",
            source="NVDA",
            target="AMD",
            label="Competition",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e4",
            source="MSFT",
            target="PLTR",
            label="Cloud Services",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e5",
            source="GOOGL",
            target="SNOW",
            label="Data Analytics",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e6",
            source="AMD",
            target="PLTR",
            label="Processing",
            data=EdgeData(category="components")
        ),
    ]
)

ENERGY_GRAPH = GraphData(
    nodes=[
        Node(
            id="TSLA",
            type="stock",
            data=NodeData(label="Tesla", ticker="TSLA", marketCapTier="large"),
            position=Position(x=300, y=100)
        ),
        Node(
            id="ENPH",
            type="stock",
            data=NodeData(label="Enphase", ticker="ENPH", marketCapTier="medium"),
            position=Position(x=150, y=250)
        ),
        Node(
            id="FSLR",
            type="stock",
            data=NodeData(label="First Solar", ticker="FSLR", marketCapTier="medium"),
            position=Position(x=450, y=250)
        ),
        Node(
            id="NEE",
            type="stock",
            data=NodeData(label="NextEra Energy", ticker="NEE", marketCapTier="large"),
            position=Position(x=300, y=400)
        ),
        Node(
            id="PLUG",
            type="stock",
            data=NodeData(label="Plug Power", ticker="PLUG", marketCapTier="small"),
            position=Position(x=100, y=450)
        ),
        Node(
            id="SEDG",
            type="stock",
            data=NodeData(label="SolarEdge", ticker="SEDG", marketCapTier="small"),
            position=Position(x=500, y=450)
        ),
    ],
    edges=[
        Edge(
            id="e1",
            source="TSLA",
            target="ENPH",
            label="Solar",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e2",
            source="TSLA",
            target="FSLR",
            label="Solar Panels",
            data=EdgeData(category="components")
        ),
        Edge(
            id="e3",
            source="ENPH",
            target="NEE",
            label="Grid Integration",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e4",
            source="FSLR",
            target="NEE",
            label="Utility Scale",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e5",
            source="NEE",
            target="PLUG",
            label="Hydrogen",
            data=EdgeData(category="automation")
        ),
        Edge(
            id="e6",
            source="ENPH",
            target="SEDG",
            label="Inverters",
            data=EdgeData(category="components")
        ),
    ]
)


def load_graphs():
    """Load all graph data into the database"""
    print("Initializing database...")
    init_db()
    
    print("\nLoading graph data...")
    
    graphs_to_load = [
        ("robotics", ROBOTICS_GRAPH),
        ("ai", AI_GRAPH),
        ("energy", ENERGY_GRAPH),
    ]
    
    loaded_count = 0
    skipped_count = 0
    
    for concept_id, graph_data in graphs_to_load:
        print(f"\nLoading {concept_id} graph...")
        print(f"  Nodes: {len(graph_data.nodes)}")
        print(f"  Edges: {len(graph_data.edges)}")
        
        # Check if graph already exists for this concept
        from src.database.graph_db import get_all_graphs
        existing_graphs = get_all_graphs(sort_by="concept_id")
        existing_for_concept = [g for g in existing_graphs if g.get("concept_id") == concept_id]
        
        if existing_for_concept:
            print(f"  ⚠️  Graph for concept '{concept_id}' already exists. Skipping...")
            skipped_count += 1
            continue
        
        # Create graph with a fixed ID for consistency
        graph_id = f"{concept_id}-graph-001"
        result = create_graph(concept_id, graph_data, graph_id=graph_id)
        
        if result:
            print(f"  ✅ Successfully loaded graph: {result}")
            loaded_count += 1
        else:
            print(f"  ❌ Failed to load graph for concept '{concept_id}'")
    
    print("\n" + "=" * 50)
    print(f"Summary:")
    print(f"  Loaded: {loaded_count} graphs")
    print(f"  Skipped: {skipped_count} graphs (already exist)")
    print("=" * 50)


if __name__ == "__main__":
    try:
        load_graphs()
        print("\n✅ Graph data loading completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error loading graph data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

