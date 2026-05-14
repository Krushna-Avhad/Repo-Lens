"""
Graph RAG Engine — True Graph-Retrieval-Augmented Generation
============================================================

Pipeline (per query):
  1. Intent classification  — understand what the user is really asking
  2. Cypher generation      — LLM writes a Neo4j Cypher query for the question
  3. Cypher execution       — run the query on Neo4j, get a subgraph
  4. Subgraph expansion     — BFS-expand the subgraph 1-2 hops for richer context
  5. Vector recall          — FAISS semantic search for additional file context
  6. RRF fusion             — Reciprocal Rank Fusion to merge both result streams
  7. Subgraph summarisation — compact the subgraph so it fits the LLM context window
  8. Final answer           — Groq LLM generates the answer with all context injected

Falls back gracefully at every step:
  - No Neo4j → keyword graph search on in-memory NetworkX graph
  - No FAISS embeddings → keyword search fallback
  - Bad Cypher → retry with error message fed back to LLM (up to 2 retries)
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.config import settings
from core.groq_client import chat, fast_chat, extract_json

# ── Neo4j schema that the LLM must know about ──────────────────────────────
NEO4J_SCHEMA = """
Node labels and their key properties:
  (:Repo   {name, url})
  (:File   {id, path, extension, lines, size, repo, preview})
  (:Function {id, name, line, repo, file, docstring})
  (:Class  {id, name, line, repo, file, methods[]})

Relationship types:
  (:Repo)-[:CONTAINS]->(:File)
  (:File)-[:DEFINES]->(:Function)
  (:File)-[:DEFINES]->(:Class)
  (:File)-[:IMPORTS]->(:File)
  (:Function)-[:CALLS]->(:Function)      // may not always exist
  (:Class)-[:INHERITS]->(:Class)         // may not always exist

Important: always filter by repo using WHERE n.repo = $repo
"""

# ── System prompt for Cypher generation ────────────────────────────────────
CYPHER_GEN_PROMPT = f"""You are a Neo4j Cypher expert for a code knowledge graph.

Graph schema:
{NEO4J_SCHEMA}

Rules:
- ALWAYS include WHERE ... AND n.repo = $repo (or equivalent) to scope to one repo.
- Use OPTIONAL MATCH for relationships that may not exist.
- LIMIT results: 30 nodes max, 60 relationships max.
- Return meaningful node properties: id, name, path, file, type (use labels(n)[0]).
- For relationship queries, return source/target ids and relationship type.
- Only use Cypher — no explanations, no markdown fences, just raw Cypher.
- If the question cannot be answered with a Cypher query, return:  SKIP
"""

# ── System prompt for final answer generation ───────────────────────────────
ANSWER_PROMPT = """You are Repo Lens — an elite codebase intelligence engine powered by Graph RAG.
You answer developer questions about codebases using:
  1. A Neo4j knowledge graph subgraph (structure, relationships)
  2. Semantic search results (file contents, docstrings)

Rules:
- Reference specific file paths and function names from the context.
- Use markdown: headers, code blocks, bullet lists.
- Be precise — if you cannot find evidence in the context, say so.
- Cite node ids or paths when making specific claims.
- For impact/debug questions, reason step-by-step through the dependency chain.
"""


class GraphRAGEngine:
    """
    Full Graph RAG pipeline.  One instance is shared across the app.
    """

    def __init__(self, memory_graphs: dict, faiss_indices: dict):
        self._driver = None                 # always None — Neo4j removed
        self._mem = memory_graphs
        self._faiss = faiss_indices

    # ────────────────────────────────────────────────────────────────────
    # Public entry-point
    # ────────────────────────────────────────────────────────────────────

    async def query(
        self,
        repo_id: str,
        question: str,
        mode: str = "explanation",           # explanation | impact | refactor | debug
    ) -> dict[str, Any]:
        """
        Execute the full Graph RAG pipeline and return a structured result.
        """
        # 1. Classify intent to tailor Cypher and answer style
        intent = await self._classify_intent(question, mode)

        # 2. Generate Cypher
        cypher, cypher_params = await self._generate_cypher(question, repo_id, intent)

        # 3. Execute Cypher → subgraph
        subgraph, cypher_used = await self._execute_cypher_with_retry(
            cypher, cypher_params, repo_id, question, intent
        )

        # 4. Expand subgraph 1-hop for richer neighbourhood
        expanded = await self._expand_subgraph(subgraph, repo_id)

        # 5. Vector recall
        vector_hits = self._vector_search(repo_id, question, top_k=6)

        # 6. RRF fusion
        fused = self._rrf_fuse(expanded, vector_hits)

        # 7. Summarise subgraph to fit context window
        subgraph_summary = await self._summarise_subgraph(fused, question)

        # 8. Generate final answer
        answer = await self._generate_answer(
            question, repo_id, subgraph_summary, fused, intent, mode
        )

        return {
            "answer": answer,
            "agent": mode,
            "cypher_used": cypher_used,
            "subgraph_nodes": len(expanded.get("nodes", [])),
            "subgraph_edges": len(expanded.get("edges", [])),
            "vector_hits": len(vector_hits),
            "intent": intent,
            "fused_context": fused[:5],   # first 5 items for frontend debug
            "confidence": self._confidence(fused),
        }

    # ────────────────────────────────────────────────────────────────────
    # Step 1 — Intent classification
    # ────────────────────────────────────────────────────────────────────

    async def _classify_intent(self, question: str, mode: str) -> dict:
        prompt = f"""Classify this developer question about a codebase.
Question: {question}
Agent mode: {mode}

Return JSON only:
{{
  "intent": "one of: flow_explanation | dependency_analysis | impact_analysis | bug_trace | architecture_overview | refactor_suggestion | api_exploration",
  "key_entities": ["list of specific functions/classes/files mentioned or implied"],
  "traversal_depth": 1,   // 1=shallow, 2=medium, 3=deep
  "needs_call_graph": true/false,
  "needs_import_graph": true/false
}}"""
        try:
            raw = await fast_chat(
                [{"role": "user", "content": prompt}], max_tokens=256
            )
            return extract_json(raw)
        except Exception:
            return {
                "intent": "flow_explanation",
                "key_entities": [],
                "traversal_depth": 2,
                "needs_call_graph": True,
                "needs_import_graph": True,
            }

    # ────────────────────────────────────────────────────────────────────
    # Step 2 — Cypher generation
    # ────────────────────────────────────────────────────────────────────

    async def _generate_cypher(
        self, question: str, repo_id: str, intent: dict
    ) -> tuple[str, dict]:
        entities = intent.get("key_entities", [])
        depth    = intent.get("traversal_depth", 2)
        intent_t = intent.get("intent", "flow_explanation")

        # Build a targeted hint so the LLM generates better Cypher
        hint = self._cypher_hint(intent_t, entities, depth)

        messages = [
            {"role": "system", "content": CYPHER_GEN_PROMPT},
            {"role": "user",   "content": (
                f"Question: {question}\n"
                f"Repo parameter: $repo (value will be bound at runtime)\n"
                f"Hint: {hint}\n\n"
                f"Write a single Cypher query. Return ONLY the Cypher, nothing else."
            )},
        ]
        raw = await chat(messages, max_tokens=512, temperature=0.1)
        cypher = raw.strip().strip("`").strip()

        # Strip accidental markdown fences
        if cypher.lower().startswith("cypher"):
            cypher = cypher[6:].strip()
        cypher = re.sub(r"^```[a-z]*\n?", "", cypher, flags=re.I)
        cypher = re.sub(r"\n?```$", "", cypher)

        return cypher, {"repo": repo_id}

    def _cypher_hint(self, intent: str, entities: list[str], depth: int) -> str:
        entity_clause = ""
        if entities:
            names = " OR ".join(f'n.name CONTAINS "{e}"' for e in entities[:3])
            entity_clause = f"Filter by entity names: {names}"

        hints = {
            "flow_explanation": (
                f"Find all nodes involved in the relevant flow. "
                f"MATCH (n)-[r*1..{depth}]->(m) WHERE n.repo=$repo. "
                f"{entity_clause}"
            ),
            "dependency_analysis": (
                "Find IMPORTS and CALLS relationships. "
                "MATCH (f:File)-[:IMPORTS]->(dep:File) WHERE f.repo=$repo. "
                f"{entity_clause}"
            ),
            "impact_analysis": (
                "Find all nodes that depend on the target (reverse traversal). "
                "MATCH (dependent)-[r*1..3]->(target) WHERE target.repo=$repo. "
                f"{entity_clause}"
            ),
            "bug_trace": (
                "Trace the call chain. "
                "MATCH path=(entry)-[:CALLS*1..4]->(suspect) WHERE entry.repo=$repo. "
                f"{entity_clause}"
            ),
            "architecture_overview": (
                "Return high-level File and Class nodes with their IMPORTS. "
                "MATCH (f:File)-[:IMPORTS]->(dep) WHERE f.repo=$repo RETURN f, dep LIMIT 50"
            ),
            "refactor_suggestion": (
                "Find Files with many outgoing IMPORTS (high coupling). "
                "MATCH (f:File)-[:IMPORTS]->(dep) WHERE f.repo=$repo "
                "WITH f, count(dep) AS deg ORDER BY deg DESC RETURN f, deg LIMIT 20"
            ),
            "api_exploration": (
                "Find Function nodes whose names suggest they are endpoints. "
                "MATCH (fn:Function) WHERE fn.repo=$repo AND "
                "(fn.name CONTAINS 'route' OR fn.name CONTAINS 'endpoint' OR fn.name CONTAINS 'handler') "
                f"{entity_clause}"
            ),
        }
        return hints.get(intent, f"Find relevant nodes. {entity_clause}")

    # ────────────────────────────────────────────────────────────────────
    # Step 3 — Execute Cypher with retry on error
    # ────────────────────────────────────────────────────────────────────

    async def _execute_cypher_with_retry(
        self,
        cypher: str,
        params: dict,
        repo_id: str,
        question: str,
        intent: dict,
        max_retries: int = 2,
    ) -> tuple[dict, str]:
        if cypher == "SKIP" or not cypher:
            return await self._fallback_graph_search(repo_id, question, intent), "FALLBACK"

        for attempt in range(max_retries + 1):
            try:
                if self._driver:
                    result = await self._run_neo4j_cypher(cypher, params)
                else:
                    result = self._run_memory_cypher(cypher, params, repo_id)
                return result, cypher
            except Exception as err:
                if attempt == max_retries:
                    # Give up — use keyword fallback
                    return await self._fallback_graph_search(repo_id, question, intent), "FALLBACK"
                # Ask LLM to fix the bad Cypher
                cypher = await self._fix_cypher(cypher, str(err), question)

        return {}, "FAILED"

    async def _run_neo4j_cypher(self, cypher: str, params: dict) -> dict:
        """Run Cypher on real Neo4j and normalise the result into nodes/edges."""
        async with self._driver.session() as session:
            result = await session.run(cypher, params)
            records = await result.data()

        nodes, edges = [], []
        seen_nodes: set[str] = set()
        seen_edges: set[str] = set()

        for rec in records:
            for val in rec.values():
                if hasattr(val, "labels"):           # Neo4j Node
                    nid = val.get("id") or val.id
                    if str(nid) not in seen_nodes:
                        seen_nodes.add(str(nid))
                        nodes.append({
                            "id":    str(nid),
                            "label": val.get("name") or val.get("path") or str(nid),
                            "type":  list(val.labels)[0].lower() if val.labels else "node",
                            "properties": dict(val),
                        })
                elif hasattr(val, "type"):            # Neo4j Relationship
                    eid = f"{val.start_node.id}-{val.type}-{val.end_node.id}"
                    if eid not in seen_edges:
                        seen_edges.add(eid)
                        edges.append({
                            "source": str(val.start_node.id),
                            "target": str(val.end_node.id),
                            "relationship": val.type.lower(),
                        })
                elif isinstance(val, dict):           # Plain dict rows
                    nid = val.get("id") or val.get("name")
                    if nid and str(nid) not in seen_nodes:
                        seen_nodes.add(str(nid))
                        nodes.append({
                            "id":    str(nid),
                            "label": val.get("name") or val.get("path") or str(nid),
                            "type":  val.get("type", "node"),
                            "properties": val,
                        })

        return {"nodes": nodes, "edges": edges}

    def _run_memory_cypher(self, cypher: str, params: dict, repo_id: str) -> dict:
        """
        Very lightweight Cypher-to-NetworkX interpreter.
        Handles the most common patterns generated by the LLM.
        Falls back to full-graph dump if parsing fails.
        """
        import networkx as nx

        G: nx.DiGraph = self._mem.get(repo_id)
        if not G:
            return {"nodes": [], "edges": []}

        cypher_lower = cypher.lower()
        nodes_out, edges_out = [], []
        seen: set[str] = set()

        # Pattern: relationship traversal
        rel_match = re.search(r"\[:(\w+)\]", cypher, re.I)
        rel_filter = rel_match.group(1).lower() if rel_match else None

        # Pattern: name CONTAINS "xyz"
        contains = re.findall(r'n\.name contains "([^"]+)"', cypher, re.I)
        contains += re.findall(r"n\.name contains '([^']+)'", cypher, re.I)

        # Pattern: label filter   (n:File)
        label_m = re.search(r"\(n:(\w+)\)", cypher, re.I)
        label_filter = label_m.group(1).lower() if label_m else None

        limit_m = re.search(r"limit\s+(\d+)", cypher, re.I)
        limit = int(limit_m.group(1)) if limit_m else 40

        for n in G.nodes:
            data = G.nodes[n]
            ntype = data.get("type", "node")
            label = data.get("label", data.get("name", n))

            if label_filter and ntype != label_filter:
                continue
            if contains and not any(c.lower() in label.lower() for c in contains):
                continue

            if n not in seen:
                seen.add(n)
                nodes_out.append({
                    "id":    n,
                    "label": label,
                    "type":  ntype,
                    "properties": {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))},
                })
            if len(nodes_out) >= limit:
                break

        # Include edges between returned nodes
        node_ids = {nd["id"] for nd in nodes_out}
        for u, v, edata in G.edges(data=True):
            rel = edata.get("relationship", "relates")
            if rel_filter and rel != rel_filter:
                continue
            if u in node_ids and v in node_ids:
                edges_out.append({"source": u, "target": v, "relationship": rel})

        return {"nodes": nodes_out, "edges": edges_out}

    async def _fix_cypher(self, bad_cypher: str, error: str, question: str) -> str:
        """Ask the LLM to repair a broken Cypher query."""
        messages = [
            {"role": "system", "content": CYPHER_GEN_PROMPT},
            {"role": "user",   "content": (
                f"The following Cypher query produced an error.\n\n"
                f"Original question: {question}\n"
                f"Bad Cypher:\n{bad_cypher}\n"
                f"Error: {error}\n\n"
                f"Fix the Cypher. Return ONLY the corrected query."
            )},
        ]
        raw = await chat(messages, max_tokens=400, temperature=0.05)
        return raw.strip().strip("`")

    # ────────────────────────────────────────────────────────────────────
    # Fallback: keyword graph search (no Neo4j / bad Cypher)
    # ────────────────────────────────────────────────────────────────────

    async def _fallback_graph_search(
        self, repo_id: str, question: str, intent: dict
    ) -> dict:
        if self._driver:
            return await self._neo4j_keyword_search(repo_id, question)
        return self._memory_keyword_search(repo_id, question)

    async def _neo4j_keyword_search(self, repo_id: str, question: str) -> dict:
        words = [w for w in question.lower().split() if len(w) > 3][:4]
        nodes, edges = [], []
        seen: set[str] = set()
        async with self._driver.session() as session:
            for word in words:
                r = await session.run(
                    "MATCH (n) WHERE n.repo=$repo AND ("
                    "toLower(coalesce(n.name,'')) CONTAINS $w OR "
                    "toLower(coalesce(n.path,'')) CONTAINS $w) "
                    "RETURN n LIMIT 10",
                    {"repo": repo_id, "w": word},
                )
                for rec in await r.data():
                    nd = rec["n"]
                    nid = str(nd.get("id") or nd.id)
                    if nid not in seen:
                        seen.add(nid)
                        nodes.append({"id": nid, "label": nd.get("name",""), "type": "node", "properties": dict(nd)})
        return {"nodes": nodes, "edges": edges}

    def _memory_keyword_search(self, repo_id: str, question: str) -> dict:
        import networkx as nx
        G: nx.DiGraph = self._mem.get(repo_id)
        if not G:
            return {"nodes": [], "edges": []}
        tokens = set(question.lower().split())
        matched = []
        for n in G.nodes:
            label = G.nodes[n].get("label", G.nodes[n].get("name", n))
            if tokens & set(label.lower().split()):
                matched.append(n)
        nodes_out = [
            {"id": n, "label": G.nodes[n].get("label", n), "type": G.nodes[n].get("type","node"),
             "properties": {k: v for k, v in G.nodes[n].items() if isinstance(v,(str,int,float,bool))}}
            for n in matched[:30]
        ]
        node_ids = {nd["id"] for nd in nodes_out}
        edges_out = [
            {"source": u, "target": v, "relationship": G[u][v].get("relationship","relates")}
            for u, v in G.edges if u in node_ids and v in node_ids
        ]
        return {"nodes": nodes_out, "edges": edges_out}

    # ────────────────────────────────────────────────────────────────────
    # Step 4 — Subgraph expansion (1-hop BFS)
    # ────────────────────────────────────────────────────────────────────

    async def _expand_subgraph(self, subgraph: dict, repo_id: str) -> dict:
        """
        Take the seed nodes from the Cypher result and expand by 1 hop
        to capture neighbouring context that the query might have missed.
        """
        seed_ids = {n["id"] for n in subgraph.get("nodes", [])}
        if not seed_ids:
            return subgraph

        if self._driver:
            return await self._neo4j_expand(subgraph, seed_ids, repo_id)
        return self._memory_expand(subgraph, seed_ids, repo_id)

    async def _neo4j_expand(self, subgraph: dict, seed_ids: set, repo_id: str) -> dict:
        nodes = list(subgraph.get("nodes", []))
        edges = list(subgraph.get("edges", []))
        seen_nodes = {n["id"] for n in nodes}
        seen_edges = {(e["source"], e["target"]) for e in edges}

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (seed)-[r]->(nb) WHERE seed.id IN $ids AND nb.repo=$repo "
                "RETURN seed.id as sid, nb, type(r) as rel LIMIT 60",
                {"ids": list(seed_ids), "repo": repo_id},
            )
            for rec in await result.data():
                nb = rec.get("nb", {})
                nid = str(nb.get("id") or "")
                if nid and nid not in seen_nodes:
                    seen_nodes.add(nid)
                    nodes.append({"id": nid, "label": nb.get("name",""), "type": "node", "properties": dict(nb)})
                key = (str(rec["sid"]), nid)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": str(rec["sid"]), "target": nid, "relationship": rec["rel"].lower()})

        return {"nodes": nodes, "edges": edges}

    def _memory_expand(self, subgraph: dict, seed_ids: set, repo_id: str) -> dict:
        import networkx as nx
        G: nx.DiGraph = self._mem.get(repo_id)
        if not G:
            return subgraph

        nodes = list(subgraph.get("nodes", []))
        edges = list(subgraph.get("edges", []))
        seen_n = {n["id"] for n in nodes}
        seen_e = {(e["source"], e["target"]) for e in edges}

        for seed in list(seed_ids):
            if seed not in G:
                continue
            for nb in list(G.successors(seed)) + list(G.predecessors(seed)):
                if nb not in seen_n:
                    seen_n.add(nb)
                    nodes.append({"id": nb, "label": G.nodes[nb].get("label",nb), "type": G.nodes[nb].get("type","node"), "properties": {}})
                key = (seed, nb)
                if key not in seen_e:
                    seen_e.add(key)
                    rel = G[seed][nb].get("relationship","relates") if G.has_edge(seed,nb) else G[nb][seed].get("relationship","relates")
                    edges.append({"source": seed, "target": nb, "relationship": rel})

        return {"nodes": nodes[:80], "edges": edges[:150]}

    # ────────────────────────────────────────────────────────────────────
    # Step 5 — Vector recall (FAISS)
    # ────────────────────────────────────────────────────────────────────

    def _vector_search(self, repo_id: str, question: str, top_k: int = 6) -> list[dict]:
        store = self._faiss.get(repo_id)
        if not store:
            return []

        try:
            import faiss, numpy as np
            model  = store["model"]
            index  = store["index"]
            texts  = store["texts"]
            metas  = store["meta"]

            q_vec = model.encode([question]).astype("float32")
            faiss.normalize_L2(q_vec)
            D, I = index.search(q_vec, min(top_k, len(texts)))
            return [
                {**metas[i], "text": texts[i], "score": float(D[0][k]), "source": "vector"}
                for k, i in enumerate(I[0]) if i >= 0
            ]
        except Exception:
            # Keyword fallback
            store_texts = store.get("texts", [])
            tokens = set(question.lower().split())
            scored = sorted(
                [(len(tokens & set(t.lower().split())), i) for i, t in enumerate(store_texts)],
                reverse=True,
            )
            metas = store.get("meta", [])
            return [
                {**metas[i], "text": store_texts[i], "score": s/max(len(tokens),1), "source": "keyword"}
                for s, i in scored[:top_k] if s > 0
            ]

    # ────────────────────────────────────────────────────────────────────
    # Step 6 — RRF fusion
    # ────────────────────────────────────────────────────────────────────

    def _rrf_fuse(self, subgraph: dict, vector_hits: list[dict], k: int = 60) -> list[dict]:
        """
        Reciprocal Rank Fusion of graph nodes and vector results.
        Each result gets score = 1/(k + rank).  Final list is sorted by fused score.
        """
        scores: dict[str, float] = {}
        items:  dict[str, dict]  = {}

        # Graph nodes (ranked by how many edges they have — more connected = more relevant)
        edge_count: dict[str, int] = {}
        for e in subgraph.get("edges", []):
            edge_count[e["source"]] = edge_count.get(e["source"], 0) + 1
            edge_count[e["target"]] = edge_count.get(e["target"], 0) + 1

        graph_nodes = sorted(
            subgraph.get("nodes", []),
            key=lambda n: edge_count.get(n["id"], 0),
            reverse=True,
        )

        for rank, node in enumerate(graph_nodes):
            nid = f"graph:{node['id']}"
            scores[nid] = scores.get(nid, 0) + 1 / (k + rank + 1)
            items[nid]  = {**node, "source": "graph"}

        # Vector hits
        for rank, hit in enumerate(vector_hits):
            hid = f"vec:{hit.get('id', hit.get('path', rank))}"
            scores[hid] = scores.get(hid, 0) + 1 / (k + rank + 1)
            items[hid]  = {**hit, "source": "vector"}

        fused = sorted(items.values(), key=lambda x: scores.get(
            f"graph:{x.get('id','')}" if x.get("source") == "graph" else f"vec:{x.get('id', x.get('path',''))}",
            0,
        ), reverse=True)

        return fused[:25]

    # ────────────────────────────────────────────────────────────────────
    # Step 7 — Subgraph summarisation
    # ────────────────────────────────────────────────────────────────────

    async def _summarise_subgraph(self, fused: list[dict], question: str) -> str:
        """
        Compact the fused context into a structured text summary that fits
        inside the LLM context window without blowing the token budget.
        """
        if not fused:
            return "No relevant graph context found."

        # Build a compact text representation
        lines = []
        for item in fused[:20]:
            src = item.get("source", "?")
            if src == "graph":
                ntype = item.get("type", "node")
                label = item.get("label", item.get("id", "?"))
                props = item.get("properties", {})
                extra = ""
                if props.get("file"):
                    extra = f" | file: {props['file']}"
                if props.get("docstring"):
                    extra += f" | doc: {props['docstring'][:80]}"
                lines.append(f"[{ntype.upper()}] {label}{extra}")
            else:
                path  = item.get("path", "?")
                text  = item.get("text", "")[:150]
                lines.append(f"[FILE] {path}: {text}")

        raw_summary = "\n".join(lines)

        # If the summary is large, ask the fast model to compress it further
        if len(raw_summary) > 3000:
            compressed = await fast_chat(
                [{"role": "user", "content": (
                    f"Summarise this codebase context for the question: '{question}'\n\n"
                    f"{raw_summary}\n\n"
                    "Keep all file paths and function names. Remove duplicates. Max 1500 chars."
                )}],
                max_tokens=512,
            )
            return compressed

        return raw_summary

    # ────────────────────────────────────────────────────────────────────
    # Step 8 — Final answer generation
    # ────────────────────────────────────────────────────────────────────

    async def _generate_answer(
        self,
        question: str,
        repo_id: str,
        subgraph_summary: str,
        fused: list[dict],
        intent: dict,
        mode: str,
    ) -> str:
        # Build edge summary for structural questions
        edge_lines = []
        graph_items = [f for f in fused if f.get("source") == "graph"]
        # We stored edges on the subgraph but not on fused items — reconstruct from properties
        # Just note: edge context is embedded in the subgraph_summary already

        mode_instruction = {
            "explanation": "Explain clearly how the relevant components work together.",
            "impact":      "List every component that would break or change, with reasoning. Be exhaustive.",
            "refactor":    "Identify specific code smells with file/function names. Suggest concrete refactors.",
            "debug":       "Trace the execution path step by step. Identify where the failure likely occurs.",
        }.get(mode, "Answer the question based on the codebase context.")

        messages = [
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user",   "content": (
                f"Repository: {repo_id}\n"
                f"Question: {question}\n"
                f"Task: {mode_instruction}\n\n"
                f"## Knowledge Graph + Vector Context\n"
                f"{subgraph_summary}\n\n"
                f"## Detected Intent\n"
                f"- Type: {intent.get('intent','unknown')}\n"
                f"- Key entities: {', '.join(intent.get('key_entities', [])) or 'general query'}\n"
                f"- Traversal depth used: {intent.get('traversal_depth', 2)}\n\n"
                f"Answer the question. Use markdown formatting."
            )},
        ]

        return await chat(messages, max_tokens=2048, temperature=0.3)

    # ────────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────────

    def _confidence(self, fused: list[dict]) -> float:
        if not fused:
            return 0.3
        graph_hits = sum(1 for f in fused if f.get("source") == "graph")
        vec_hits   = sum(1 for f in fused if f.get("source") == "vector")
        base = min((graph_hits * 0.05) + (vec_hits * 0.08), 0.95)
        return round(max(base, 0.4), 2)
