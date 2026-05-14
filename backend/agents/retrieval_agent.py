"""
Retrieval Agent
===============
- Builds a FAISS vector index (sentence-transformers, no API key required)
- Exposes hybrid_retrieve for backward-compat with legacy agents
- The Graph RAG engine calls _vector_search directly on the indices dict
"""
from __future__ import annotations
from typing import Any
from core.config import settings


class RetrievalAgent:
    def __init__(self):
        self.indices: dict[str, Any] = {}
        self._ok = self._check_deps()

    def _check_deps(self) -> bool:
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
            return True
        except ImportError:
            print("[RetrievalAgent] FAISS/sentence-transformers not installed — keyword fallback active")
            return False

    def build_index(self, repo_id: str, parsed_data: dict):
        texts, meta = self._build_corpus(parsed_data)
        if not texts:
            self.indices[repo_id] = {"texts": texts, "meta": meta}
            return
        if self._ok:
            self._build_faiss(repo_id, texts, meta)
        else:
            self.indices[repo_id] = {"texts": texts, "meta": meta}

    def _build_corpus(self, parsed: dict) -> tuple[list[str], list[dict]]:
        texts, meta = [], []
        for f in parsed.get("files", []):
            path = f.get("path", "")
            fns  = " ".join(fn["name"] for fn in f.get("functions", []))
            cls  = " ".join(c["name"]  for c  in f.get("classes",   []))
            txt  = f"File: {path} Language: {f.get('language','')} LOC: {f.get('loc','')} Functions: {fns} Classes: {cls}"
            texts.append(txt)
            meta.append({"type": "file", "id": f["id"], "path": path})
        for fn in parsed.get("functions", []):
            calls = ", ".join(fn.get("calls", []))
            txt   = f"Function: {fn['name']} in file {fn['file']} complexity: {fn.get('complexity',1)} calls: {calls}"
            texts.append(txt)
            meta.append({"type": "function", "id": fn["id"], "name": fn["name"], "path": fn["file"]})
        for cls in parsed.get("classes", []):
            methods = ", ".join(cls.get("methods", []))
            txt = f"Class: {cls['name']} in {cls['file']} methods: {methods}"
            texts.append(txt)
            meta.append({"type": "class", "id": cls["id"], "name": cls["name"], "path": cls["file"]})
        return texts, meta

    def _build_faiss(self, repo_id: str, texts: list[str], meta: list[dict]):
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.EMBEDDING_MODEL)
        vecs  = model.encode(texts, show_progress_bar=False, batch_size=64).astype("float32")
        faiss.normalize_L2(vecs)
        index = faiss.IndexFlatIP(vecs.shape[1])
        index.add(vecs)
        self.indices[repo_id] = {"index": index, "model": model, "texts": texts, "meta": meta}
        print(f"[RetrievalAgent] FAISS index: {len(texts)} vectors for {repo_id}")

    def search(self, repo_id: str, query: str, top_k: int = 8) -> list[dict]:
        store = self.indices.get(repo_id)
        if not store:
            return []
        if self._ok and "index" in store:
            return self._faiss_search(store, query, top_k)
        return self._keyword_search(store, query, top_k)

    def _faiss_search(self, store: dict, query: str, top_k: int) -> list[dict]:
        import faiss, numpy as np
        q_vec = store["model"].encode([query]).astype("float32")
        faiss.normalize_L2(q_vec)
        D, I = store["index"].search(q_vec, min(top_k, len(store["texts"])))
        return [
            {**store["meta"][i], "text": store["texts"][i], "score": float(D[0][k])}
            for k, i in enumerate(I[0]) if i >= 0
        ]

    def _keyword_search(self, store: dict, query: str, top_k: int) -> list[dict]:
        tokens = set(query.lower().split())
        scored = sorted(
            [(len(tokens & set(t.lower().split())), i) for i, t in enumerate(store["texts"])],
            reverse=True,
        )
        return [
            {**store["meta"][i], "text": store["texts"][i], "score": s / max(len(tokens), 1)}
            for s, i in scored[:top_k] if s > 0
        ]

    def hybrid_retrieve(self, repo_id: str, query: str) -> dict:
        return {"results": self.search(repo_id, query), "query": query}
