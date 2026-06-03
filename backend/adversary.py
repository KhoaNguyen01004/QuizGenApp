"""Adversary Agent — Enhanced for quality assurance and educational rigor.

Implements Task 7/8 validation gatekeeping and strict JSON enforcement.

Key reliability guarantees (per Instruction.md):
- Strict JSON enforcement with at most one repair retry; invalid JSON => reject batch (FAILED per-question).
- Deterministic acceptance: accept = supported_by_source AND answer_consistent AND explanation_consistent AND score >= threshold.
- Deterministic final gatekeeper: only export questions that pass all checks.
- No heuristic fallback paths that could leak invalid/unsupported questions.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.llm_provider import LLMProvider
from backend.utils.json_utils import safe_parse_json
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer

logger = logging.getLogger(__name__)


# ── Prompt templates ───────────────────────────────────────────────────────────

_ADVERSARY_SYSTEM = """You are an MCQ quality auditor. Score each question 0-100 on rigorous criteria.

SCORING RUBRIC:
- Factual correctness (40%): Answer is factually correct per source. No wrong facts.
- Source support (30%): Answer is evidenced in source. Explanation cites source.
- Clarity (15%): Question is unambiguous. Only ONE correct answer (no ambiguity).
- Difficulty/Quality (15%): Distractors are plausible. Question tests understanding.

DETERMINISTIC SCORING RULES:
- supported_by_source=false => score <= 20, accept=false
- answer_consistent=false => score = 0, accept=false
- explanation_consistent=false => score = 0, accept=false
- Multiple valid answers (ambiguous) => score <= 20, accept=false
- Otherwise: score based on rubric above

ACCEPTANCE CRITERIA (all must be true):
accept = supported_by_source AND answer_consistent AND explanation_consistent AND score >= 50

OUTPUT: JSON array only. Schema per item:
{
  "id":<int>,
  "supported_by_source":<bool>,
  "answer_consistent":<bool>,
  "explanation_consistent":<bool>,
  "score":<int>,
  "accept":<bool>,
  "issues":["issue1","issue2"],
  "corrected_answer":"A|B|C|D|null"
}

Return JSON array ONLY. No other text."""

_ADVERSARY_USER = """VERIFICATION TASK:
1. Check if answer is factually correct per source (supported_by_source)
2. Verify explanation supports the marked answer (answer_consistent)
3. Verify explanation is supported by source (explanation_consistent)
4. Detect if multiple options could be correct (ambiguity)
5. Score on rubric, apply deterministic rules

SOURCE:
{knowledge}

QUESTIONS:
{questions_json}

Return JSON array only."""


class AdversaryAgent:
    """Validates and scores candidate questions, selects top N (deterministic gatekeeping)."""

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
model: str = "qwen3:4b",
        timeout: int = 600,
        acceptance_threshold: int = 60,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.llm = llm or LLMProvider(model=model, timeout=timeout)
        self.acceptance_threshold = acceptance_threshold
        self.metrics = metrics

    def _format_questions_for_prompt(self, questions: List[Dict[str, Any]]) -> str:
        compact = []
        for q in questions:
            options = q.get("options", [])
            opts_labeled = {chr(65 + i): opt for i, opt in enumerate(options[:4])}
            compact.append(
                {
                    "id": q.get("id", 0),
                    "question": q.get("question", ""),
                    "options": opts_labeled,
                    "marked_answer": q.get("answer", "A"),
                }
            )
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _parse_scores(self, raw: str) -> List[Dict[str, Any]]:
        parsed = safe_parse_json(raw or "")
        if parsed is None or not isinstance(parsed, list):
            return []

        results: List[Dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            q_id = item.get("id", 0)
            supported_by_source = bool(item.get("supported_by_source", False))
            answer_consistent = bool(item.get("answer_consistent", False))
            explanation_consistent = bool(item.get("explanation_consistent", False))

            score = item.get("score", 0)
            if not isinstance(score, (int, float)):
                try:
                    score = int(score)
                except (ValueError, TypeError):
                    score = 0
            score = max(0, min(100, int(score)))

            # TASK 6 deterministic scoring rules
            if not supported_by_source:
                score = min(score, 20)
            if not answer_consistent:
                score = 0
            if not explanation_consistent:
                score = 0

            accept = (
                supported_by_source
                and answer_consistent
                and explanation_consistent
                and score >= 50
            )

            corrected = item.get("corrected_answer")
            if corrected:
                corrected = str(corrected).strip().upper()
                if not re.match(r"^[ABCD]$", corrected):
                    corrected = None

            issues = item.get("issues", [])
            if not isinstance(issues, list):
                issues = []

            results.append(
                {
                    "id": q_id,
                    "supported_by_source": supported_by_source,
                    "answer_consistent": answer_consistent,
                    "explanation_consistent": explanation_consistent,
                    "score": score,
                    "verdict": "accept" if accept else "reject",
                    "accept": accept,
                    "corrected_answer": corrected,
                    "issues": issues,
                    "notes": str(item.get("notes", "")),
                }
            )

        return results

    def _reject_batch_as_failed(self, batch: List[Dict[str, Any]], issues: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "id": q.get("id", 0),
                "supported_by_source": False,
                "answer_consistent": False,
                "explanation_consistent": False,
                "score": 0,
                "verdict": "reject",
                "accept": False,
                "corrected_answer": None,
                "issues": issues,
                "notes": "; ".join(issues),
            }
            for q in batch
        ]

    def _validate_batch(
        self,
        batch: List[Dict[str, Any]],
        knowledge: str,
        batch_idx: int,
        rag_indexer: Optional[RAGIndexer] = None,
    ) -> List[Dict[str, Any]]:
        """Validate a single batch with strict JSON enforcement (Task 1/2).

        If JSON parsing fails, retry once with repair prompt.
        If still invalid, reject batch deterministically (FAILED per-question).
        """
        if rag_indexer is not None and getattr(rag_indexer, "chunks", None):
            query = " ".join(q.get("question", "")[:60] for q in batch)
            relevant_chunks = rag_indexer.retrieve(query, top_k=1)
            context = relevant_chunks[0] if relevant_chunks else knowledge[:800]
        else:
            context = knowledge[:800]

        prompt = _ADVERSARY_SYSTEM + "\n\n" + _ADVERSARY_USER.format(
            knowledge=context,
            questions_json=self._format_questions_for_prompt(batch),
        )

        if self.metrics:
            self.metrics.add_token_usage("adversary", prompt)

        t0 = time.perf_counter()
        raw = self.llm.generate(prompt=prompt, options={"temperature": 0.1, "num_ctx": 3072})
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if self.metrics:
            self.metrics.record_llm_call("adversary", elapsed_ms)

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        if raw:
            (OUTPUT_DIR / f"adversary_batch{batch_idx}.txt").write_text(raw, encoding="utf-8")

        if not raw:
            if self.metrics:
                self.metrics.metrics.adversary_failures += len(batch)
            return self._reject_batch_as_failed(batch, ["Adversary validation failed: no LLM response"])

        parsed = safe_parse_json(raw)
        if parsed is None or not isinstance(parsed, list):
            if self.metrics:
                self.metrics.metrics.json_parse_failures += 1

            logger.warning(
                f"Adversary: Batch {batch_idx} JSON parse failed, attempting repair (single retry)..."
            )

            repair_prompt = (
                "Extract ONLY the JSON array of validation results from this text.\n"
                "Each object needs: id, supported_by_source, answer_consistent, explanation_consistent, score, accept, issues.\n"
                "Return ONLY valid JSON array. No other text.\n\n"
                f"TEXT:\n{raw[:6000]}"
            )

            repair_raw = self.llm.generate(prompt=repair_prompt, options={"temperature": 0.1, "num_ctx": 3072})
            if self.metrics:
                self.metrics.metrics.repair_attempts += 1

            parsed = safe_parse_json(repair_raw)

        if parsed is None or not isinstance(parsed, list):
            logger.error(
                f"Adversary: Batch {batch_idx} JSON repair failed. Rejecting {len(batch)} questions."
            )
            if self.metrics:
                self.metrics.metrics.adversary_failures += len(batch)
            return self._reject_batch_as_failed(
                batch,
                ["Adversary validation failed: invalid JSON response after retry"],
            )

        # parsed is valid list => parse into structured results
        return self._parse_scores(json.dumps(parsed, ensure_ascii=False))

    def _final_validation_pass(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Task 7 final gatekeeper validation before export."""
        passed: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for q in questions:
            failures: List[str] = []
            q_id = q.get("id", 0)

            if not q.get("source_chunk_id"):
                failures.append("No source_chunk_id")
            if not q.get("answer"):
                failures.append("No answer")
            if not q.get("explanation"):
                failures.append("No explanation")
            if not q.get("question"):
                failures.append("No question")
            if not q.get("options") or len(q.get("options", [])) < 4:
                failures.append("Incomplete options")

            # adversary flags
            if not q.get("supported_by_source", False):
                failures.append("Not supported by source")
            if not q.get("answer_consistent", False):
                failures.append("Answer not consistent")
            if not q.get("explanation_consistent", False):
                failures.append("Explanation not consistent")
            if not q.get("accept", False) and q.get("adversary_flag", False):
                failures.append("Adversary rejected")

            if failures:
                logger.warning(f"Question {q_id} failed final validation: {'; '.join(failures)}")
                rejected.append(q)
                if self.metrics:
                    self.metrics.metrics.questions_with_issues += 1
            else:
                passed.append(q)

        logger.info(
            f"Adversary Final Gatekeeper: {len(passed)} passed, {len(rejected)} rejected final validation"
        )
        return passed

    def validate_quiz(
        self,
        knowledge_bricks: str,
        quiz_data: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        num_questions: Optional[int] = None,
        rag_indexer: Optional[RAGIndexer] = None,
    ) -> List[Dict[str, Any]]:
        """Public API used by main.py/api.py."""
        if not quiz_data:
            return []

        if self.metrics:
            self.metrics.start_timer("adversary")

        if not self.llm.is_available():
            logger.error("Adversary: Ollama is not running. Cannot validate questions.")
            if self.metrics:
                self.metrics.stop_timer("adversary")
            return []

        # Split into batches
        batch_size = 5
        max_workers = 3
        batches: List[Tuple[int, List[Dict[str, Any]]]] = []
        for i in range(0, len(quiz_data), batch_size):
            batches.append((i // batch_size, quiz_data[i : i + batch_size]))

        # Build score map
        score_map: Dict[int, Dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(
                    self._validate_batch,
                    batch,
                    knowledge_bricks,
                    batch_idx,
                    rag_indexer,
                ): batch_idx
                for batch_idx, batch in batches
            }

            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    scores = future.result()
                    for s in scores:
                        score_map[int(s["id"])] = s
                except Exception as exc:
                    logger.error(f"Adversary: Batch {batch_idx + 1} failed: {exc}")

        # Apply scores back to questions (CRITICAL: preserve full original question objects)
        scored_questions: List[Dict[str, Any]] = []
        for q in quiz_data:
            # IMPORTANT: start from the original question dict so no metadata is dropped
            q2 = dict(q)
            qid = int(q2.get("id", 0))
            score_info = score_map.get(qid)

            if score_info:
                q2["adversary_score"] = score_info.get("score", 0)
                q2["adversary_flag"] = not bool(score_info.get("accept", False))
                q2["validation_notes"] = " | ".join(score_info.get("issues", []) or [])

                q2["supported_by_source"] = score_info.get("supported_by_source", False)
                q2["answer_consistent"] = score_info.get("answer_consistent", False)
                q2["explanation_consistent"] = score_info.get("explanation_consistent", False)
                q2["accept"] = score_info.get("accept", False)

                corrected = score_info.get("corrected_answer")
                if corrected and corrected != str(q2.get("answer", "")).upper():
                    q2["answer"] = corrected
                    q2["correct_answer"] = ord(corrected) - 65
                    q2["answer_corrected"] = corrected
            else:
                q2["adversary_score"] = 0
                q2["adversary_flag"] = True
                q2["validation_notes"] = "No adversary validation"
                q2["supported_by_source"] = False
                q2["answer_consistent"] = False
                q2["explanation_consistent"] = False
                q2["accept"] = False

            # Integrity assertions (do not crash pipeline; log only)
            if q2.get("source_chunk_id", None) in (None, ""):
                logger.warning(f"Adversary: Q{qid} missing source_chunk_id")
            if "topic" not in q2:
                logger.warning(f"Adversary: Q{qid} missing topic")
            if q2.get("explanation", None) in (None, ""):
                # This is allowed pre-explainer, but adversary final gatekeeper expects it
                pass

            scored_questions.append(q2)

        scores_list = [q.get("adversary_score", 0) for q in scored_questions]
        avg_score = (sum(scores_list) / len(scores_list)) if scores_list else 0.0
        accepted = [q for q in scored_questions if not q.get("adversary_flag", True)]
        rejected = [q for q in scored_questions if q.get("adversary_flag", False)]


        if self.metrics:
            self.metrics.stop_timer("adversary")
            self.metrics.metrics.questions_validated = len(scored_questions)
            self.metrics.metrics.questions_rejected = len(rejected)
            self.metrics.metrics.average_adversary_score = round(avg_score, 1)

        # Deterministic top-N selection: ONLY those >= acceptance_threshold.
        sorted_q = sorted(scored_questions, key=lambda q: q.get("adversary_score", 0), reverse=True)
        above_threshold = [q for q in sorted_q if q.get("adversary_score", 0) >= self.acceptance_threshold]

        # If none meet threshold => return empty (deterministic gatekeeping)
        if not above_threshold:
            logger.warning(
                f"Adversary: No questions above threshold {self.acceptance_threshold}. Returning 0 questions."
            )
            final_candidates: List[Dict[str, Any]] = []
        else:
            if num_questions is not None:
                final_candidates = above_threshold[:num_questions]
            else:
                final_candidates = above_threshold

        for i, q in enumerate(final_candidates):
            q["id"] = i + 1

        # Task 7 gatekeeper (field + adversary consistency)
        final_validated = self._final_validation_pass(final_candidates)

        if self.metrics:
            self.metrics.metrics.questions_accepted = len(final_validated)

        # Save artifacts
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "adversary_scored.json").write_text(
            json.dumps(scored_questions, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if output_path:
            Path(output_path).write_text(
                json.dumps(final_validated, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        return final_validated

