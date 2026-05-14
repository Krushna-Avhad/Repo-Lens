from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class IngestRequest(BaseModel):
    repo_url: str
    branch: str = "main"

class QueryRequest(BaseModel):
    repo_id: str
    question: str
    agent: str = "explanation"   # explanation | impact | refactor | debug

class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: Dict[str, Any] = {}

class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str

class AgentResponse(BaseModel):
    answer: str
    agent: str
    context_nodes: List[str] = []
    confidence: float = 1.0
    suggestions: List[str] = []

class RepoInfo(BaseModel):
    repo_id: str
    name: str
    url: str
    language: str
    file_count: int
    function_count: int
    complexity_score: float
    coupling_score: float
    maintainability_score: float
    status: str
