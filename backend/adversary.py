import concurrent.futures
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ollama

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class AdversaryAgent:
    """Phase 3: Validation / Fact-checking.

    Receives quiz_data from Pedagogue + knowledge_bricks (source).
    Validates each question's answer by checking support from knowledge_bricks.
    If an answer seems unsupported, flags it and may attempt a correction.
    """

    def __init__(self, model: str = "llama3.2:3b", timeout: int = 600, use_gpu: bool = True):
        self.model = model
        self.timeout = timeout
        self.use_gpu = use_gpu
        self._log_gpu_status()

    def _log_gpu_status(self):
        try:
            info = ollama.ps()
            gpu_info = "GPU support unknown"

            has_models = False
            if hasattr(info, "models") and info.models:
                has_models = True
            elif isinstance(info, (list, dict)) and len(info) > 0:
                has_models = True

            if has_models:
                gpu_info = "Ollama running (GPU support depends on installation)"
            logging.info(f"Ollama GPU status: {gpu_info}")
        except Exception as e:
            logging.warning(f"Could not check Ollama GPU status: {e}")

    def _run_with_timeout(self, fn, *args, timeout: int = 600, **kwargs):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logging.error("Ollama request timed out after %s seconds.", timeout)
                return None
            except Exception as exc:
                logging.error("Ollama request failed: %s", exc)
                return None

    def _check_ollama(self) -> bool:
        try:
            ollama.list()
            return True
        except Exception:
            return False

    def _normalize_space(self, s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip()

    def _extract_letter_answer(self, answer: str) -> str:
        a = (answer or "").strip().upper()
        # Expect formats like "A", "B", "C", "D"
        m = re.match(r"^([ABCD])\b", a)
        if m:
            return m.group(1)
        return a[:1] if a else ""

    def _letter_to_option_map(self, options: Any) -> Dict[str, str]:
        # options may be list like ["A) ...", "B) ..."] or ["A. ..."] etc
        # We'll index by first occurrence of A/B/C/D.
        mapping: Dict[str, str] = {"A": "", "B": "", "C": "", "D": ""}
        if not isinstance(options, list):
            return mapping

        for opt in options:
            opt_str = str(opt)
            opt_str_norm = opt_str.strip()
            m = re.match(r"^\s*([ABCD])[\)\.]\s*(.*)$", opt_str_norm, flags=re.IGNORECASE)
            if m:
                letter = m.group(1).upper()
                mapping[letter] = m.group(2).strip()
            else:
                # Try generic: if contains "A)" somewhere
                m2 = re.search(r"\b([ABCD])[\)\.]\b\s*(.*)$", opt_str_norm, flags=re.IGNORECASE)
                if m2:
                    letter = m2.group(1).upper()
                    mapping[letter] = m2.group(2).strip()

        return mapping

    def _quick_support_score(self, knowledge_bricks: str, candidate: str) -> int:
        """Lightweight heuristic: counts overlapping normalized tokens."""
        kb = self._normalize_space(knowledge_bricks).lower()
        cand = self._normalize_space(candidate).lower()
        if not cand:
            return 0

        # Remove LaTeX wrappers for heuristic tokenization
        kb_clean = re.sub(r"\$[^\$]*\$", " ", kb)
        cand_clean = re.sub(r"\$[^\$]*\$", " ", cand)

        cand_tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", cand_clean) if len(t) >= 4]
        if not cand_tokens:
            return 0

        score = 0
        for t in set(cand_tokens):
            if t in kb_clean:
                score += 1
        return score

    def validate_quiz(
        self,
        knowledge_bricks: str,
        quiz_data: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns validated quiz JSON array.

        Adds fields per question:
          - adversary_flag: bool
          - validation_notes: str
          - answer_corrected (optional): str (letter)
        """

        if not quiz_data:
            return []

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)

        # First: deterministic heuristic pass
        validated: List[Dict[str, Any]] = []
        any_uncertain = False

        for idx, q in enumerate(quiz_data):
            if not isinstance(q, dict):
                continue

            answer_letter = self._extract_letter_answer(str(q.get("answer", "")))
            options = q.get("options", [])
            opt_map = self._letter_to_option_map(options)
            candidate_text = opt_map.get(answer_letter, "")

            score = self._quick_support_score(knowledge_bricks, f"{q.get('question','')} {candidate_text}")

            # Threshold: if there are almost no overlaps, ask model.
            adversary_flag = score < 2
            if adversary_flag:
                any_uncertain = True

            notes = (
                "Heuristic check: answer appears unsupported by knowledge bricks; flagged for review."
                if adversary_flag
                else "Heuristic check: answer seems supported by knowledge bricks."
            )

            q2 = dict(q)
            q2["adversary_flag"] = adversary_flag
            q2["validation_notes"] = notes
            validated.append(q2)

        # Second: model pass only for uncertain items
        if any_uncertain and self._check_ollama():
            num_gpu = -1 if self.use_gpu else 0
            
            for i, q in enumerate(validated):
                if not q.get("adversary_flag", False):
                    continue

                prompt = f"""
[SYSTEM: ADVERSARY VALIDATOR]
You must fact-check the given MCQ using ONLY the provided Knowledge Bricks.
If the current answer letter is unsupported or contradicts the Knowledge Bricks, choose the best supported option letter.
Return ONLY valid JSON with this schema:
{{"flagged": true/false, "best_answer": "A"/"B"/"C"/"D", "notes": "..."}}

IMPORTANT LATEX AND FORMAT RULES:
- Use the Knowledge Bricks as ground truth.
- If none of the options are supported, set flagged=true and best_answer to the closest supported option (or keep original if equally unsupported).
- Return ONLY valid JSON that can be parsed by JSON.parse() (NO markdown code blocks, NO extra text).
- LATEX SAFETY RULES: Use ONLY valid KaTeX commands. NEVER invent, truncate, or hallucinate LaTeX commands (e.g., NO \\ullet, \\ext, \\heta). ONLY use standard operators like \\cdot, \\sin, \\cos, \\theta, \\frac, etc.
- All mathematical expressions MUST use KaTeX-compatible LaTeX, wrap inline math with $...$, and be on a SINGLE LINE.
- DO NOT break down equations into multiple lines (NO OCR-style formatting).
- Notes text must be clean, markdown-safe, without random line breaks or decorative emojis.


Knowledge Bricks:
{knowledge_bricks}

Question:
{q.get('question','')}

Options:
A) {self._letter_to_option_map(q.get('options', []))['A']}
B) {self._letter_to_option_map(q.get('options', []))['B']}
C) {self._letter_to_option_map(q.get('options', []))['C']}
D) {self._letter_to_option_map(q.get('options', []))['D']}

Current answer: {self._extract_letter_answer(str(q.get('answer', '')))}
                """.strip()

                logging.info(f"Adversary validating question {i+1}/{len(validated)}...")

                resp = self._run_with_timeout(
                    ollama.generate,
                    model=self.model,
                    prompt=prompt,
                    options={"num_ctx": 4096, "num_gpu": num_gpu},
                    format="json",
                    timeout=self.timeout,
                )

                raw = ""
                parsed: Optional[Dict[str, Any]] = None
                if resp is None:
                    continue
                if isinstance(resp, dict):
                    raw = resp.get("response", "") or ""
                else:
                    raw = getattr(resp, "response", "") or ""

                (OUTPUT_DIR / f"adversary_response_q{i+1}.txt").write_text(raw, encoding="utf-8")

                # Extract JSON object if needed
                raw_clean = raw.strip()
                
                def _sanitize_invalid_json_escapes(s: str) -> str:
                    out: List[str] = []
                    i = 0
                    valid_after = {'"', '\\', '/', 'n', 'r', 'u'}
                    n = len(s)
                    while i < n:
                        ch = s[i]
                        if ch == "\\" and i + 1 < n:
                            nxt = s[i + 1]
                            if nxt == 'u':
                                if i + 5 < n and all(c in '0123456789abcdefABCDEF' for c in s[i + 2 : i + 6]):
                                    out.append('\\u' + s[i + 2 : i + 6])
                                    i += 6
                                    continue
                            if nxt in valid_after:
                                out.append('\\' + nxt)
                                i += 2
                                continue
                            out.append('\\\\' + nxt)
                            i += 2
                            continue
                        out.append(ch)
                        i += 1
                    return ''.join(out)

                raw_clean = _sanitize_invalid_json_escapes(raw_clean)
                
                try:
                    parsed = json.loads(raw_clean)
                except Exception:
                    # try to locate first { ... }
                    m = re.search(r"\{[\s\S]*\}", raw_clean)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                        except Exception:
                            parsed = None

                if not parsed or not isinstance(parsed, dict):
                    continue

                flagged = bool(parsed.get("flagged", True))
                best_answer = str(parsed.get("best_answer", self._extract_letter_answer(str(q.get("answer", ""))))).strip().upper()
                best_answer = self._extract_letter_answer(best_answer)
                notes = str(parsed.get("notes", ""))

                q["adversary_flag"] = flagged
                q["validation_notes"] = notes
                if best_answer and best_answer != self._extract_letter_answer(str(q.get("answer", ""))):
                    q["answer_corrected"] = best_answer
                    q["answer"] = best_answer

        if output_path:
            Path(output_path).write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")

        return validated
