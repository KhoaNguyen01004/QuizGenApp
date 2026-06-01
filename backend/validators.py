"""Answer Consistency Checker — Task #6.

Validates that every question meets strict criteria:
1. Answer is supported by explanation
2. Answer is supported by source chunk
3. Exactly one correct answer (no ambiguity)
4. No multiple correct options
5. Explanation aligns with answer
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class AnswerConsistencyValidator:
    """Validates question-answer-explanation-source consistency."""

    def __init__(self, strict: bool = True):
        """
        Args:
            strict: If True, reject on any warning. If False, accept if major rules pass.
        """
        self.strict = strict
        self.failures: Dict[str, int] = {
            "answer_not_in_options": 0,
            "explanation_mismatch": 0,
            "source_mismatch": 0,
            "ambiguous_answer": 0,
            "unsupported_claim": 0,
        }

    def validate(
        self,
        question: Dict[str, Any],
        source_chunk: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Validate a single question.

        Args:
            question: Dict with question, options, answer, explanation, correct_answer.
            source_chunk: Source text that should support the answer.

        Returns:
            (passed: bool, reason: str)
        """
        checks = [
            self._check_answer_in_options(question),
            self._check_unique_answer(question),
            self._check_explanation_format(question),
        ]

        if source_chunk:
            checks.append(self._check_source_support(question, source_chunk))
            checks.append(self._check_explanation_source_alignment(question, source_chunk))

        # Aggregate results
        all_passed = all(passed for passed, _ in checks)
        reasons = [reason for _, reason in checks if reason]

        if self.strict:
            return all_passed, " | ".join(reasons) if reasons else "PASS"
        else:
            # In lenient mode, fail only on critical issues
            critical = any(
                "must have exactly" in reason or "answer_text not found" in reason
                for _, reason in checks
            )
            return not critical, " | ".join(reasons) if reasons else "PASS"

    def _check_answer_in_options(self, q: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify that the marked answer exists in options."""
        options = q.get("options", [])
        answer = q.get("answer", "").strip().upper()
        correct_answer_idx = q.get("correct_answer", 0)

        if not isinstance(correct_answer_idx, int) or correct_answer_idx < 0 or correct_answer_idx >= len(options):
            self.failures["answer_not_in_options"] += 1
            return False, f"correct_answer index {correct_answer_idx} out of range (only {len(options)} options)"

        if answer not in "ABCD":
            self.failures["answer_not_in_options"] += 1
            return False, f"answer '{answer}' not in ABCD"

        expected_answer = chr(65 + correct_answer_idx)
        if answer != expected_answer:
            self.failures["answer_not_in_options"] += 1
            return False, f"answer mismatch: {answer} vs index {correct_answer_idx} ({expected_answer})"

        return True, ""

    def _check_unique_answer(self, q: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify exactly one correct answer (no ambiguity)."""
        options = q.get("options", [])
        correct_answer_idx = q.get("correct_answer", 0)

        if len(options) < 4:
            self.failures["ambiguous_answer"] += 1
            return False, f"question has only {len(options)} options (need 4)"

        # Check for duplicate options (potential ambiguity)
        unique_options = set(str(opt).lower().strip() for opt in options)
        if len(unique_options) < len(options):
            self.failures["ambiguous_answer"] += 1
            return False, "duplicate options detected (ambiguous question)"

        return True, ""

    def _check_explanation_format(self, q: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify explanation exists and is non-trivial."""
        explanation = q.get("explanation", "").strip()

        if not explanation or len(explanation) < 10:
            self.failures["explanation_mismatch"] += 1
            return False, "explanation missing or too short"

        # Check for placeholder text
        if "placeholder" in explanation.lower() or "..." in explanation:
            self.failures["explanation_mismatch"] += 1
            return False, "explanation looks like placeholder"

        return True, ""

    def _check_source_support(self, q: Dict[str, Any], source: str) -> Tuple[bool, str]:
        """Verify that source chunk contains key concepts from the question and answer."""
        question_text = q.get("question", "").lower()
        options = q.get("options", [])
        answer_idx = q.get("correct_answer", 0)

        if answer_idx >= len(options):
            return False, "answer index out of range"

        answer_text = str(options[answer_idx]).lower()
        source_lower = source.lower()

        # Extract key terms (words longer than 4 chars)
        q_terms = set(re.findall(r"\b\w{4,}\b", question_text))
        a_terms = set(re.findall(r"\b\w{4,}\b", answer_text))
        combined_terms = q_terms | a_terms

        if not combined_terms:
            return True, ""  # No key terms to verify

        # Check overlap with source
        matched = sum(1 for term in combined_terms if term in source_lower)
        coverage = matched / len(combined_terms) if combined_terms else 0

        if coverage < 0.3:  # At least 30% key terms should be in source
            self.failures["source_mismatch"] += 1
            return False, f"low source coverage ({coverage:.0%}): answer may not be in source"

        return True, ""

    def _check_explanation_source_alignment(self, q: Dict[str, Any], source: str) -> Tuple[bool, str]:
        """Verify explanation aligns with source and supports the answer."""
        explanation = q.get("explanation", "").lower()
        options = q.get("options", [])
        answer_idx = q.get("correct_answer", 0)

        if answer_idx >= len(options):
            return False, "answer index out of range"

        answer_text = str(options[answer_idx]).lower()
        source_lower = source.lower()

        # Extract key terms from answer
        answer_terms = set(re.findall(r"\b\w{4,}\b", answer_text))

        # Check if explanation contains answer concepts
        matched_in_explanation = sum(1 for term in answer_terms if term in explanation)
        if matched_in_explanation < len(answer_terms) * 0.3:  # At least 30% answer terms in explanation
            self.failures["explanation_mismatch"] += 1
            return False, f"explanation may not support answer: only {matched_in_explanation}/{len(answer_terms)} answer terms found"

        # Check if explanation is sourced from the provided text
        explanation_terms = set(re.findall(r"\b\w{4,}\b", explanation))
        matched_in_source = sum(1 for term in explanation_terms if term in source_lower)

        if len(explanation_terms) > 0:
            source_coverage = matched_in_source / len(explanation_terms)
            if source_coverage < 0.4:  # At least 40% explanation terms should be in source
                self.failures["unsupported_claim"] += 1
                return False, f"explanation may contain unsupported claims ({source_coverage:.0%} source coverage)"

        return True, ""

    def validate_batch(
        self,
        questions: list,
        source_chunks: Optional[Dict[int, str]] = None,
    ) -> Tuple[list, list]:
        """Validate a batch of questions.

        Args:
            questions: List of question dicts.
            source_chunks: Dict mapping question id to source text.

        Returns:
            (passed_questions: list, rejected_questions: list)
        """
        passed = []
        rejected = []

        for q in questions:
            q_id = q.get("id", 0)
            source = source_chunks.get(q_id) if source_chunks else None

            is_valid, reason = self.validate(q, source)

            if is_valid:
                q["validation_status"] = "PASS"
                q["validation_notes"] = ""
                passed.append(q)
            else:
                q["validation_status"] = "FAIL"
                q["validation_notes"] = reason
                rejected.append(q)
                logger.warning(f"Question {q_id} rejected: {reason}")

        logger.info(
            f"Validation results: {len(passed)} passed, {len(rejected)} rejected. "
            f"Failures: {self.failures}"
        )
        return passed, rejected

    def get_failure_report(self) -> Dict[str, int]:
        """Return summary of validation failures."""
        return dict(self.failures)

    def reset_failures(self):
        """Reset failure counters."""
        self.failures = {k: 0 for k in self.failures}
