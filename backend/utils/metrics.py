"""Pipeline metrics collector — Task 8 (extended).

New in Task 8:
- prompt_tokens / completion_tokens per agent (estimated)
- average_latency_per_agent (ms)
- retrieval_latency (ms)
- ocr_latency (ms)
- ollama_latency (ms, total LLM wall-clock time)
- All metrics saved to outputs/metrics.json
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class PipelineMetrics:
    # ── Run identity ──────────────────────────────────────────────────────────
    # Fix C-1: these were previously set as dynamic attributes and omitted from
    # metrics.json (dataclasses.asdict() only serialises declared fields).
    model_used: str = ""
    num_questions_requested: int = 0
    rag_chunks_used: int = 0
    ocr_skipped: bool = False

    # ── Timing (seconds) ──────────────────────────────────────────────────────
    extraction_time: float = 0.0
    native_extraction_time: float = 0.0   # Task 8: native-only portion
    ocr_time: float = 0.0                 # Task 8: OCR portion (0 if skipped)
    rag_index_time: float = 0.0
    retrieval_latency_ms: float = 0.0     # Task 8: avg RAG retrieval latency
    curator_time: float = 0.0
    pedagogue_time: float = 0.0
    adversary_time: float = 0.0
    explainer_time: float = 0.0
    total_time: float = 0.0

    # ── Per-agent average latency (ms per LLM call) ───────────────────────────
    avg_latency_curator_ms: float = 0.0   # Task 8
    avg_latency_pedagogue_ms: float = 0.0 # Task 8
    avg_latency_adversary_ms: float = 0.0 # Task 8
    avg_latency_explainer_ms: float = 0.0 # Task 8
    ollama_total_latency_ms: float = 0.0  # Task 8: sum of all LLM call durations
    ollama_calls: int = 0
    avg_ollama_latency_ms: float = 0.0

    # ── Question counts ───────────────────────────────────────────────────────
    candidates_generated: int = 0
    questions_validated: int = 0
    questions_rejected: int = 0
    questions_accepted: int = 0

    # ── Quality ───────────────────────────────────────────────────────────────
    average_adversary_score: float = 0.0
    acceptance_rate: float = 0.0

    # ── Token usage (estimated from prompt/response lengths) ──────────────────
    # Task 8: split into prompt vs completion tokens per agent
    prompt_tokens_curator: int = 0
    completion_tokens_curator: int = 0
    prompt_tokens_pedagogue: int = 0
    completion_tokens_pedagogue: int = 0
    prompt_tokens_adversary: int = 0
    completion_tokens_adversary: int = 0
    prompt_tokens_explainer: int = 0
    completion_tokens_explainer: int = 0
    estimated_tokens_total: int = 0

    # Legacy fields (kept for backward compat)
    estimated_tokens_curator: int = 0
    estimated_tokens_pedagogue: int = 0
    estimated_tokens_adversary: int = 0
    estimated_tokens_explainer: int = 0

    # ── Quality metrics (Task #10) ────────────────────────────────────────────
    answer_consistency_failures: int = 0
    explanation_consistency_failures: int = 0
    unsupported_questions: int = 0
    duplicate_topics: int = 0
    ambiguity_failures: int = 0
    questions_with_issues: int = 0
    json_parse_failures: int = 0
    repair_attempts: int = 0
    adversary_failures: int = 0
    missing_explanations: int = 0


class MetricsCollector:
    """Collects and persists pipeline metrics."""

    def __init__(self):
        self.metrics = PipelineMetrics()
        self._timers: Dict[str, float] = {}
        # Task 8: per-agent LLM call tracking
        self._llm_call_counts: Dict[str, int] = {}
        self._llm_call_total_ms: Dict[str, float] = {}
        self._retrieval_call_count: int = 0
        self._retrieval_total_ms: float = 0.0

    def start_timer(self, phase: str):
        self._timers[phase] = time.perf_counter()

    def stop_timer(self, phase: str):
        if phase not in self._timers:
            return
        elapsed = time.perf_counter() - self._timers.pop(phase)
        attr = f"{phase}_time"
        if hasattr(self.metrics, attr):
            setattr(self.metrics, attr, round(elapsed, 2))

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return max(1, len(text) // 4)

    def add_token_usage(self, phase: str, prompt: str, response: str = ""):
        """Track prompt and completion tokens separately (Task 8)."""
        prompt_toks = self.estimate_tokens(prompt)
        completion_toks = self.estimate_tokens(response) if response else 0

        # New per-agent split fields
        p_attr = f"prompt_tokens_{phase}"
        c_attr = f"completion_tokens_{phase}"
        if hasattr(self.metrics, p_attr):
            setattr(self.metrics, p_attr, getattr(self.metrics, p_attr) + prompt_toks)
        if hasattr(self.metrics, c_attr):
            setattr(self.metrics, c_attr, getattr(self.metrics, c_attr) + completion_toks)

        # Legacy total field
        legacy_attr = f"estimated_tokens_{phase}"
        if hasattr(self.metrics, legacy_attr):
            current = getattr(self.metrics, legacy_attr)
            setattr(self.metrics, legacy_attr, current + prompt_toks + completion_toks)

        self.metrics.estimated_tokens_total += prompt_toks + completion_toks

    def record_llm_call(self, phase: str, duration_ms: float):
        """Record a single LLM call duration for per-agent latency (Task 8)."""
        self._llm_call_counts[phase] = self._llm_call_counts.get(phase, 0) + 1
        self._llm_call_total_ms[phase] = self._llm_call_total_ms.get(phase, 0.0) + duration_ms
        self.metrics.ollama_total_latency_ms = round(
            self.metrics.ollama_total_latency_ms + duration_ms, 1
        )
        self.metrics.ollama_calls += 1

    def record_retrieval(self, duration_ms: float):
        """Record a RAG retrieval call duration (Task 8)."""
        self._retrieval_call_count += 1
        self._retrieval_total_ms += duration_ms

    def set_ocr_times(self, native_time: float, ocr_time: float, ocr_skipped: bool):
        """Record extraction sub-timings from PDFExtractor (Task 8)."""
        self.metrics.native_extraction_time = round(native_time, 2)
        self.metrics.ocr_time = round(ocr_time, 2)
        self.metrics.ocr_skipped = ocr_skipped

    def finalize(self):
        """Compute derived metrics."""
        total = self.metrics.candidates_generated
        accepted = self.metrics.questions_accepted
        rejected = self.metrics.questions_rejected

        if total > 0:
            self.metrics.acceptance_rate = round(accepted / total * 100, 1)
        else:
            self.metrics.acceptance_rate = 0.0

        self.metrics.questions_rejected = total - accepted if total > 0 else rejected

        # Sum all phase times for total
        phase_times = [
            self.metrics.extraction_time,
            self.metrics.rag_index_time,
            self.metrics.curator_time,
            self.metrics.pedagogue_time,
            self.metrics.adversary_time,
            self.metrics.explainer_time,
        ]
        self.metrics.total_time = round(sum(phase_times), 2)

        # Task 8: compute per-agent average latency
        for phase in ("curator", "pedagogue", "adversary", "explainer"):
            count = self._llm_call_counts.get(phase, 0)
            total_ms = self._llm_call_total_ms.get(phase, 0.0)
            attr = f"avg_latency_{phase}_ms"
            if hasattr(self.metrics, attr):
                setattr(
                    self.metrics, attr,
                    round(total_ms / count, 1) if count > 0 else 0.0,
                )

        # Task 8: average retrieval latency
        if self._retrieval_call_count > 0:
            self.metrics.retrieval_latency_ms = round(
                self._retrieval_total_ms / self._retrieval_call_count, 1
            )

        if self.metrics.ollama_calls > 0:
            self.metrics.avg_ollama_latency_ms = round(
                self.metrics.ollama_total_latency_ms / self.metrics.ollama_calls, 1
            )

    def save(self, output_dir: str = "outputs"):
        self.finalize()
        out = Path(output_dir)
        out.mkdir(exist_ok=True)
        metrics_path = out / "metrics.json"
        metrics_path.write_text(
            json.dumps(asdict(self.metrics), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._log_summary()

    def _log_summary(self):
        m = self.metrics
        logging.info("=" * 60)
        logging.info("PIPELINE METRICS SUMMARY")
        logging.info("=" * 60)
        logging.info(f"  Model used:              {m.model_used}")
        logging.info(f"  Total time:              {m.total_time:.1f}s")
        logging.info(f"  Extraction (native):     {m.native_extraction_time:.1f}s")
        logging.info(f"  Extraction (OCR):        {m.ocr_time:.1f}s {'[SKIPPED]' if m.ocr_skipped else ''}")
        logging.info(f"  RAG indexing:            {m.rag_index_time:.1f}s")
        logging.info(f"  Avg retrieval latency:   {m.retrieval_latency_ms:.1f}ms")
        logging.info(f"  Curator:                 {m.curator_time:.1f}s  (avg {m.avg_latency_curator_ms:.0f}ms/call)")
        logging.info(f"  Pedagogue:               {m.pedagogue_time:.1f}s  (avg {m.avg_latency_pedagogue_ms:.0f}ms/call)")
        logging.info(f"  Adversary:               {m.adversary_time:.1f}s  (avg {m.avg_latency_adversary_ms:.0f}ms/call)")
        logging.info(f"  Explainer:               {m.explainer_time:.1f}s  (avg {m.avg_latency_explainer_ms:.0f}ms/call)")
        logging.info(f"  Ollama total latency:    {m.ollama_total_latency_ms:.0f}ms")
        logging.info(f"  Ollama calls:            {m.ollama_calls}")
        logging.info(f"  Avg Ollama latency:      {m.avg_ollama_latency_ms:.1f}ms")
        logging.info(f"  Candidates generated:    {m.candidates_generated}")
        logging.info(f"  Questions accepted:      {m.questions_accepted}")
        logging.info(f"  Questions rejected:      {m.questions_rejected}")
        logging.info(f"  Acceptance rate:         {m.acceptance_rate:.1f}%")
        logging.info(f"  Avg adversary score:     {m.average_adversary_score:.1f}/100")
        logging.info(f"  Prompt tokens (total):   {m.prompt_tokens_curator + m.prompt_tokens_pedagogue + m.prompt_tokens_adversary + m.prompt_tokens_explainer:,}")
        logging.info(f"  Completion tokens (tot): {m.completion_tokens_curator + m.completion_tokens_pedagogue + m.completion_tokens_adversary + m.completion_tokens_explainer:,}")
        logging.info(f"  Est. total tokens:       {m.estimated_tokens_total:,}")
        logging.info("=" * 60)
