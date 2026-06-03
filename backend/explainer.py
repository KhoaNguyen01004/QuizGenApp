"""Explainer Agent — Task 10 + Task 8.

Responsibilities:
- Generate explanations ONLY for questions that passed adversary validation.
- Never waste tokens explaining rejected questions.
- Batch explanations in a single LLM call when possible.
- Fall back to parallel individual calls if batch fails.

BEFORE (old approach):
  One LLM call per question, sequential loop.
  Explains ALL questions including adversary-rejected ones.
  20 questions = 20 sequential LLM calls.

AFTER (new approach):
  Batch explanations (up to 10 per call).
  Only explains accepted questions (score ≥ threshold).
  Parallel fallback with ThreadPoolExecutor.
  ~5-10x fewer LLM calls.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.llm_provider import LLMProvider
from backend.utils.json_utils import safe_parse_json
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer

logger = logging.getLogger(__name__)


# ── Prompt templates ──────────────────────────────────────────────────────────

_EXPLAINER_BATCH_SYSTEM = """You are an expert educational explainer.
For each MCQ question provided, write a clear 2-sentence explanation of why the correct answer is right.

Requirements:
- Explanation must be grounded in the provided knowledge source.
- Sentence 1: State what concept/principle makes the answer correct.
- Sentence 2: Briefly explain why the other options are incorrect or less accurate.
- Use LaTeX inside $...$ for math. Double-escape backslashes: \\\\frac, \\\\cos
- Do NOT use emojis or decorative symbols.
- Keep explanations concise and educational.

OUTPUT FORMAT:
Return ONLY a valid JSON array. Each item must follow this exact schema:
{{
  "id": <question id>,
  "explanation": "Two-sentence explanation here."
}}

Return ONLY the JSON array, no other text."""

_EXPLAINER_BATCH_USER = """Generate explanations for these questions using the knowledge source.

KNOWLEDGE SOURCE:
{knowledge}

QUESTIONS:
{questions_json}

Return ONLY the JSON array of explanations."""


_EXPLAINER_SINGLE_SYSTEM = """You are an expert educational explainer.
Write a clear 2-sentence explanation for the following MCQ.

Requirements:
- Grounded in the provided knowledge source.
- Sentence 1: Why the correct answer is right.
- Sentence 2: Why the other options are wrong.
- Use LaTeX inside $...$ for math. Double-escape backslashes: \\\\frac, \\\\cos
- Return ONLY valid JSON: {{"explanation": "..."}}
"""

_EXPLAINER_SINGLE_USER = """Knowledge source:
{knowledge}

Question: {question}
Options: {options}
Correct Answer: {answer}

Return ONLY: {{"explanation": "..."}}"""


# ── ExplainerAgent ────────────────────────────────────────────────────────────

class ExplainerAgent:
    """Generates explanations for validated questions only."""

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
model: str = "qwen3:4b",
        timeout: int = 600,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.llm = llm or LLMProvider(model=model, timeout=timeout)
        self.metrics = metrics

    def _format_questions_for_batch(self, questions: List[Dict[str, Any]]) -> str:
        """Format questions compactly for batch prompt."""
        compact = []
        for q in questions:
            options = q.get("options", [])
            opts_labeled = {
                chr(65 + i): opt for i, opt in enumerate(options[:4])
            }
            compact.append({
                "id": q.get("id", 0),
                "question": q.get("question", ""),
                "options": opts_labeled,
                "correct_answer": q.get("answer", "A"),
            })
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def _parse_batch_explanations(self, raw: str) -> Dict[int, str]:
        """Parse batch explanation response into {id: explanation} map."""
        parsed = safe_parse_json(raw)
        if parsed is None:
            return {}

        result: Dict[int, str] = {}
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    qid = item.get("id", 0)
                    explanation = item.get("explanation", "")
                    if qid and explanation:
                        result[int(qid)] = str(explanation).strip()
        elif isinstance(parsed, dict):
            # Single explanation response
            explanation = parsed.get("explanation", "")
            if explanation:
                result[0] = str(explanation).strip()

        return result

    def _explain_batch(
        self,
        batch: List[Dict[str, Any]],
        knowledge: str,
        batch_idx: int,
    ) -> Dict[int, str]:
        """Explain a batch of questions in a single LLM call."""
        prompt = _EXPLAINER_BATCH_SYSTEM + "\n\n" + _EXPLAINER_BATCH_USER.format(
            knowledge=knowledge[:2500],
            questions_json=self._format_questions_for_batch(batch),
        )

        if self.metrics:
            self.metrics.add_token_usage("explainer", prompt)

        raw = self.llm.generate(
            prompt=prompt,
            options={"temperature": 0.2, "num_ctx": 6144},
        )

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        if raw:
            (OUTPUT_DIR / f"explainer_batch{batch_idx}.txt").write_text(raw, encoding="utf-8")
            return self._parse_batch_explanations(raw)

        return {}

    def _explain_single(self, q: Dict[str, Any], knowledge: str) -> str:
        """Fallback: explain a single question."""
        options = q.get("options", [])
        opts_str = ", ".join(
            f"{chr(65+i)}) {opt}" for i, opt in enumerate(options[:4])
        )
        prompt = _EXPLAINER_SINGLE_SYSTEM + "\n\n" + _EXPLAINER_SINGLE_USER.format(
            knowledge=knowledge[:2000],
            question=q.get("question", ""),
            options=opts_str,
            answer=q.get("answer", "A"),
        )

        raw = self.llm.generate(
            prompt=prompt,
            options={"temperature": 0.2, "num_ctx": 4096},
            format="json",
        )

        if raw:
            parsed = safe_parse_json(raw)
            if isinstance(parsed, dict):
                return str(parsed.get("explanation", "")).strip()

        return q.get("explanation", "No explanation available.")

    def _postprocess_explanation(self, text: str) -> str:
        """Clean up explanation text."""
        if not text:
            return "No explanation available."
        # Wrap bare math expressions in $...$
        if "$" not in text and re.search(
            r"\\(?:frac|cos|sin|tan|theta|phi|mathbf|alpha|beta|gamma|delta|sum|int|sqrt)",
            text,
        ):
            text = f"${text}$"
        return text.strip()

    def generate_explanations(
        self,
        knowledge_bricks: str,
        quiz_data: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        batch_size: int = 8,
        max_workers: int = 2,
        rag_indexer: Optional[RAGIndexer] = None,
    ) -> List[Dict[str, Any]]:
        """Generate explanations for validated questions only.

        Args:
            knowledge_bricks: Markdown knowledge from CuratorAgent.
            quiz_data: Validated questions from AdversaryAgent.
            output_path: Optional path to save output JSON.
            batch_size: Questions per batch LLM call.
            max_workers: Parallel batch workers.
            rag_indexer: RAG index for per-question context retrieval.

        Returns:
            Quiz data with explanations added.
        """
        if not quiz_data:
            return []

        if self.metrics:
            self.metrics.start_timer("explainer")

        if not self.llm.is_available():
            logger.warning("Explainer: Ollama not available, keeping existing explanations.")
            if self.metrics:
                self.metrics.stop_timer("explainer")
            return quiz_data


        # Instrumentation: log Stage C input completeness before generation
        input_ids = [q.get("id") for q in quiz_data if isinstance(q, dict)]
        missing_expl_before = [
            q.get("id")
            for q in quiz_data
            if isinstance(q, dict) and (q.get("explanation") is None)
        ]
        logger.info(
            f"Stage C input: {len(quiz_data)} questions; "
            f"missing explanation placeholders: {len(missing_expl_before)}"
        )
        if missing_expl_before:
            logger.warning(f"Stage C input missing explanations for IDs: {missing_expl_before}")

        # Only explain questions that passed adversary validation
        # (adversary_flag=False means accepted)
        questions_to_explain = [
            q for q in quiz_data
            if isinstance(q, dict) and not q.get("adversary_flag", False)
        ]

        skipped = len(quiz_data) - len(questions_to_explain)
        if skipped > 0:
            logger.info(f"Explainer: Skipping {skipped} rejected questions (saving tokens).")

        logger.info(f"Explainer: Generating explanations for {len(questions_to_explain)} questions...")

        # Split into batches
        batches: List[tuple] = []
        for i in range(0, len(questions_to_explain), batch_size):
            batches.append((i // batch_size, questions_to_explain[i : i + batch_size]))

        # Explanation map: question_id → explanation
        explanation_map: Dict[int, str] = {}

        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(
                    self._explain_batch,
                    batch,
                    knowledge_bricks,
                    batch_idx,
                ): (batch_idx, batch)
                for batch_idx, batch in batches
            }

            for future in as_completed(future_to_batch):
                batch_idx, batch = future_to_batch[future]
                try:
                    explanations = future.result()
                    explanation_map.update(explanations)
                    logger.info(
                        f"Explainer: Batch {batch_idx+1}/{len(batches)} → "
                        f"{len(explanations)} explanations."
                    )

                    # Fallback: for questions in this batch that got no explanation
                    for q in batch:
                        qid = q.get("id", 0)
                        if qid not in explanation_map:
                            logger.warning(
                                f"Explainer: Q{qid} missing from batch response, "
                                "using single-call fallback."
                            )
                            explanation_map[qid] = self._explain_single(q, knowledge_bricks)

                except Exception as exc:
                    logger.error(f"Explainer: Batch {batch_idx+1} failed: {exc}")
                    # Fallback to individual calls for this batch
                    for q in batch:
                        qid = q.get("id", 0)
                        explanation_map[qid] = self._explain_single(q, knowledge_bricks)

        # Apply explanations back to quiz data
        result: List[Dict[str, Any]] = []
        for q in quiz_data:
            if not isinstance(q, dict):
                continue
            q2 = dict(q)
            qid = q2.get("id", 0)

            if not q2.get("adversary_flag", False):
                # Accepted question — apply new explanation
                new_explanation = explanation_map.get(qid, "")
                if new_explanation:
                    q2["explanation"] = self._postprocess_explanation(new_explanation)
                elif not q2.get("explanation"):
                    q2["explanation"] = q2.get("explanation") or "No explanation available."

            else:
                # Rejected question — keep existing or set placeholder
                if not q2.get("explanation"):
                    q2["explanation"] = "Question did not pass quality validation."

            result.append(q2)

        if self.metrics:
            self.metrics.stop_timer("explainer")

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "final_quiz.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if output_path:
            Path(output_path).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        return result
