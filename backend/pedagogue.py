"""Pedagogue Agent — Enhanced for educational quality.

Task #2: Two-stage question generation
  Stage A: Generate question + options + source_chunk_id (no answer yet)
  Stage B: Independently determine correct answer from source
  Stage C: Generate explanation from verified answer
  
Task #3: Source traceability
  - Track source_chunk_id, source_excerpt for every question
  - Enable auditing and validation

Task #4: Enhanced distractors
  - Prompts now include distractor quality guidelines
  - Distractors must be plausible, not obviously wrong
  
Task #5: Understanding-based questions
  - Target: 30% factual, 40% conceptual, 30% application
  - Vary question stems to encourage reasoning
  
Performance optimizations (Issue #2/#3/#4):
  - Truncate knowledge_bricks to 2000 chars per prompt
  - Use only top-3 RAG chunks for context
  - Parallel batch generation with ThreadPoolExecutor
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.llm_provider import LLMProvider
from backend.utils.json_utils import safe_parse_json
from backend.utils.markdown_cleaner import clean_markdown_output
from backend.utils.metrics import MetricsCollector
from backend.utils.rag import RAGIndexer

logger = logging.getLogger(__name__)

# Issue #3: cap knowledge sent per prompt
_MAX_KNOWLEDGE_CHARS = 2000
_MAX_CONTEXT_CHARS = 800


# ── Prompt templates ──────────────────────────────────────────────────────────

_PEDAGOGUE_SYSTEM = """You are an MCQ designer.
Target: 30% factual, 40% conceptual, 30% application.
Write understanding-based questions with 4 plausible options and exactly one correct answer.
Ground all content in the provided knowledge. Do not invent facts.
Output JSON array only:
[{"id":1,"question":"","options":["","","",""],"topic":"","difficulty":"easy|medium|hard","source_chunk_id":0}]
"""

_PEDAGOGUE_USER = """Generate {num_questions} unique MCQs on different concepts.
Avoid trivial recall and obvious answers.

KNOWLEDGE:
{knowledge_bricks}

CONTEXT:
{context}

Return Stage A JSON array only."""

_ANSWER_VERIFICATION_SYSTEM = """Verify multiple MCQs against a SOURCE chunk.
Choose exactly one correct answer per question based only on the source.
Return JSON array only:
[{"id":1,"answer":"A","reasoning":""}]
"""

_ANSWER_VERIFICATION_USER = """SOURCE:
{source}

QUESTIONS:
{questions_json}

Return JSON array only."""

_EXPLANATION_GENERATION_SYSTEM = """Write concise explanations for verified answers using the SOURCE.
Explain why the chosen answer is correct.
Return JSON array only:
[{"id":1,"explanation":""}]
"""

_EXPLANATION_GENERATION_USER = """SOURCE:
{source}

QUESTIONS:
{question_answer_json}

Return JSON array only."""

_REPAIR_PROMPT = """Extract ONLY the JSON array of MCQ objects from this text.
Each object needs: id, question, options (4 items), correct_answer (0-3), answer (A-D), explanation, difficulty, topic.
Return ONLY valid JSON array.

TEXT:
{raw}"""


# ── PedagogueAgent ────────────────────────────────────────────────────────────

class PedagogueAgent:
    """Generates candidate MCQs using knowledge bricks and RAG context."""

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
model: str = "qwen3:4b",
        timeout: int = 600,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.llm = llm or LLMProvider(model=model, timeout=timeout)
        self.metrics = metrics

    def _build_prompt(self, knowledge_bricks: str, context: str, num_questions: int) -> str:
        # Issue #3: truncate inputs to reduce prompt tokens
        kb_truncated = knowledge_bricks[:_MAX_KNOWLEDGE_CHARS]
        ctx_truncated = context[:_MAX_CONTEXT_CHARS]
        return _PEDAGOGUE_SYSTEM + "\n\n" + _PEDAGOGUE_USER.format(
            num_questions=num_questions,
            knowledge_bricks=kb_truncated,
            context=ctx_truncated,
        )

    def _parse_questions(self, raw: str) -> List[Dict[str, Any]]:
        """Parse LLM output into a list of question dicts (Stage A format)."""
        parsed = safe_parse_json(raw)
        if parsed is None or not isinstance(parsed, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            q = dict(item)

            if "question" not in q and "text" in q:
                q["question"] = q.pop("text")
            if "question" not in q:
                continue

            options = q.get("options", [])
            if not isinstance(options, list) or len(options) < 2:
                continue
            while len(options) < 4:
                options.append("N/A")
            options = options[:4]
            q["options"] = options

            # Stage A: no answer/explanation yet
            q.pop("correct_answer", None)
            q.pop("answer", None)
            q.pop("explanation", None)
            
            q.setdefault("difficulty", "medium")
            q.setdefault("topic", "General")
            q.setdefault("source_chunk_id", None)

            normalized.append(q)

        return normalized

    def _generate_batch(
        self,
        batch_idx: int,
        batch_count: int,
        knowledge_bricks: str,
        context: str,
        covered_topics: List[str],
        rag_indexer: Optional[RAGIndexer] = None,
    ) -> List[Dict[str, Any]]:
        """Generate a single batch of questions (Stage A only).

        Task #2: Stage A generates question + options only (no answer/explanation).
        """
        diversity_hint = ""
        if covered_topics:
            topics_str = ", ".join(covered_topics[-10:])
            diversity_hint = f"\nALREADY COVERED (skip): {topics_str}"

        prompt = self._build_prompt(
            knowledge_bricks,
            context + diversity_hint,
            batch_count,
        )

        t0 = time.perf_counter()
        raw = self.llm.generate(
            prompt=prompt,
            options={"temperature": 0.4, "num_ctx": 4096},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if self.metrics:
            self.metrics.add_token_usage("pedagogue", prompt, raw)
            self.metrics.record_llm_call("pedagogue", elapsed_ms)

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)

        if not raw:
            logger.warning(f"Pedagogue: Batch {batch_idx+1} returned no response.")
            return []

        (OUTPUT_DIR / f"pedagogue_response_batch{batch_idx+1}.txt").write_text(
            raw, encoding="utf-8"
        )
        questions = self._parse_questions(raw)

        if not questions:
            logger.warning(f"Pedagogue: Batch {batch_idx+1} parse failed, attempting repair...")
            repair_prompt = _REPAIR_PROMPT.format(raw=raw[:6000])
            repair_raw = self.llm.generate(
                prompt=repair_prompt,
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            if repair_raw:
                questions = self._parse_questions(repair_raw)

        logger.info(f"Pedagogue Stage A: Batch {batch_idx+1} → {len(questions)} questions")
        return questions

    def _verify_answers(
        self,
        questions: List[Dict[str, Any]],
        source_chunks: Dict[int, str],
        batch_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Stage B: Verify answers in batches grouped by source chunk.
        
        STRICT MODE: 
        - Requires valid JSON from LLM
        - Retries once with repair prompt if JSON parsing fails
        - Marks question as FAILED if both parsing attempts fail
        - NO heuristic fallbacks
        """
        if not questions:
            return []

        logger.info(f"Pedagogue Stage B: Verifying answers for {len(questions)} questions...")

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for q in questions:
            chunk_id = q.get("source_chunk_id", -1)
            grouped.setdefault(int(chunk_id), []).append(q)

        verified: List[Dict[str, Any]] = []
        failed_ids = set()
        
        for chunk_id, group in grouped.items():
            source = source_chunks.get(chunk_id, "")
            if not source:
                logger.warning(
                    f"Pedagogue Stage B: No source for chunk_id={chunk_id}, rejecting batch"
                )
                for q in group:
                    q["status"] = "FAILED"
                    q["answer"] = None
                    q["answer_reasoning"] = "No source chunk available"
                    failed_ids.add(q.get("id", 0))
                verified.extend(group)
                continue

            for start in range(0, len(group), batch_size):
                batch = group[start : start + batch_size]
                questions_json = []
                for q in batch:
                    questions_json.append({
                        "id": q.get("id", 0),
                        "question": q.get("question", ""),
                        "options": {
                            chr(65 + i): opt for i, opt in enumerate(q.get("options", []))
                        },
                    })

                prompt = _ANSWER_VERIFICATION_SYSTEM + "\n\n" + _ANSWER_VERIFICATION_USER.format(
                    source=source[:2000],
                    questions_json=json.dumps(questions_json, ensure_ascii=False),
                )

                t0 = time.perf_counter()
                raw = self.llm.generate(
                    prompt=prompt,
                    options={"temperature": 0.1, "num_ctx": 2048},
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

                if self.metrics:
                    self.metrics.add_token_usage("pedagogue", prompt, raw)
                    self.metrics.record_llm_call("pedagogue", elapsed_ms)

                # TASK 1: Strict JSON enforcement with retry
                parsed = safe_parse_json(raw)
                if parsed is None or not isinstance(parsed, list):
                    logger.warning(f"Pedagogue Stage B: JSON parse failed for batch, attempting repair...")
                    if self.metrics:
                        self.metrics.metrics.json_parse_failures += 1
                    
                    # Retry once with repair prompt
                    repair_prompt = _REPAIR_PROMPT.format(raw=raw[:4000])
                    repair_raw = self.llm.generate(
                        prompt=repair_prompt,
                        options={"temperature": 0.1, "num_ctx": 2048},
                    )
                    parsed = safe_parse_json(repair_raw)
                    if self.metrics:
                        self.metrics.metrics.repair_attempts += 1
                
                # If still no valid JSON after retry, reject entire batch
                if parsed is None or not isinstance(parsed, list):
                    logger.error(f"Pedagogue Stage B: JSON repair failed, rejecting batch of {len(batch)} questions")
                    for q in batch:
                        q["status"] = "FAILED"
                        q["answer"] = None
                        q["answer_reasoning"] = "Answer verification failed (JSON parse error)"
                        failed_ids.add(q.get("id", 0))
                    verified.extend(batch)
                    continue
                
                # Parse successful — extract answers
                answer_map = {}
                for item in parsed:
                    if isinstance(item, dict) and "id" in item:
                        answer_map[int(item["id"])] = item

                for q in batch:
                    q_id = q.get("id", 0)
                    item = answer_map.get(q_id)
                    if item:
                        answer = str(item.get("answer", "")).strip().upper()
                        if answer in "ABCD":
                            q["status"] = "VERIFIED"
                            q["answer"] = answer
                            q["correct_answer"] = ord(answer) - 65
                            q["answer_reasoning"] = str(item.get("reasoning", ""))
                        else:
                            q["status"] = "FAILED"
                            q["answer"] = None
                            q["answer_reasoning"] = f"Invalid answer format: {answer}"
                            failed_ids.add(q_id)
                    else:
                        q["status"] = "FAILED"
                        q["answer"] = None
                        q["answer_reasoning"] = "No answer provided by verifier"
                        failed_ids.add(q_id)

                verified.extend(batch)

        logger.info(f"Pedagogue Stage B: {len(failed_ids)} questions failed verification")
        if self.metrics:
            self.metrics.metrics.answer_consistency_failures += len(failed_ids)
            
        return verified

    def _generate_explanations(
        self,
        questions: List[Dict[str, Any]],
        source_chunks: Dict[int, str],
        batch_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Stage C: Generate explanations in batches grouped by source chunk.
        
        STRICT MODE:
        - Requires valid JSON from LLM
        - Retries once with repair prompt if parsing fails
        - Marks question as FAILED if explanation missing or unparseable
        - NO placeholder explanations
        """
        if not questions:
            return []

        logger.info(f"Pedagogue Stage C: Generating explanations for {len(questions)} questions...")

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for q in questions:
            chunk_id = q.get("source_chunk_id", -1)
            grouped.setdefault(int(chunk_id), []).append(q)

        with_explanations: List[Dict[str, Any]] = []
        failed_ids = set()
        
        for chunk_id, group in grouped.items():
            source = source_chunks.get(chunk_id, "")
            if not source:
                logger.warning(f"Pedagogue Stage C: No source for chunk_id={chunk_id}, rejecting batch")
                for q in group:
                    q["status"] = "FAILED"
                    q["explanation"] = None
                    failed_ids.add(q.get("id", 0))
                with_explanations.extend(group)
                continue

            for start in range(0, len(group), batch_size):
                batch = group[start : start + batch_size]
                
                # Only process questions that have verified answers
                question_answer_json = []
                for q in batch:
                    if q.get("status") != "VERIFIED" or "answer" not in q or not q.get("answer"):
                        q["status"] = "FAILED"
                        q["explanation"] = None
                        failed_ids.add(q.get("id", 0))
                        continue
                    question_answer_json.append({
                        "id": q.get("id", 0),
                        "question": q.get("question", ""),
                        "options": {
                            chr(65 + i): opt for i, opt in enumerate(q.get("options", []))
                        },
                        "answer": q.get("answer", "A"),
                    })

                if not question_answer_json:
                    for q in batch:
                        if q.get("status") != "FAILED":
                            q["status"] = "FAILED"
                            q["explanation"] = None
                    with_explanations.extend(batch)
                    continue

                prompt = _EXPLANATION_GENERATION_SYSTEM + "\n\n" + _EXPLANATION_GENERATION_USER.format(
                    source=source[:2000],
                    question_answer_json=json.dumps(question_answer_json, ensure_ascii=False),
                )

                t0 = time.perf_counter()
                raw = self.llm.generate(
                    prompt=prompt,
                    options={"temperature": 0.2, "num_ctx": 2048},
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

                if self.metrics:
                    self.metrics.add_token_usage("pedagogue", prompt, raw)
                    self.metrics.record_llm_call("pedagogue", elapsed_ms)

                # TASK 1: Strict JSON enforcement with retry
                parsed = safe_parse_json(raw)
                if parsed is None or not isinstance(parsed, list):
                    logger.warning(f"Pedagogue Stage C: JSON parse failed, attempting repair...")
                    if self.metrics:
                        self.metrics.metrics.json_parse_failures += 1
                    
                    repair_prompt = _REPAIR_PROMPT.format(raw=raw[:4000])
                    repair_raw = self.llm.generate(
                        prompt=repair_prompt,
                        options={"temperature": 0.1, "num_ctx": 2048},
                    )
                    parsed = safe_parse_json(repair_raw)
                    if self.metrics:
                        self.metrics.metrics.repair_attempts += 1
                
                # If still no valid JSON, reject batch
                if parsed is None or not isinstance(parsed, list):
                    logger.error(f"Pedagogue Stage C: JSON repair failed, rejecting batch")
                    for q in question_answer_json:
                        q_id = q.get("id", 0)
                        q["status"] = "FAILED"
                        q["explanation"] = None
                        failed_ids.add(q_id)
                    for q in batch:
                        if "explanation" not in q:
                            q["status"] = "FAILED"
                            q["explanation"] = None
                    with_explanations.extend(batch)
                    continue
                
                # Parse successful — extract explanations
                explanation_map = {}
                for item in parsed:
                    if isinstance(item, dict) and "id" in item:
                        explanation_map[int(item["id"])] = item

                for q in batch:
                    q_id = q.get("id", 0)
                    if q_id not in explanation_map:
                        q["status"] = "FAILED"
                        q["explanation"] = None
                        failed_ids.add(q_id)
                        continue
                    
                    item = explanation_map[q_id]
                    explanation = str(item.get("explanation", "")).strip()
                    
                    # TASK 5: Reject if explanation missing or is placeholder
                    if not explanation or "could not be generated" in explanation.lower() or len(explanation) < 20:
                        q["status"] = "FAILED"
                        q["explanation"] = None
                        failed_ids.add(q_id)
                        logger.warning(f"Question {q_id}: Empty or placeholder explanation rejected")
                    else:
                        q["status"] = "VERIFIED"
                        q["explanation"] = explanation

                with_explanations.extend(batch)

        logger.info(f"Pedagogue Stage C: {len(failed_ids)} questions failed explanation generation")
        if self.metrics:
            self.metrics.metrics.explanation_consistency_failures += len(failed_ids)
            
        return with_explanations

    def generate_quiz(
        self,
        knowledge_bricks: str,
        output_path: Optional[str] = None,
        num_questions: int = 20,
        rag_indexer: Optional[RAGIndexer] = None,
        candidate_multiplier: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """Generate N×candidate_multiplier candidate questions using three-stage approach.

        Task #2: Three-stage generation reduces hallucination:
          Stage A: Generate question + options (parallel)
          Stage B: Verify answers independently (parallel)
          Stage C: Generate explanations (parallel)

        Args:
            knowledge_bricks: Markdown string from CuratorAgent.
            output_path: Optional path to save Markdown output.
            num_questions: Target number of final questions.
            rag_indexer: RAG index for retrieving source chunks per question.
            candidate_multiplier: Candidates per final question.

        Returns:
            List of candidate question dicts with answers and explanations.
        """
        if self.metrics:
            self.metrics.start_timer("pedagogue")

        if not self.llm.is_available():
            logger.error("Pedagogue: Ollama is not running.")
            if self.metrics:
                self.metrics.stop_timer("pedagogue")
            return []

        num_candidates = int(num_questions * candidate_multiplier)
        logger.info(
            f"Pedagogue: Generating {num_candidates} candidates "
            f"(target={num_questions}, multiplier={candidate_multiplier}x) in three stages..."
        )

        # Get context for Stage A
        context = ""
        if rag_indexer is not None:
            context = rag_indexer.retrieve_for_topic(
                "key concepts definitions formulas", top_k=3
            )

        # ──── STAGE A: Parallel question generation ────────────────────────────
        batch_size = 5
        batches = []
        remaining = num_candidates
        batch_idx = 0
        while remaining > 0:
            count = min(batch_size, remaining)
            batches.append((batch_idx, count))
            remaining -= count
            batch_idx += 1

        logger.info(f"Pedagogue Stage A: {len(batches)} batches of ≤{batch_size} questions")

        all_questions: List[Dict[str, Any]] = []
        covered_topics: List[str] = []

        max_workers = min(len(batches), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    self._generate_batch,
                    idx,
                    count,
                    knowledge_bricks,
                    context,
                    list(covered_topics),
                    rag_indexer,
                ): idx
                for idx, count in batches
            }

            for future in as_completed(future_to_idx):
                try:
                    questions = future.result()
                    all_questions.extend(questions)
                    for q in questions:
                        t = q.get("topic", "").strip()
                        if t and t not in covered_topics:
                            covered_topics.append(t)
                except Exception as exc:
                    logger.error(f"Pedagogue Stage A: Batch failed: {exc}")

        # Deduplicate and re-number
        all_questions = self._deduplicate_questions(all_questions)
        for i, q in enumerate(all_questions):
            q["id"] = i + 1

        logger.info(f"Pedagogue Stage A complete: {len(all_questions)} unique questions")

        if not all_questions:
            logger.error("Pedagogue: No questions generated in Stage A")
            if self.metrics:
                self.metrics.stop_timer("pedagogue")
            return []

        # ──── Retrieve source chunks for each question ────────────────────────
        source_chunks_by_id: Dict[int, str] = {}
        retrieval_cache: Dict[str, List[tuple]] = {}

        if rag_indexer:
            for q in all_questions:
                topic = q.get("topic", "").strip() or q.get("question", "")[:100]
                query = topic
                if query not in retrieval_cache:
                    retrieval_cache[query] = rag_indexer.retrieve_with_ids(query, top_k=1)

                chunk_results = retrieval_cache[query]
                if chunk_results:
                    chunk_id, source = chunk_results[0]
                    chunk_id = int(chunk_id)
                    q["source_chunk_id"] = chunk_id
                    q["source_excerpt"] = source[:200]
                    source_chunks_by_id.setdefault(chunk_id, source)
                else:
                    q["source_chunk_id"] = -1
                    q["source_excerpt"] = ""
                    source_chunks_by_id.setdefault(-1, knowledge_bricks[:500])
        else:
            for q in all_questions:
                q["source_chunk_id"] = -1
                q["source_excerpt"] = ""
                source_chunks_by_id.setdefault(-1, knowledge_bricks[:500])

        # ──── STAGE B: Parallel answer verification ──────────────────────────
        logger.info("Pedagogue Stage B: Verifying answers...")
        all_questions = self._verify_answers(all_questions, source_chunks_by_id, batch_size=10)

        # ──── STAGE C: Parallel explanation generation ────────────────────────
        logger.info("Pedagogue Stage C: Generating explanations...")
        all_questions = self._generate_explanations(all_questions, source_chunks_by_id)

        # Save Stage A+B+C output
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "pedagogue_candidates.json").write_text(
            json.dumps(all_questions, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(f"Pedagogue: {len(all_questions)} candidates (Stages A+B+C complete)")

        if self.metrics:
            self.metrics.stop_timer("pedagogue")
            self.metrics.metrics.candidates_generated = len(all_questions)

        if all_questions and output_path:
            self.save_as_markdown(all_questions, output_path)

        return all_questions

    def _deduplicate_questions(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove near-duplicate questions by normalized question text."""
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for q in questions:
            key = re.sub(r"[^a-z0-9 ]", "", q.get("question", "").lower())[:80]
            if key and key not in seen:
                seen.add(key)
                unique.append(q)
        return unique

    def save_as_markdown(self, quiz_data: List[Dict[str, Any]], output_path: str) -> None:
        """Save quiz to Markdown file."""
        md_content = "# Generated Quiz\n\n"

        for i, q in enumerate(quiz_data, 1):
            if not isinstance(q, dict):
                continue

            question = q.get("question", "N/A")
            options = q.get("options", [])
            answer = q.get("answer", "N/A")
            explanation = q.get("explanation", "N/A")
            difficulty = q.get("difficulty", "")
            topic = q.get("topic", "")
            score = q.get("adversary_score", None)

            header = f"### Question {i}"
            if difficulty:
                header += f" `{difficulty}`"
            if topic:
                header += f" — {topic}"
            if score is not None:
                header += f" (score: {score}/100)"

            md_content += f"{header}\n{question}\n\n"

            for idx, opt in enumerate(options if isinstance(options, list) else []):
                label = chr(65 + idx)
                clean_opt = re.sub(r"^([A-D][.)]\s*)", "", str(opt)).strip()
                md_content += f"- **{label}**) {clean_opt}\n\n"

            md_content += f"\n> **Correct Answer:** {str(answer).upper()}\n"
            explanation_formatted = "\n> ".join(
                explanation.replace("\r\n", "\n").split("\n")
            )
            md_content += f"> **Explanation:** {explanation_formatted}\n\n---\n\n"

        md_content = clean_markdown_output(md_content)
        Path(output_path).write_text(md_content, encoding="utf-8")
