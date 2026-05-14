"""
Agent Orchestrator
==================
Wires all agents together.
Primary path : GraphRAGEngine  (Groq + Neo4j/NetworkX + FAISS)
Fallback path: template agents (no LLM required)
"""
from __future__ import annotations
import asyncio
from typing import Any

from agents.ingestion_agent      import RepoIngestionAgent
from agents.graph_builder_agent  import GraphBuilderAgent
from agents.retrieval_agent      import RetrievalAgent
from agents.explanation_agent    import ExplanationAgent
from agents.refactor_debug_agents import (
    ImpactAnalysisAgent, RefactoringAgent, DebuggingAgent
)
from core.graph_rag  import GraphRAGEngine
from core.config     import settings


class AgentOrchestrator:

    def __init__(self):
        self.ingestion     = RepoIngestionAgent()
        self.graph_builder = GraphBuilderAgent()
        self.retrieval     = RetrievalAgent()
        self.explanation   = ExplanationAgent()
        self.impact        = ImpactAnalysisAgent(self.graph_builder)
        self.refactoring   = RefactoringAgent(self.graph_builder)
        self.debugging     = DebuggingAgent(self.graph_builder)

        self.graph_rag = GraphRAGEngine(
            memory_graphs = self.graph_builder._memory_graphs,
            faiss_indices = self.retrieval.indices,
        )

        self._repo_registry: dict[str, dict] = {}
        self._groq_ok = bool(settings.GROQ_API_KEY)
        print(
            f"[Orchestrator] Groq: "
            f"{'enabled ✓' if self._groq_ok else 'NOT SET — template fallback active'}"
        )

    # ── Ingestion ────────────────────────────────────────────────────────

    def ingest_repo(self, repo_url: str, branch: str = "main") -> dict:
        parsed  = self.ingestion.ingest(repo_url, branch)
        repo_id = parsed["repo_id"]

        self.graph_builder.build_graph(parsed)
        self.retrieval.build_index(repo_id, parsed)

        metrics   = self.graph_builder.get_metrics(repo_id)
        repo_info = {
            "repo_id":        repo_id,
            "name":           repo_url.rstrip("/").split("/")[-1].replace(".git", ""),
            "url":            repo_url,
            "language":       parsed.get("language", "unknown"),
            "file_count":     parsed["stats"]["file_count"],
            "function_count": parsed["stats"]["function_count"],
            "class_count":    parsed["stats"].get("class_count", 0),
            "status":         "ready",
            **metrics,
        }
        self._repo_registry[repo_id] = repo_info
        return repo_info

    # ── Query ─────────────────────────────────────────────────────────────

    def query(self, repo_id: str, question: str, agent: str = "explanation") -> dict:
        """
        Route to Graph RAG (Groq) if API key is set,
        otherwise use legacy template agents.
        """
        if self._groq_ok:
            try:
                return self._run_async(
                    self.graph_rag.query(repo_id, question, agent)
                )
            except Exception as e:
                print(f"[Orchestrator] Graph RAG error: {e} — falling back to templates")

        # ── Legacy fallback ──────────────────────────────────────────────
        context = self.retrieval.hybrid_retrieve(repo_id, question)

        if agent == "impact":
            results = context.get("results") or [{}]
            return self.impact.analyze(
                repo_id, results[0].get("id", "unknown"), question
            )
        if agent == "refactor":
            return self.refactoring.analyze(repo_id)
        if agent == "debug":
            return self.debugging.debug(repo_id, question, context)
        return self.explanation.explain(question, context)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _run_async(self, coro) -> Any:
        """Run an async coroutine from sync code safely."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside FastAPI's event loop — run in a thread pool
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=90)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def get_graph(self, repo_id: str) -> dict:
        return self.graph_builder.get_graph(repo_id)

    def get_repo_info(self, repo_id: str) -> dict:
        return self._repo_registry.get(repo_id, {})

    def list_repos(self) -> list:
        return list(self._repo_registry.values())


orchestrator = AgentOrchestrator()
