"""Build a graph.json from the wiki using Graphify (optional).

This is the bridge between the wiki (markdown-first) and graph-based queries.
Run ``build_wiki_graph()`` to produce ``wiki-graph/graph.json`` that can be
queried via Graphify's BFS/DFS traversal.

Graphify is an optional dependency — the wiki works without it.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


WIKI_ROOT = Path(__file__).resolve().parents[3] / "wiki"
GRAPH_OUT = Path(__file__).resolve().parents[3] / "wiki-graph"


def _graphify_available() -> bool:
    """Check if graphify is importable."""
    try:
        import graphify  # noqa: F401
        return True
    except ImportError:
        return False


def build_wiki_graph(
    wiki_root: Optional[Path] = None,
    graph_out: Optional[Path] = None,
) -> Optional[Path]:
    """Run Graphify on the wiki folder to produce graph.json.

    Returns the path to graph.json if successful, None otherwise.
    """
    root = wiki_root or WIKI_ROOT
    out = graph_out or GRAPH_OUT
    out.mkdir(parents=True, exist_ok=True)

    if not _graphify_available():
        print(
            "  ⚠ graphify not installed — skipping graph build. "
            "Install with: pip install graphifyy"
        )
        return None

    from graphify.detect import detect
    from graphify.extract import collect_files, extract
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.export import to_json

    # Detect files
    detection = detect(root)
    total_files = detection.get("total_files", 0)
    if total_files == 0:
        print("  ⚠ No wiki files found — nothing to graph.")
        return None

    print(f"  📊 Building graph from {total_files} wiki files...")

    # AST extraction (for any code files, unlikely in wiki but safe)
    all_files = []
    for ftype, fpaths in detection.get("files", {}).items():
        for fp in fpaths:
            p = Path(fp)
            if p.is_dir():
                all_files.extend(collect_files(p))
            else:
                all_files.append(p)

    ast_result = extract(all_files) if all_files else {"nodes": [], "edges": []}

    # Build graph
    graph = build_from_json(ast_result)
    communities = cluster(graph)
    cohesion = score_all(graph, communities)

    # Export
    graph_json_path = out / "graph.json"
    to_json(graph, communities, str(graph_json_path))

    print(
        f"  ✓ Graph built: {graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges, {len(communities)} communities"
    )
    print(f"  ✓ Saved to {graph_json_path}")

    return graph_json_path


def query_graph(
    question: str,
    mode: str = "bfs",
    budget: int = 2000,
    graph_out: Optional[Path] = None,
) -> str:
    """Query the wiki graph using BFS or DFS traversal.

    Returns a plain-text answer fragment based on the graph structure.
    """
    out = graph_out or GRAPH_OUT
    graph_json = out / "graph.json"

    if not graph_json.exists():
        return "No graph found. Run build_wiki_graph() first."

    import networkx as nx
    from networkx.readwrite import json_graph

    data = json.loads(graph_json.read_text())
    G = json_graph.node_link_graph(data, edges="links")

    terms = [t.lower() for t in question.split() if len(t) > 3]
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:3]]

    if not start_nodes:
        return f"No matching nodes found for: {question}"

    subgraph_nodes: set = set(start_nodes)
    subgraph_edges: list = []

    if mode == "dfs":
        visited: set = set()
        stack = [(n, 0) for n in reversed(start_nodes)]
        while stack:
            node, depth = stack.pop()
            if node in visited or depth > 6:
                continue
            visited.add(node)
            subgraph_nodes.add(node)
            for neighbor in G.neighbors(node):
                if neighbor not in visited:
                    stack.append((neighbor, depth + 1))
                    subgraph_edges.append((node, neighbor))
    else:
        frontier = set(start_nodes)
        for _ in range(3):
            next_frontier: set = set()
            for n in frontier:
                for neighbor in G.neighbors(n):
                    if neighbor not in subgraph_nodes:
                        next_frontier.add(neighbor)
                        subgraph_edges.append((n, neighbor))
            subgraph_nodes.update(next_frontier)
            frontier = next_frontier

    lines = [
        f"Traversal: {mode.upper()} | Start: "
        f"{[G.nodes[n].get('label', n) for n in start_nodes]} | "
        f"{len(subgraph_nodes)} nodes"
    ]
    for nid in subgraph_nodes:
        d = G.nodes[nid]
        lines.append(f"  NODE {d.get('label', nid)} [src={d.get('source_file', '')}]")
    for u, v in subgraph_edges:
        if u in subgraph_nodes and v in subgraph_nodes:
            d = G.edges[u, v]
            lines.append(
                f"  EDGE {G.nodes[u].get('label', u)} "
                f"--{d.get('relation', '')} [{d.get('confidence', '')}]--> "
                f"{G.nodes[v].get('label', v)}"
            )

    output = "\n".join(lines)
    char_budget = budget * 4
    if len(output) > char_budget:
        output = output[:char_budget] + "\n... (truncated)"
    return output
