# 🔭 Repo Lens

**Codebase Intelligence Engine** — Ask anything about any GitHub repository and get precise, graph-grounded answers powered by Graph RAG.

---

## What it does

Repo Lens ingests any GitHub repository, builds a knowledge graph of its structure, and lets you query it using natural language. Instead of keyword search, it uses a full 8-step Graph RAG pipeline — generating graph traversal queries, combining structural and semantic search, and producing answers grounded in your actual codebase.

```
You: "What breaks if I remove the auth middleware?"

Repo Lens:
  → Classifies intent as impact_analysis
  → Traverses the dependency graph 3 hops deep
  → Finds 12 files that directly or indirectly depend on auth.js
  → Combines with semantic vector search
  → Streams a precise, file-cited answer via Groq
```

---

## How it works

### Ingestion pipeline
When you paste a GitHub URL, Repo Lens:
1. Clones the repo locally (depth=1, no history)
2. Parses every file using Python AST (for `.py`) or regex (for JS, TS, Java, Go, Rust, C, C++, and 20+ more)
3. Extracts files, functions, classes, imports, and call relationships
4. Builds a NetworkX directed graph — nodes are files/functions/classes, edges are `contains`, `calls`, `imports`, `defines`
5. Encodes every node as a 384-dimensional vector using `all-MiniLM-L6-v2` and indexes them in FAISS
6. Calculates complexity, coupling, and maintainability scores

### Graph RAG pipeline (8 steps)
Every query goes through:

| Step | What happens | Model used |
|------|-------------|------------|
| 1. Intent classification | Understand what type of question this is | llama-3.1-8b-instant |
| 2. Cypher generation | Write a graph traversal query for the question | llama-3.3-70b-versatile |
| 3. Graph execution | Run the query on the NetworkX graph, get a subgraph | NetworkX |
| 4. Subgraph expansion | 1-hop BFS to capture neighbouring context | NetworkX |
| 5. Vector search | Semantic similarity search across all nodes | FAISS |
| 6. RRF fusion | Reciprocal Rank Fusion merges graph + vector results | Python |
| 7. Summarisation | Compress context to fit token budget | llama-3.1-8b-instant |
| 8. Answer generation | Stream the final grounded answer | llama-3.3-70b-versatile |

### Four specialised agents

| Agent | Best for |
|-------|----------|
| **Explain** | Understanding how something works — "How does authentication work?" |
| **Impact** | Predicting what breaks — "What happens if I remove this file?" |
| **Refactor** | Finding code smells — detects tight coupling, circular dependencies, god nodes |
| **Debug** | Tracing failures — "Why is login failing?" traces the execution path |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn, Python 3.11 |
| LLM | Groq API — llama-3.3-70b-versatile + llama-3.1-8b-instant |
| Graph | NetworkX (in-memory directed graph) |
| Vector search | FAISS + sentence-transformers (all-MiniLM-L6-v2, runs locally) |
| Code parsing | Python AST + language-specific regex |
| Frontend | React 18 + Vite + Tailwind CSS |
| Graph visualiser | Cytoscape.js |
| Charts | Recharts |
| State management | Zustand |

---

## Project structure

```
repo-lens/
├── backend/
│   ├── agents/
│   │   ├── ingestion_agent.py        # Clone + parse → RepoIngestionAgent
│   │   ├── graph_builder_agent.py    # NetworkX knowledge graph
│   │   ├── retrieval_agent.py        # FAISS vector index + search
│   │   ├── explanation_agent.py      # Template fallback (no Groq key)
│   │   └── refactor_debug_agents.py  # Impact, Refactor, Debug agents
│   ├── api/
│   │   └── routes.py                 # FastAPI endpoints + SSE streaming
│   ├── core/
│   │   ├── config.py                 # All settings, loaded from .env
│   │   ├── groq_client.py            # Groq SDK wrapper (lazy-loaded)
│   │   ├── graph_rag.py              # Full 8-step Graph RAG engine
│   │   └── orchestrator.py           # Wires all agents together
│   ├── models/
│   │   └── schemas.py                # Pydantic request/response models
│   ├── main.py                       # FastAPI app entry point
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── HomePage.jsx          # Landing page + repo input
│   │   │   └── WorkspacePage.jsx     # Split-view workspace
│   │   ├── components/
│   │   │   ├── Sidebar.jsx           # Agent selector + repo list + Code DNA
│   │   │   ├── ChatInterface.jsx     # Chat with live pipeline step UI
│   │   │   ├── GraphVisualizer.jsx   # Interactive Cytoscape knowledge graph
│   │   │   └── MetricsDashboard.jsx  # Health radar, complexity charts
│   │   ├── services/api.js           # Axios API client
│   │   └── store/index.js            # Zustand global state
│   ├── vite.config.js                # Dev server + /api proxy to port 8000
│   └── package.json
└── README.md
```

---

## Setup

### Requirements
- Python 3.11+
- Node.js 20+
- Git
- A free Groq API key from [console.groq.com](https://console.groq.com)

### Step 1 — Configure environment

```bash
cd repo-lens/backend
cp .env.example .env
```

Open `.env` and add your Groq key:

```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FAST_MODEL=llama-3.1-8b-instant
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Step 2 — Backend (Terminal 1)

```bash
cd repo-lens/backend

# Create virtual environment
python -m venv .venv

# Activate — Windows
.venv\Scripts\activate

# Activate — macOS/Linux
source .venv/bin/activate

# Install dependencies (~3-5 min first time)
pip install -r requirements.txt

# Start server
uvicorn main:app --reload --port 8000
```

Verify:
```bash
# Open in browser or run curl
http://localhost:8000/api/health

# Expected:
# {"status":"ok","groq":true,"faiss":true,"repos_ingested":0}
```

### Step 3 — Frontend (Terminal 2)

```bash
cd repo-lens/frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ingest` | Start repo ingestion (async background task) |
| `GET` | `/api/status/{job_id}` | Poll ingestion status |
| `POST` | `/api/query` | Query with an agent — returns full JSON |
| `POST` | `/api/query/stream` | Query with streaming SSE — tokens appear live |
| `GET` | `/api/graph/{repo_id}` | Get full graph (nodes + edges) |
| `GET` | `/api/repos` | List all ingested repos |
| `GET` | `/api/repo/{repo_id}` | Get repo info and metrics |
| `GET` | `/api/health` | Health check |

**Query request body:**
```json
{
  "repo_id":  "130bd43b1c7b",
  "question": "How does authentication work?",
  "agent":    "explanation"
}
```

**Agent values:** `explanation` · `impact` · `refactor` · `debug`

**Query response includes:**
```json
{
  "answer":          "...",
  "agent":           "explanation",
  "cypher_used":     "MATCH (n)-[r*1..2]->...",
  "subgraph_nodes":  80,
  "subgraph_edges":  108,
  "vector_hits":     6,
  "confidence":      0.95,
  "intent":          {"intent": "flow_explanation", ...},
  "suggestions":     ["Explore the dependency chain", ...]
}
```

---

## Supported languages

| Language | File extensions | Parsing method |
|----------|----------------|----------------|
| Python | `.py` `.pyw` `.pyx` | AST (100% accurate) |
| Jupyter | `.ipynb` | Code cell extraction + AST |
| JavaScript | `.js` `.jsx` `.mjs` | Regex |
| TypeScript | `.ts` `.tsx` | Regex |
| Java | `.java` | Regex |
| Kotlin | `.kt` | Regex |
| Go | `.go` | Regex |
| Rust | `.rs` | Regex |
| C | `.c` `.h` | Regex |
| C++ | `.cpp` `.cc` `.hpp` | Regex |
| C# | `.cs` | Regex |
| Ruby | `.rb` | Regex |
| PHP | `.php` | Regex |
| Scala | `.scala` | Regex |
| SQL | `.sql` | Indexed (no parse) |
| R | `.r` `.R` | Indexed (no parse) |
| Shell | `.sh` `.bash` `.ps1` | Indexed (no parse) |
| Web | `.html` `.css` `.scss` | Indexed (no parse) |
| Config | `.json` `.yaml` `.toml` `.xml` | Indexed (no parse) |
| Docs | `.md` `.rst` `.txt` | Indexed (no parse) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ImportError: RepoIngestionAgent` | Make sure you have the latest version of `ingestion_agent.py` |
| `GROQ_API_KEY not set` | Check `backend/.env` — no quotes around the key, no spaces around `=` |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` with venv activated |
| Only README.md parsed | Your repo's file types may not be supported — check the language table above |
| `[WinError 5] Access denied` | Windows `.git` read-only files — the `force_remove` handler fixes this automatically on re-ingest |
| Frontend shows 404 | Make sure backend is running on port 8000 |
| Ingestion times out | Large repos (1000+ files) take 3-5 min — try a smaller repo first |
| `500` error on query | Check the uvicorn terminal for the full traceback and share it |

---

## How Graph RAG differs from plain vector search

| | Plain vector search | Graph RAG (Repo Lens) |
|--|--------------------|-----------------------|
| Finds | Semantically similar text | Structurally connected + semantically similar nodes |
| Understands | What words mean | What code depends on what |
| Answers | "What files mention auth?" | "What breaks if auth.js is removed?" |
| Context | Decontextualised chunks | Subgraph with full relationship context |
| Hallucination risk | High (no structural grounding) | Low (grounded in actual graph) |

---

## License

MIT
