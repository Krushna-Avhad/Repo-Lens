"""
Knowledge Graph Builder Agent
Uses NetworkX in-memory directed graph.
Neo4j removed — NetworkX handles all graph operations.
"""
from __future__ import annotations
import json
from typing import Any
import networkx as nx


class GraphBuilderAgent:

    def __init__(self):
        self.driver = None  # always None — kept for compatibility
        self._memory_graphs: dict[str, Any] = {}
        print("[GraphBuilder] Using NetworkX in-memory graph ✓")

    # ── Public ──────────────────────────────────────────────────────────

    def build_graph(self, parsed: dict) -> dict:
        return self._build_memory(parsed["repo_id"], parsed)

    def get_graph(self, repo_id: str) -> dict:
        return self._get_memory_graph(repo_id)

    def query_dependencies(self, repo_id: str, node_id: str) -> list[dict]:
        return self._memory_deps(repo_id, node_id)

    def get_metrics(self, repo_id: str) -> dict:
        graph = self.get_graph(repo_id)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        n = max(len(nodes), 1)
        e = len(edges)
        max_possible = n * (n - 1)
        coupling = (e / max_possible) if max_possible else 0.0
        avg_cx = sum(
            nd.get("properties", {}).get("complexity", 1)
            for nd in nodes
        ) / n
        return {
            "complexity_score":      round(min(avg_cx / 10, 1.0), 3),
            "coupling_score":        round(coupling, 3),
            "maintainability_score": round(
                max(0.0, 1.0 - (coupling * 0.5 + min(avg_cx / 20, 0.5))), 3
            ),
        }

    # ── Build ────────────────────────────────────────────────────────────

    def _build_memory(self, repo_id: str, data: dict) -> dict:
        G = nx.DiGraph()

        # Add file nodes
        for f in data.get("files", []):
            G.add_node(
                f["id"],
                label    = f["path"],
                type     = "file",
                **{k: v for k, v in f.items()
                   if isinstance(v, (str, int, float, bool))}
            )

        # Add function nodes + CONTAINS edges
        for fn in data.get("functions", []):
            G.add_node(
                fn["id"],
                label = fn["name"],
                type  = "function",
                **{k: v for k, v in fn.items()
                   if isinstance(v, (str, int, float, bool))}
            )
            fid = f"file:{fn['file']}"
            if fid in G:
                G.add_edge(fid, fn["id"], relationship="contains")

        # Add class nodes + DEFINES edges
        for cls in data.get("classes", []):
            G.add_node(
                cls["id"],
                label = cls["name"],
                type  = "class",
                **{k: v for k, v in cls.items()
                   if isinstance(v, (str, int, float, bool))}
            )
            fid = f"file:{cls['file']}"
            if fid in G:
                G.add_edge(fid, cls["id"], relationship="defines")

        # Wire CALLS edges between functions
        name_to_id = {
            G.nodes[n].get("label", ""): n
            for n in G.nodes
            if G.nodes[n].get("type") == "function"
        }
        for fn in data.get("functions", []):
            for called in fn.get("calls", []):
                target = name_to_id.get(called)
                if target and target != fn["id"]:
                    G.add_edge(fn["id"], target, relationship="calls")

        # Wire IMPORTS edges between files
        path_map = {
            G.nodes[n].get("path", ""): n
            for n in G.nodes
            if G.nodes[n].get("type") == "file"
        }
        for imp in data.get("imports", []):
            mod = imp.get("module")
            if not mod or not isinstance(mod, str):
                continue
            from_id = f"file:{imp['from_file']}"
            for path, fid in path_map.items():
                if not path or not isinstance(path, str):
                    continue
                try:
                    if mod in path or path.replace("/", ".").endswith(mod):
                        if from_id != fid and from_id in G:
                            G.add_edge(from_id, fid, relationship="imports")
                        break
                except TypeError:
                    continue

        self._memory_graphs[repo_id] = G
        print(f"[GraphBuilder] Graph built — {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges for repo {repo_id}")
        return {"status": "built", "repo_id": repo_id}

    # ── Query ────────────────────────────────────────────────────────────

    def _get_memory_graph(self, repo_id: str) -> dict:
        G = self._memory_graphs.get(repo_id)
        if not G:
            return {"nodes": [], "edges": []}
        return {
            "nodes": [
                {
                    "id":    n,
                    "label": G.nodes[n].get("label", G.nodes[n].get("name", n)),
                    "type":  G.nodes[n].get("type", "node"),
                    "properties": {
                        k: v for k, v in G.nodes[n].items()
                        if isinstance(v, (str, int, float, bool))
                    },
                }
                for n in G.nodes
            ],
            "edges": [
                {
                    "source":       u,
                    "target":       v,
                    "relationship": G[u][v].get("relationship", "relates"),
                }
                for u, v in G.edges
            ],
        }

    def _memory_deps(self, repo_id: str, node_id: str) -> list[dict]:
        G = self._memory_graphs.get(repo_id)
        if not G or node_id not in G:
            return []
        visited, result, queue = set(), [], [(node_id, 0)]
        while queue:
            curr, depth = queue.pop(0)
            if curr in visited or depth > 3:
                continue
            visited.add(curr)
            for nb in G.successors(curr):
                result.append({
                    "id":   nb,
                    "name": G.nodes[nb].get("label", nb),
                    "rel":  G[curr][nb].get("relationship", "relates"),
                })
                queue.append((nb, depth + 1))
        return result