"""
Impact Analysis, Refactoring, and Debugging Agents
All powered by Groq + Graph RAG (via GraphRAGEngine).
These are thin wrappers; the heavy lifting is in graph_rag.py.
"""
from __future__ import annotations
from typing import Any
from core.groq_client import chat


# ── Impact Analysis Agent ──────────────────────────────────────────────────

class ImpactAnalysisAgent:

    def __init__(self, graph_builder, explanation_agent=None):
        self.graph_builder = graph_builder

    def analyze(self, repo_id: str, target_node_id: str, question: str) -> dict:
        graph   = self.graph_builder.get_graph(repo_id)
        affected = self._find_affected(graph, target_node_id)
        ripple   = self._compute_ripple(graph, target_node_id)

        answer = self._template_impact(target_node_id, affected, ripple)
        return {
            "answer":          answer,
            "agent":           "impact",
            "context_nodes":   [a["id"] for a in affected[:5]],
            "confidence":      0.85,
            "suggestions":     [f"Write tests for `{a['label']}`" for a in affected[:3]],
            "impact_data": {
                "directly_affected": len(affected),
                "ripple_depth":      ripple["depth"],
                "risk_level":        ripple["risk"],
                "affected_nodes":    affected[:10],
            },
        }

    def _find_affected(self, graph: dict, node_id: str) -> list[dict]:
        edges     = graph.get("edges", [])
        nodes_map = {n["id"]: n for n in graph.get("nodes", [])}
        return [
            nodes_map.get(e["source"], {"id": e["source"], "label": e["source"], "type": "unknown"})
            for e in edges if e["target"] == node_id
        ]

    def _compute_ripple(self, graph: dict, node_id: str) -> dict:
        edges     = graph.get("edges", [])
        nodes_map = {n["id"]: n for n in graph.get("nodes", [])}
        visited, queue, depth, ripple_nodes = {node_id}, [(node_id, 0)], 0, []
        while queue:
            curr, d = queue.pop(0)
            depth = max(depth, d)
            for e in edges:
                if e["target"] == curr and e["source"] not in visited:
                    visited.add(e["source"])
                    ripple_nodes.append(nodes_map.get(e["source"], {}))
                    if d < 4:
                        queue.append((e["source"], d + 1))
        count = len(ripple_nodes)
        risk  = "HIGH" if count > 10 else "MEDIUM" if count > 3 else "LOW"
        return {"depth": depth, "count": count, "risk": risk, "nodes": ripple_nodes}

    def _template_impact(self, node_id: str, affected: list, ripple: dict) -> str:
        emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(ripple["risk"], "⚪")
        lines = [
            f"## Impact Analysis: `{node_id}`\n",
            f"**Risk Level:** {emoji} {ripple['risk']}\n",
            f"**Directly affected:** {len(affected)} component(s)",
            f"**Ripple depth:** {ripple['depth']} levels",
            f"**Total affected:** {ripple['count']} nodes\n",
        ]
        if affected:
            lines.append("### Directly affected components:")
            for n in affected[:6]:
                lines.append(f"  - `{n.get('label', n.get('id','?'))}` ({n.get('type','node')})")
        return "\n".join(lines)


# ── Refactoring Agent ──────────────────────────────────────────────────────

class RefactoringAgent:

    def __init__(self, graph_builder, explanation_agent=None):
        self.graph_builder = graph_builder

    def analyze(self, repo_id: str) -> dict:
        graph  = self.graph_builder.get_graph(repo_id)
        smells = self._detect_smells(graph)
        return {
            "answer":        self._template_refactor(smells),
            "agent":         "refactor",
            "context_nodes": [s["node_id"] for s in smells[:5]],
            "confidence":    0.8,
            "suggestions":   [s["suggestion"] for s in smells[:5]],
            "smells":        smells,
        }

    def _detect_smells(self, graph: dict) -> list[dict]:
        nodes  = graph.get("nodes", [])
        edges  = graph.get("edges", [])
        smells = []

        in_deg:  dict[str, int] = {}
        out_deg: dict[str, int] = {}
        for e in edges:
            out_deg[e["source"]] = out_deg.get(e["source"], 0) + 1
            in_deg[e["target"]]  = in_deg.get(e["target"],  0) + 1

        adj: dict[str, list] = {}
        for e in edges:
            adj.setdefault(e["source"], []).append(e["target"])

        def has_cycle(node, visited, stack):
            visited.add(node); stack.add(node)
            for nb in adj.get(node, []):
                if nb not in visited:
                    if has_cycle(nb, visited, stack): return True
                elif nb in stack:
                    return True
            stack.discard(node); return False

        seen: set = set()
        for nd in nodes:
            nid = nd["id"]
            if nid not in seen:
                if has_cycle(nid, seen, set()):
                    smells.append({"type": "circular_dependency", "node_id": nid, "severity": "HIGH",
                                   "suggestion": f"Break circular dependency involving `{nid}`"})

        for nd in nodes:
            nid   = nd["id"]
            total = in_deg.get(nid, 0) + out_deg.get(nid, 0)
            if total > 8:
                smells.append({"type": "god_node", "node_id": nid, "severity": "MEDIUM",
                                "connections": total,
                                "suggestion": f"`{nd['label']}` has {total} connections — consider splitting"})

        for nd in nodes:
            c = nd.get("properties", {}).get("complexity", 0)
            if isinstance(c, (int, float)) and c > 8:
                smells.append({"type": "high_complexity", "node_id": nd["id"], "severity": "MEDIUM",
                                "complexity": c,
                                "suggestion": f"`{nd['label']}` has complexity {c} — extract helpers"})

        return smells[:15]

    def _template_refactor(self, smells: list) -> str:
        if not smells:
            return "✅ No major code smells detected."
        lines = [f"## Refactoring Analysis — {len(smells)} issue(s) found\n"]
        for s in smells[:8]:
            emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(s.get("severity","LOW"), "⚪")
            lines.append(f"{emoji} **{s['type'].replace('_',' ').title()}**")
            lines.append(f"   {s['suggestion']}\n")
        return "\n".join(lines)


# ── Debugging Agent ────────────────────────────────────────────────────────

class DebuggingAgent:

    def __init__(self, graph_builder, explanation_agent=None):
        self.graph_builder = graph_builder

    def debug(self, repo_id: str, question: str, context: dict = None) -> dict:
        graph = self.graph_builder.get_graph(repo_id)
        path  = self._trace_path(graph, question)
        return {
            "answer":         self._template_debug(question, path),
            "agent":          "debug",
            "context_nodes":  [p["id"] for p in path[:5]],
            "confidence":     0.75,
            "suggestions":    ["Add logging at entry points", "Check input validation", "Verify dependency injection"],
            "execution_path": path,
        }

    def _trace_path(self, graph: dict, question: str) -> list[dict]:
        tokens    = set(question.lower().split())
        nodes     = graph.get("nodes", [])
        edges     = graph.get("edges", [])
        nodes_map = {n["id"]: n for n in nodes}
        adj: dict[str, list] = {}
        for e in edges:
            adj.setdefault(e["source"], []).append(e["target"])

        entries = [n for n in nodes if tokens & set(n["label"].lower().split())][:3]
        if not entries:
            return nodes[:5]

        path, visited, queue = [], set(), [entries[0]["id"]]
        while queue and len(path) < 8:
            curr = queue.pop(0)
            if curr in visited: continue
            visited.add(curr)
            if curr in nodes_map:
                path.append(nodes_map[curr])
            for nb in adj.get(curr, [])[:3]:
                queue.append(nb)
        return path

    def _template_debug(self, question: str, path: list) -> str:
        lines = [f"## Debug Trace: *{question}*\n", "### Execution path:\n"]
        for i, n in enumerate(path[:8]):
            arrow = "↓" if i < len(path) - 1 else "⚑"
            lines.append(f"  {i+1}. `{n.get('label', n['id'])}` ({n.get('type','node')}) {arrow}")
        lines.append("\n### Suggested checks:")
        lines += [
            "- Verify input validation at entry points",
            "- Check exception handling along the traced path",
            "- Look for null/undefined references",
        ]
        return "\n".join(lines)
