"""RAG (Retrieval-Augmented Generation) module — Task 2 + Task 7.

Implements:
- Intelligent document chunking
- sentence-transformers embeddings (all-MiniLM-L6-v2)
- FAISS vector store
- Top-k retrieval
- MMR (Max Marginal Relevance) for deduplicated, diverse retrieval (Task 7)
"""

import logging
import re
import time
from typing import TYPE_CHECKING, List, Optional

import numpy as np

if TYPE_CHECKING:
    from backend.utils.metrics import MetricsCollector

logger = logging.getLogger(__name__)


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences using simple regex heuristics."""
    # Split on sentence-ending punctuation followed by whitespace/newline
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_document(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
    min_chunk_len: int = 50,
) -> List[str]:
    """Chunk document text intelligently.

    Strategy:
    1. Split on paragraph boundaries first (double newlines).
    2. If a paragraph is too long, split further by sentences.
    3. Merge short paragraphs with the next one to avoid tiny chunks.
    4. Apply sliding window overlap between chunks.

    Args:
        text: Raw document text.
        chunk_size: Target max characters per chunk.
        overlap: Character overlap between consecutive chunks.
        min_chunk_len: Minimum characters for a chunk to be kept.

    Returns:
        List of text chunks.
    """
    if not text:
        return []

    # Step 1: Split on paragraph boundaries
    paragraphs = re.split(r"\n{2,}", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # Step 2: Break oversized paragraphs into sentence groups
    raw_chunks: List[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            raw_chunks.append(para)
        else:
            sentences = _split_into_sentences(para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= chunk_size:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        raw_chunks.append(current)
                    current = sent
            if current:
                raw_chunks.append(current)

    # Step 3: Merge tiny chunks with the next one
    merged: List[str] = []
    buffer = ""
    for chunk in raw_chunks:
        if len(buffer) + len(chunk) + 1 <= chunk_size:
            buffer = (buffer + " " + chunk).strip()
        else:
            if buffer:
                merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)

    # Step 4: Apply overlap — re-attach tail of previous chunk to start of next
    if overlap <= 0 or len(merged) <= 1:
        return [c for c in merged if len(c) >= min_chunk_len]

    overlapped: List[str] = [merged[0]]
    for i in range(1, len(merged)):
        prev_tail = merged[i - 1][-overlap:] if len(merged[i - 1]) > overlap else merged[i - 1]
        overlapped.append((prev_tail + " " + merged[i]).strip())

    return [c for c in overlapped if len(c) >= min_chunk_len]


class RAGIndexer:
    """Builds and queries a FAISS index over document chunks.

    Uses sentence-transformers all-MiniLM-L6-v2 for embeddings.
    Falls back to TF-IDF keyword matching if sentence-transformers
    or FAISS are not available.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", metrics: "Optional[MetricsCollector]" = None):
        self.model_name = model_name
        self.chunks: List[str] = []
        self.index = None
        self._embedder = None
        self._use_faiss = True
        self._embeddings: Optional[np.ndarray] = None
        # H-2: optional metrics collector for retrieval latency tracking
        self._metrics = metrics

        self._init_embedder()

    def _init_embedder(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.model_name)
            logger.info(f"RAG: Loaded sentence-transformer '{self.model_name}'")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. RAG will use keyword fallback. "
                "Install with: pip install sentence-transformers"
            )
            self._embedder = None
            self._use_faiss = False

        if self._use_faiss:
            try:
                import faiss  # noqa: F401
            except ImportError:
                logger.warning(
                    "faiss-cpu not installed. RAG will use keyword fallback. "
                    "Install with: pip install faiss-cpu"
                )
                self._use_faiss = False

    def build_index(self, chunks: List[str]) -> None:
        """Embed all chunks and build FAISS index."""
        self.chunks = chunks
        if not chunks:
            return

        if not self._use_faiss or self._embedder is None:
            logger.info("RAG: Using keyword fallback (no FAISS/sentence-transformers).")
            return

        import faiss

        logger.info(f"RAG: Embedding {len(chunks)} chunks...")
        embeddings = self._embedder.encode(
            chunks,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        self._embeddings = embeddings.astype("float32")

        dim = self._embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # Inner product = cosine similarity (normalized)
        self.index.add(self._embeddings)
        logger.info(f"RAG: FAISS index built with {self.index.ntotal} vectors (dim={dim}).")

    def retrieve(self, query: str, top_k: int = 5, use_mmr: bool = True, mmr_lambda: float = 0.6) -> List[str]:
        """Retrieve top-k most relevant chunks for a query.

        Task 7: uses MMR (Max Marginal Relevance) by default to return
        diverse, non-redundant chunks. Falls back to keyword overlap if
        FAISS is unavailable.

        Args:
            query: Search query string.
            top_k: Number of chunks to return.
            use_mmr: If True, apply MMR for diversity (Task 7).
            mmr_lambda: MMR trade-off: 1.0 = pure relevance, 0.0 = pure diversity.
        """
        if not self.chunks:
            return []

        t0 = time.perf_counter()

        if self._use_faiss and self.index is not None and self._embedder is not None:
            if use_mmr:
                result = self._mmr_retrieve(query, top_k, mmr_lambda)
            else:
                result = self._faiss_retrieve(query, top_k)
        else:
            result = self._keyword_retrieve(query, top_k)

        # H-2: record retrieval latency
        if self._metrics is not None:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._metrics.record_retrieval(elapsed_ms)

        return result

    def retrieve_with_ids(self, query: str, top_k: int = 5, use_mmr: bool = True, mmr_lambda: float = 0.6) -> List[tuple]:
        """Retrieve top-k chunks with their indices.
        
        Task #9: Source traceability — returns (chunk_id, chunk_text) tuples.

        Args:
            query: Search query string.
            top_k: Number of chunks to return.
            use_mmr: If True, apply MMR for diversity.
            mmr_lambda: MMR trade-off parameter.

        Returns:
            List of (chunk_id, chunk_text) tuples.
        """
        if not self.chunks:
            return []

        t0 = time.perf_counter()

        if self._use_faiss and self.index is not None and self._embedder is not None:
            if use_mmr:
                indices = self._mmr_retrieve_indices(query, top_k, mmr_lambda)
            else:
                indices = self._faiss_retrieve_indices(query, top_k)
        else:
            indices = self._keyword_retrieve_indices(query, top_k)

        # H-2: record retrieval latency
        if self._metrics is not None:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._metrics.record_retrieval(elapsed_ms)

        return [(idx, self.chunks[idx]) for idx in indices]

    def _faiss_retrieve(self, query: str, top_k: int) -> List[str]:
        import faiss  # noqa: F401

        q_emb = self._embedder.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        k = min(top_k, len(self.chunks))
        distances, indices = self.index.search(q_emb, k)

        results = []
        for idx in indices[0]:
            if 0 <= idx < len(self.chunks):
                results.append(self.chunks[idx])
        return results

    def _faiss_retrieve_indices(self, query: str, top_k: int) -> List[int]:
        """FAISS retrieval returning indices only."""
        import faiss  # noqa: F401

        q_emb = self._embedder.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        k = min(top_k, len(self.chunks))
        distances, indices = self.index.search(q_emb, k)

        results = []
        for idx in indices[0]:
            if 0 <= idx < len(self.chunks):
                results.append(int(idx))
        return results

    def _mmr_retrieve(self, query: str, top_k: int, mmr_lambda: float = 0.6) -> List[str]:
        """Max Marginal Relevance retrieval — Task 7.

        Selects chunks that are both relevant to the query AND diverse
        from each other, eliminating near-duplicate chunks.

        Algorithm:
          1. Fetch a candidate pool (top_k * 3 by cosine similarity).
          2. Iteratively pick the chunk that maximises:
             MMR = lambda * sim(chunk, query) - (1-lambda) * max_sim(chunk, selected)
        """
        indices = self._mmr_retrieve_indices(query, top_k, mmr_lambda)
        return [self.chunks[i] for i in indices]

    def _mmr_retrieve_indices(self, query: str, top_k: int, mmr_lambda: float = 0.6) -> List[int]:
        """MMR retrieval returning indices only."""
        pool_size = min(top_k * 3, len(self.chunks))
        if pool_size == 0:
            return []

        q_emb = self._embedder.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        # Fetch candidate pool
        distances, indices = self.index.search(q_emb, pool_size)
        candidate_indices = [int(idx) for idx in indices[0] if 0 <= idx < len(self.chunks)]
        if not candidate_indices:
            return []

        candidate_embeddings = self._embeddings[candidate_indices]  # (pool, dim)
        query_sims = distances[0][: len(candidate_indices)]  # cosine sims to query

        selected_indices: List[int] = []
        selected_embeddings: List[np.ndarray] = []

        remaining = list(range(len(candidate_indices)))

        for _ in range(min(top_k, len(candidate_indices))):
            if not remaining:
                break

            best_score = -float("inf")
            best_pos = -1

            for pos in remaining:
                relevance = float(query_sims[pos])

                if selected_embeddings:
                    # Max similarity to any already-selected chunk
                    sel_embs = np.stack(selected_embeddings)  # (n_sel, dim)
                    redundancy = float(np.max(candidate_embeddings[pos] @ sel_embs.T))
                else:
                    redundancy = 0.0

                score = mmr_lambda * relevance - (1.0 - mmr_lambda) * redundancy
                if score > best_score:
                    best_score = score
                    best_pos = pos

            if best_pos == -1:
                break

            selected_indices.append(candidate_indices[best_pos])
            selected_embeddings.append(candidate_embeddings[best_pos])
            remaining.remove(best_pos)

        return selected_indices

    def _keyword_retrieve(self, query: str, top_k: int) -> List[str]:
        """Simple TF-IDF-like keyword overlap fallback."""
        query_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower()))
        if not query_tokens:
            return self.chunks[:top_k]

        scored = []
        for i, chunk in enumerate(self.chunks):
            chunk_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", chunk.lower()))
            overlap = len(query_tokens & chunk_tokens)
            scored.append((overlap, i, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, _, c in scored[:top_k]]

    def _keyword_retrieve_indices(self, query: str, top_k: int) -> List[int]:
        """Keyword retrieval returning indices only."""
        query_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower()))
        if not query_tokens:
            return list(range(min(top_k, len(self.chunks))))

        scored = []
        for i, chunk in enumerate(self.chunks):
            chunk_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", chunk.lower()))
            overlap = len(query_tokens & chunk_tokens)
            scored.append((overlap, i))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [idx for _, idx in scored[:top_k]]

    def retrieve_for_topic(self, topic: str, top_k: int = 5) -> str:
        """Retrieve and join top-k chunks as a single context string."""
        chunks = self.retrieve(topic, top_k=top_k)
        return "\n\n---\n\n".join(chunks)
