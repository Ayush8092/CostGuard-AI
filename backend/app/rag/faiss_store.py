"""
FAISS embedding + retrieval (Part 5) - the ACTUAL RAG component.

Embeds each curated corpus chunk with a local sentence-transformers
model (free, runs entirely on CPU, no API calls), stores vectors in a
FAISS index, and retrieves top-k relevant chunks per Copilot query or
Advisor recommendation. Retrieved chunks are passed as cited context to
the LLM - the LLM is grounded in these chunks and explicitly may not
invent facts beyond them.

This module stays embedded inside the Copilot/Advisor only, per spec:
no standalone "ask anything about AWS docs" tab is built anywhere in
this project.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.rag.knowledge_corpus import KNOWLEDGE_CHUNKS, KnowledgeChunk

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"  # free, local, 384-dim, ~80MB


@dataclass
class RetrievedChunk:
    chunk: KnowledgeChunk
    similarity_score: float


class FaissKnowledgeBase:
    """
    NOTE ON FIRST RUN: SentenceTransformer(model_name) downloads the model
    (~80MB for all-MiniLM-L6-v2) from Hugging Face on first use and caches
    it locally afterward. This requires outbound internet access the
    first time the container runs. The provided Dockerfile pre-downloads
    this model at IMAGE BUILD time (not container start time) specifically
    so the running container never needs to reach the internet for this.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self.index: faiss.Index | None = None
        self.chunks: list[KnowledgeChunk] = []

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def build(self, chunks: list[KnowledgeChunk] | None = None) -> None:
        self.chunks = chunks or KNOWLEDGE_CHUNKS
        texts = [f"{c.title}. {c.content}" for c in self.chunks]
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        embeddings = np.asarray(embeddings, dtype="float32")

        dim = embeddings.shape[1]
        # Inner product on normalized vectors = cosine similarity
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)

    def save(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        faiss.write_index(self.index, os.path.join(directory, "knowledge.index"))
        with open(os.path.join(directory, "chunks.pkl"), "wb") as f:
            pickle.dump(self.chunks, f)

    def load(self, directory: str) -> None:
        self.index = faiss.read_index(os.path.join(directory, "knowledge.index"))
        with open(os.path.join(directory, "chunks.pkl"), "rb") as f:
            self.chunks = pickle.load(f)

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        if self.index is None:
            raise RuntimeError("Index not built or loaded. Call build() or load() first.")
        query_embedding = self.model.encode([query], normalize_embeddings=True)
        query_embedding = np.asarray(query_embedding, dtype="float32")
        scores, indices = self.index.search(query_embedding, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            results.append(RetrievedChunk(chunk=self.chunks[idx], similarity_score=float(score)))
        return results


_kb_singleton: FaissKnowledgeBase | None = None


def get_knowledge_base(index_dir: str = "/app/data/faiss_index") -> FaissKnowledgeBase:
    """
    Lazily builds (or loads, if already persisted) the singleton FAISS
    knowledge base used by both the Copilot and the Advisor.
    """
    global _kb_singleton
    if _kb_singleton is not None:
        return _kb_singleton

    kb = FaissKnowledgeBase()
    index_path = os.path.join(index_dir, "knowledge.index")
    if os.path.exists(index_path):
        kb.load(index_dir)
    else:
        kb.build()
        kb.save(index_dir)
    _kb_singleton = kb
    return kb


if __name__ == "__main__":
    kb = FaissKnowledgeBase()
    kb.build()
    print(f"Indexed {len(kb.chunks)} chunks, dimension {kb.index.d}")

    test_queries = [
        "why did my bill increase this month",
        "which instances should I terminate",
        "show idle resources",
        "should I use reserved instances or spot",
    ]
    for q in test_queries:
        print(f"\nQuery: {q!r}")
        results = kb.retrieve(q, top_k=3)
        for r in results:
            print(f"  [{r.similarity_score:.3f}] {r.chunk.chunk_id} ({r.chunk.category}): {r.chunk.title}")
