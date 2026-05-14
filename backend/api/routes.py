from __future__ import annotations
import asyncio
import hashlib
import json
from typing import Dict

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from models.schemas import IngestRequest, QueryRequest
from core.orchestrator import orchestrator
from core.config import settings

router = APIRouter()
_jobs: Dict[str, dict] = {}


# ── Ingestion ─────────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_repo(req: IngestRequest, background_tasks: BackgroundTasks):
    job_id = hashlib.md5(req.repo_url.encode()).hexdigest()[:12]
    _jobs[job_id] = {"status": "ingesting", "repo_id": job_id}

    def run():
        try:
            info = orchestrator.ingest_repo(req.repo_url, req.branch)
            _jobs[job_id] = {"status": "ready", **info}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "error": str(e)}

    background_tasks.add_task(run)
    return {"job_id": job_id, "status": "ingesting"}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ── Query (standard JSON) ─────────────────────────────────────────────────

@router.post("/query")
async def query(req: QueryRequest):
    try:
        result = orchestrator.query(req.repo_id, req.question, req.agent)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Query (streaming SSE) ─────────────────────────────────────────────────

@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    if not settings.GROQ_API_KEY:
        raise HTTPException(400, "GROQ_API_KEY not configured")

    async def event_generator():
        steps = [
            ("intent",    "🎯 Classifying intent..."),
            ("cypher",    "🔍 Generating Cypher query..."),
            ("execute",   "⚡ Executing on knowledge graph..."),
            ("expand",    "🕸️  Expanding subgraph..."),
            ("vector",    "🔎 Running vector search..."),
            ("fuse",      "🔗 Fusing results (RRF)..."),
            ("summarise", "📝 Summarising context..."),
            ("answer",    "🧠 Generating answer with Groq..."),
        ]
        for step_id, msg in steps:
            yield f"data: {json.dumps({'type':'step','step':step_id,'message':msg})}\n\n"
            await asyncio.sleep(0.04)

        try:
            result = await orchestrator.graph_rag.query(
                req.repo_id, req.question, req.agent
            )
            answer = result.get("answer", "")
            chunk_size = 8
            for i in range(0, len(answer), chunk_size):
                yield f"data: {json.dumps({'type':'token','content':answer[i:i+chunk_size]})}\n\n"
                await asyncio.sleep(0.01)

            meta = {k: v for k, v in result.items() if k != "answer"}
            yield f"data: {json.dumps({'type':'meta',**meta})}\n\n"
            yield f"data: {json.dumps({'type':'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Graph ─────────────────────────────────────────────────────────────────

@router.get("/graph/{repo_id}")
async def get_graph(repo_id: str):
    graph = orchestrator.get_graph(repo_id)
    if not graph.get("nodes"):
        raise HTTPException(404, "Graph not found — ingest a repo first")
    return graph


# ── Repos ─────────────────────────────────────────────────────────────────

@router.get("/repos")
async def list_repos():
    return orchestrator.list_repos()


@router.get("/repo/{repo_id}")
async def get_repo(repo_id: str):
    info = orchestrator.get_repo_info(repo_id)
    if not info:
        raise HTTPException(404, "Repo not found")
    return info


# ── Health ────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status":         "ok",
        "groq":           bool(settings.GROQ_API_KEY),
        "neo4j":          orchestrator.graph_builder.driver is not None,
        "faiss":          orchestrator.retrieval._ok,
        "repos_ingested": len(orchestrator.list_repos()),
    }
