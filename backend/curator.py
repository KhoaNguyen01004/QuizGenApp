"""Curator Agent — Task 4.

Responsibilities:
- Receive RAG-retrieved context chunks (NOT the full PDF).
- Identify core concepts, definitions, formulas, exam-relevant content.
- Output structured JSON knowledge bricks.
- Ignore references, bibliographies, administrative content.

BEFORE (old prompt):
  Free-form Markdown bullet list extraction from full document.
  No structure, fragile downstream parsing.

AFTER (new prompt):
  Structured JSON output with typed fields.
  RAG-grounded: only receives relevant chunks.
  Explicit filtering of noise content.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.llm_provider import LLMProvider
from backend.utils.json_utils import safe_parse_json
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer, chunk_document

logger = logging.getLogger(__name__)


# ── Prompt templates ──────────────────────────────────────────────────────────

_CURATOR_SYSTEM = """You are an educational content curator. Extract ONLY exam-relevant knowledge.

EXTRACT: core concepts, definitions, formulas, theorems, key terms, processes, learning objectives.
IGNORE: references, citations, author names, page numbers, administrative text, decorative content.

OUTPUT: JSON array only. Schema per item:
{"concept":"<name>","type":"definition|formula|theorem|process|principle|term","content":"<precise text>","importance":"high|medium|low","topic":"<broader topic>"}

Rules: plain text; LaTeX inside $...$; double-escape backslashes (\\\\frac); no invented content; no emojis; return array only."""

_CURATOR_USER = """Extract knowledge bricks from:

{context}

Return JSON array only."""


_MERGE_SYSTEM = """Merge partial knowledge brick lists into one deduplicated JSON array.
Keep the most complete version of each concept. Remove exact and near-duplicates.
Return JSON array only."""

_MERGE_USER = """Merge these lists:

{partials}

Return merged JSON array only."""


# ── CuratorAgent ──────────────────────────────────────────────────────────────

class CuratorAgent:
    """Extracts structured knowledge bricks from RAG-retrieved context."""

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
model: str = "qwen3:4b",
        timeout: int = 600,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.llm = llm or LLMProvider(model=model, timeout=timeout)
        self.metrics = metrics

    def _build_prompt(self, context: str) -> str:
        return _CURATOR_SYSTEM + "\n\n" + _CURATOR_USER.format(context=context)

    def _build_merge_prompt(self, partials_json: str) -> str:
        return _MERGE_SYSTEM + "\n\n" + _MERGE_USER.format(partials=partials_json)

    def _parse_knowledge_bricks(self, raw: str) -> List[Dict[str, Any]]:
        """Parse LLM output into a list of knowledge brick dicts."""
        parsed = safe_parse_json(raw)
        if parsed is None:
            return []
        if isinstance(parsed, list):
            # Validate each item has required fields
            valid = []
            for item in parsed:
                if isinstance(item, dict) and "concept" in item and "content" in item:
                    # Ensure all required fields exist with defaults
                    item.setdefault("type", "definition")
                    item.setdefault("importance", "medium")
                    item.setdefault("topic", "General")
                    valid.append(item)
            return valid
        return []

    def _bricks_to_markdown(self, bricks: List[Dict[str, Any]]) -> str:
        """Convert structured bricks to readable Markdown for downstream agents."""
        if not bricks:
            return ""
        lines = []
        for b in bricks:
            concept = b.get("concept", "")
            content = b.get("content", "")
            btype = b.get("type", "")
            topic = b.get("topic", "")
            lines.append(f"- **[{btype.upper()}]** {concept} ({topic}): {content}")
        return "\n".join(lines)

    def extract_knowledge(
        self,
        md_content: str,
        rag_indexer: Optional[RAGIndexer] = None,
        top_k: int = 8,
    ) -> str:
        """Extract knowledge bricks from document content.

        If a RAGIndexer is provided, uses RAG to retrieve relevant chunks
        and processes them in parallel batches.
        Otherwise falls back to chunked sequential processing.

        Args:
            md_content: Full extracted Markdown text.
            rag_indexer: Pre-built RAG index (optional but recommended).
            top_k: Number of chunks to retrieve per query.

        Returns:
            Markdown string of knowledge bricks for downstream agents.
        """
        if self.metrics:
            self.metrics.start_timer("curator")

        if not self.llm.is_available():
            logger.error("Curator: Ollama is not running.")
            if self.metrics:
                self.metrics.stop_timer("curator")
            return ""

        logger.info("Curator: Extracting knowledge bricks...")

        # Strategy: if RAG index available, query with broad topics
        # Otherwise chunk the document directly
        if rag_indexer is not None and rag_indexer.chunks:
            contexts = self._get_rag_contexts(rag_indexer, top_k)
        else:
            contexts = self._get_chunked_contexts(md_content)

        logger.info(f"Curator: Processing {len(contexts)} context segments in parallel...")

        # Task 6: parallelize context segment processing
        all_bricks: List[Dict[str, Any]] = []

        def _process_segment(idx_ctx):
            idx, ctx = idx_ctx
            prompt = self._build_prompt(ctx)
            if self.metrics:
                self.metrics.add_token_usage("curator", prompt)
            raw = self.llm.generate(
                prompt=prompt,
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            if raw:
                bricks = self._parse_knowledge_bricks(raw)
                logger.info(f"Curator: Segment {idx+1}/{len(contexts)} → {len(bricks)} bricks")
                return bricks
            return []

        max_workers = min(3, len(contexts))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_segment, (i, ctx)): i
                for i, ctx in enumerate(contexts)
            }
            for future in as_completed(futures):
                try:
                    bricks = future.result()
                    all_bricks.extend(bricks)
                except Exception as exc:
                    logger.error(f"Curator: Segment processing failed: {exc}")

        # Deduplicate if we have multiple segments
        if len(contexts) > 1 and all_bricks:
            all_bricks = self._deduplicate_bricks(all_bricks)

        if not all_bricks:
            logger.warning("Curator: No knowledge bricks extracted.")
            if self.metrics:
                self.metrics.stop_timer("curator")
            return ""

        # Save structured JSON for debugging
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "knowledge_bricks.json").write_text(
            json.dumps(all_bricks, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Convert to Markdown for downstream agents
        result = self._bricks_to_markdown(all_bricks)
        (OUTPUT_DIR / "knowledge_bricks.md").write_text(result, encoding="utf-8")

        logger.info(f"Curator: Extracted {len(all_bricks)} knowledge bricks.")

        if self.metrics:
            self.metrics.stop_timer("curator")
            self.metrics.metrics.rag_chunks_used = len(contexts)

        return result

    def _get_rag_contexts(self, rag_indexer: RAGIndexer, top_k: int) -> List[str]:
        """Query RAG index with broad educational topic queries."""
        queries = [
            "core concepts definitions principles",
            "mathematical formulas equations theorems",
            "key terminology important terms",
            "processes algorithms steps procedures",
            "learning objectives outcomes",
        ]
        seen: set = set()
        contexts: List[str] = []
        for query in queries:
            chunks = rag_indexer.retrieve(query, top_k=top_k)
            for chunk in chunks:
                # Deduplicate by first 100 chars
                key = chunk[:100]
                if key not in seen:
                    seen.add(key)
                    contexts.append(chunk)

        # Group into batches of ~3000 chars to stay within context window
        return self._group_into_batches(contexts, max_chars=3000)

    def _get_chunked_contexts(self, md_content: str) -> List[str]:
        """Fallback: chunk the document directly."""
        chunks = chunk_document(md_content, chunk_size=3000, overlap=200)
        return chunks

    def _group_into_batches(self, chunks: List[str], max_chars: int = 3000) -> List[str]:
        """Group chunks into batches that fit within max_chars."""
        batches: List[str] = []
        current = ""
        for chunk in chunks:
            if len(current) + len(chunk) + 4 <= max_chars:
                current = (current + "\n\n" + chunk).strip()
            else:
                if current:
                    batches.append(current)
                current = chunk
        if current:
            batches.append(current)
        return batches

    def _deduplicate_bricks(self, bricks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate bricks by concept name (case-insensitive)."""
        seen_concepts: set = set()
        unique: List[Dict[str, Any]] = []
        for brick in bricks:
            key = brick.get("concept", "").lower().strip()
            if key and key not in seen_concepts:
                seen_concepts.add(key)
                unique.append(brick)
        return unique
