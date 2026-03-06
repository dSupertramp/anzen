import os
import time
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from typing import List, Dict, Any, Union
from sentence_transformers import SentenceTransformer
from anzen.guards.prompt import _layer1 as prompt_layer1


_root = Path(__file__).resolve().parent.parent.parent
_ml_cache = _root / "ml"
os.environ.setdefault("HF_HOME", str(_ml_cache))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(_ml_cache))


# Lazy imports
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        if SentenceTransformer is None:
            _embedder = "unavailable"
        else:
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


@dataclass
class ChunkResult:
    text: str
    risk_score: float
    is_blocked: bool
    is_alerted: bool
    explanation: str
    injection_score: float = 0.0  # score from prompt injection check
    relevance_score: float = 1.0  # cosine sim to query (higher = more relevant)
    outlier_score: float = 0.0  # how different from other chunks (higher = more anomalous)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RAGResult:
    safe_chunks: List[str]
    chunk_results: List[ChunkResult]
    blocked_count: int
    alerted_count: int
    latency_ms: float

    @property
    def has_threats(self) -> bool:
        return self.blocked_count > 0 or self.alerted_count > 0


class RAGGuard:
    """
    Scans RAG chunks before they are injected into the LLM context.

    Usage:
        guard = RAGGuard()

        # Filter a list of chunks before passing to LLM
        result = guard.scan(chunks, query="What is the refund policy?")
        safe_chunks = result.safe_chunks

        # Or scan a single chunk
        chunk_result = guard.scan_chunk(chunk, query=query)
    """

    def __init__(
        self,
        block_threshold: float = 0.80,
        alert_threshold: float = 0.45,
        relevance_threshold: float = 0.20,
        max_injection_score: float = 0.60,
        use_embeddings: bool = True,
    ):
        self.block_threshold = block_threshold
        self.alert_threshold = alert_threshold
        self.relevance_threshold = relevance_threshold
        self.max_injection_score = max_injection_score
        self.use_embeddings = use_embeddings
        self._injection_check = prompt_layer1

    # ─── Public API ──────────────────────────────────────────────────────────

    def scan(
        self,
        chunks: List[Union[str, Dict]],
        query: str | None = None,
    ) -> RAGResult:
        """
        Scan a list of chunks. Accepts plain strings or dicts with a 'text'/'page_content' key
        (compatible with LangChain Document objects).
        Returns RAGResult with safe_chunks and per-chunk analysis.
        """
        t0 = time.perf_counter()

        # Normalize to strings, keeping originals for output
        texts = [self._extract_text(c) for c in chunks]

        # Compute embeddings once for the whole batch
        embeddings = None
        query_embedding = None
        if self.use_embeddings and texts:
            embeddings, query_embedding = self._embed_batch(texts, query)

        results: List[ChunkResult] = []
        for i, text in enumerate(texts):
            emb = embeddings[i] if embeddings is not None else None
            q_emb = query_embedding
            result = self._analyze_chunk(text, i, texts, emb, q_emb, embeddings)
            results.append(result)

        safe_chunks = [chunks[i] for i, r in enumerate(results) if not r.is_blocked]

        return RAGResult(
            safe_chunks=safe_chunks,
            chunk_results=results,
            blocked_count=sum(1 for r in results if r.is_blocked),
            alerted_count=sum(1 for r in results if r.is_alerted and not r.is_blocked),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    def scan_chunk(self, chunk: Union[str, Dict], query: str | None = None) -> ChunkResult:
        """Scan a single chunk."""
        result = self.scan([chunk], query=query)
        return result.chunk_results[0]

    # ─── Internal ────────────────────────────────────────────────────────────

    def _extract_text(self, chunk) -> str:
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            return chunk.get("text") or chunk.get("page_content") or chunk.get("content") or str(chunk)
        # LangChain Document
        if hasattr(chunk, "page_content"):
            return chunk.page_content
        return str(chunk)

    def _embed_batch(self, texts: List[str], query: str | None):
        embedder = _get_embedder()
        if embedder == "unavailable":
            return None, None
        try:
            all_texts = texts + ([query] if query else [])
            all_embs = embedder.encode(all_texts, normalize_embeddings=True)
            chunk_embs = all_embs[: len(texts)]
            query_emb = all_embs[len(texts)] if query else None
            return chunk_embs, query_emb
        except Exception:
            return None, None

    def _cosine(self, a, b) -> float:
        try:
            return float(np.dot(a, b))  # already normalized
        except Exception:
            return 1.0

    def _analyze_chunk(
        self,
        text: str,
        index: int,
        all_texts: List[str],
        embedding,
        query_embedding,
        all_embeddings,
    ) -> ChunkResult:

        reasons = []
        injection_score = 0.0
        relevance_score = 1.0
        outlier_score = 0.0

        # ── 1. Injection check (reuse PromptGuard Layer 1) ──────────────────
        l1 = self._injection_check(text)
        if l1:
            injection_score = l1.risk_score
            reasons.append(f"injection pattern detected ({l1.explanation})")

        # ── 2. Relevance check (vs query) ───────────────────────────────────
        if embedding is not None and query_embedding is not None:
            relevance_score = self._cosine(embedding, query_embedding)
            if relevance_score < self.relevance_threshold:
                reasons.append(f"low relevance to query (cosine={relevance_score:.2f})")

        # ── 3. Outlier check (vs other chunks in batch) ─────────────────────
        if embedding is not None and all_embeddings is not None and len(all_embeddings) > 1:
            others = [all_embeddings[j] for j in range(len(all_embeddings)) if j != index]
            avg_sim = float(np.mean([self._cosine(embedding, o) for o in others]))
            outlier_score = max(0.0, 1.0 - avg_sim)
            if outlier_score > 0.65:
                reasons.append(f"semantic outlier among chunks (score={outlier_score:.2f})")

        # ── Combine scores ───────────────────────────────────────────────────
        risk_score = max(
            injection_score,
            (1.0 - relevance_score) * 0.6 if relevance_score < self.relevance_threshold else 0.0,
            outlier_score * 0.7 if outlier_score > 0.65 else 0.0,
        )

        # Boost if injection AND irrelevance both fire
        if injection_score > 0 and relevance_score < self.relevance_threshold:
            risk_score = min(1.0, risk_score * 1.25)

        explanation = "; ".join(reasons) if reasons else "clean"

        return ChunkResult(
            text=text,
            risk_score=risk_score,
            is_blocked=risk_score >= self.block_threshold,
            is_alerted=risk_score >= self.alert_threshold,
            explanation=explanation,
            injection_score=injection_score,
            relevance_score=relevance_score,
            outlier_score=outlier_score,
        )
