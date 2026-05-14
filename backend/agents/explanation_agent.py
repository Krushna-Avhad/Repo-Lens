"""
Explanation Agent — Groq-powered, Graph RAG backed.
All queries now go through the GraphRAGEngine pipeline.
"""
from __future__ import annotations
from typing import AsyncGenerator, Any
from core.groq_client import stream_chat, chat
from core.config import settings


SYSTEM_PROMPT = """You are Repo Lens — an elite codebase intelligence engine.
You analyse codebases using a Knowledge Graph (Neo4j) and semantic vector search.
Always reference specific file paths, function names, and relationships from the context.
Use markdown: headers, bullet lists, code blocks. Be precise and developer-focused."""


class ExplanationAgent:
    """Thin wrapper kept for backward-compatibility. Real work is in GraphRAGEngine."""

    def explain(self, question: str, context: dict) -> dict:
        """Synchronous non-streaming fallback (used by legacy orchestrator path)."""
        results  = context.get("results", [])
        files    = [r for r in results if r.get("type") == "file"]
        funcs    = [r for r in results if r.get("type") == "function"]
        classes  = [r for r in results if r.get("type") == "class"]

        lines = [f"**Analysis for:** *{question}*\n"]
        if files:
            lines.append("**Relevant files:**")
            lines += [f"  - `{f.get('path', f.get('id',''))}`" for f in files[:5]]
        if funcs:
            lines.append("\n**Key functions:**")
            lines += [f"  - `{fn.get('name', fn.get('id',''))}`" for fn in funcs[:5]]
        if classes:
            lines.append("\n**Classes involved:**")
            lines += [f"  - `{c.get('name', c.get('id',''))}`" for c in classes[:5]]
        lines.append("\n> Tip: make sure `GROQ_API_KEY` is set for full Graph RAG answers.")
        return {
            "answer": "\n".join(lines),
            "agent":  "explanation",
            "context_nodes": [r.get("id","") for r in results[:5]],
            "confidence": 0.5,
            "suggestions": [
                "Explore the authentication flow",
                "Check database relationships",
                "Analyse API endpoints",
            ],
        }
