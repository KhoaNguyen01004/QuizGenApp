# import concurrent.futures

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama

from backend.utils.markdown_cleaner import clean_markdown_output


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class PedagogueAgent:

    def __init__(self, model: str = "llama3.2:3b", timeout: int = 180):
        self.model = model
        self.timeout = timeout
        self._log_gpu_status()

    def _log_gpu_status(self):
        """Log GPU availability for Ollama."""
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

    def _run_with_timeout(self, fn, *args, timeout: int = 180, **kwargs):
        """Thread-based timeout wrapper."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logging.error("Ollama request timed out after %s seconds (timeout).", timeout)
                return None
            except Exception as exc:
                logging.error("Ollama request failed: %s", exc)
                return None

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            ollama.list()
            return True
        except Exception:
            return False

    def _extract_last_json_array(self, text: str) -> Optional[str]:
        """Extract the last complete top-level JSON array from arbitrary text.

        This is a best-effort bracket matcher that tracks whether we're inside
        strings and escapes.
        """
        s = text.strip()
        if not s:
            return None

        last = None
        start = None
        depth = 0
        in_string = False
        escape = False

        for i, c in enumerate(s):
            if c == '"' and not escape:
                in_string = not in_string
            if in_string:
                escape = (c == "\\") and not escape
                continue

            if c == '[':
                if depth == 0:
                    start = i
                depth += 1
            elif c == ']':
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        candidate = s[start : i + 1].strip()
                        last = candidate
                        start = None

            escape = (c == "\\") and not escape

        return last

    def _parse_json(self, text: str) -> List[Dict[str, Any]]:
        """Parse Pedagogue output into a list of question objects."""
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)

        cleaned = text.replace("```json", "").replace("```", "")
        candidate = self._extract_last_json_array(cleaned)

        (OUTPUT_DIR / "raw_extracted_pedagogue.json").write_text(
            candidate or "", encoding="utf-8"
        )

        if not candidate:
            logging.error("Parsing failed: no valid JSON array found in response.")
            return []

        repaired = candidate

        # 1) Normalize backslash + newline/carriage returns into literal "\\n".
        # This fixes cases where the model emits an actual newline inside a JSON string,
        # preceded by a backslash.
        repaired = repaired.replace("\\\r\n", "\\\\n")
        repaired = repaired.replace("\\\n", "\\\\n")
        repaired = repaired.replace("\\\r", "\\\\n")

        # 2) Sanitize invalid backslash escapes ("\\x", "\\(", "\\c", etc.).
        # Valid JSON string escapes: \" , \\\ , \/ , \b , \f , \n , \r , \t , \uXXXX.
        def _sanitize_invalid_json_escapes(s: str) -> str:
            out: List[str] = []
            i = 0
            valid_after = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}
            n = len(s)
            while i < n:
                ch = s[i]
                if ch == "\\" and i + 1 < n:
                    nxt = s[i + 1]

                    # Keep valid \uXXXX sequences
                    if nxt == 'u':
                        if i + 5 < n and all(c in '0123456789abcdefABCDEF' for c in s[i + 2 : i + 6]):
                            out.append('\\u' + s[i + 2 : i + 6])
                            i += 6
                            continue

                    if nxt in valid_after:
                        out.append('\\' + nxt)
                        i += 2
                        continue

                    # Invalid escape: escape the backslash itself.
                    out.append('\\\\' + nxt)
                    i += 2
                    continue

                out.append(ch)
                i += 1

            return ''.join(out)

        repaired_sanitized = _sanitize_invalid_json_escapes(repaired)

        try:
            parsed = json.loads(repaired_sanitized)
        except json.JSONDecodeError as e:
            logging.error("Parsing failed: JSON decode error: %s", e)
            (OUTPUT_DIR / "pedagogue_json_repair_failed.txt").write_text(
                repaired_sanitized[:20000], encoding="utf-8"
            )
            return []

        # Must be list of dicts
        if not isinstance(parsed, list):
            logging.error("Parsing failed: JSON is not a list/array.")
            return []

        if not parsed:
            logging.warning("Parsing failed: JSON array is empty.")
            return []

        if not all(isinstance(x, dict) for x in parsed):
            types = [type(x).__name__ for x in parsed[:5]]
            logging.error(
                "Parsing failed: array items are not objects. Item types (first 5): %s",
                types,
            )
            return []

        # Normalize fields
        normalized: List[Dict[str, Any]] = []
        for item in parsed:
            q = dict(item)
            if "explanation" not in q:
                q["explanation"] = "No explanation provided."
            if "question" not in q and "text" in q:
                q["question"] = q["text"]
            normalized.append(q)

        (OUTPUT_DIR / "cleaned_pedagogue.json").write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return normalized

    def save_as_markdown(self, quiz_data: List[Dict[str, Any]], output_path: str) -> None:
        md_content = "# Generated Quiz\n\n"

        for i, q in enumerate(quiz_data, 1):
            if not isinstance(q, dict):
                md_content += f"### Question {i}\nN/A\n\n"
                continue

            question = q.get("question", "N/A")
            options = q.get("options", [])
            answer = q.get("answer", "N/A")
            explanation = q.get("explanation", "N/A")

            md_content += f"### Question {i}\n{question}\n\n"

            for idx, opt in enumerate(options if isinstance(options, list) else []):
                label = chr(65 + idx)
                clean_opt = re.sub(r"^([A-D][\.])\\s*", "", str(opt)).strip()
                md_content += f"- **{label}**) {clean_opt}\n"

            md_content += f"\n> **Correct Answer:** {str(answer).upper()}\n"
            md_content += f"> **Explanation:** {explanation}\n\n---\n\n"

        def _fix_tex_wrapping(s: str) -> str:
            if not isinstance(s, str):
                return s
            if "\\\\" in s and "$" not in s:
                return f"${s}$"
            return s

        md_content_fixed = re.sub(
            r"(> \*\*Explanation:\*\* )(.*?)(\\n\\n---\\n)",
            lambda m: m.group(1) + _fix_tex_wrapping(m.group(2)) + m.group(3),
            md_content,
            flags=re.DOTALL,
        )
        md_content_fixed = _fix_tex_wrapping(md_content_fixed)

        md_content_fixed = clean_markdown_output(md_content_fixed)
        Path(output_path).write_text(md_content_fixed, encoding="utf-8")

    def generate_quiz(
        self,
        knowledge_bricks: str,
        output_path: Optional[str] = None,
        num_questions: int = 5,
    ) -> List[Dict[str, Any]]:
        prompt = f"""[SYSTEM: PEDAGOGUE]
Generate {num_questions} MCQs from ONLY these knowledge bricks.

Return ONLY a single JSON array (no extra text). No markdown, no code fences, no commentary.

Each array item MUST be exactly this JSON object schema:
{{
  "question": "...",
  "options": ["A) ...","B) ...","C) ...","D) ..."],
  "answer": "A|B|C|D",
  "explanation": "..."
}}

Rules:
- Exactly 4 options per question.
- Exactly one correct answer (letter A-D in "answer").
- Use LaTeX for math ONLY.
- Double escape backslashes in LaTeX: \\\\cos \\\\theta
- Output must be valid JSON that can be parsed directly.

KNOWLEDGE:
{knowledge_bricks}
"""

        if not self._check_ollama():
            logging.error(
                "Ollama is not running or accessible. Please start Ollama and ensure the model is available."
            )
            return []

        response = self._run_with_timeout(
            ollama.generate,
            model=self.model,
            prompt=prompt,
            keep_alive=0,
            options={"temperature": 0.1, "num_ctx": 2048, "num_gpu": 0},
            timeout=self.timeout,
        )

        if response is None:
            return []

        raw_response = (
            response.get("response", "")
            if isinstance(response, dict)
            else getattr(response, "response", "")
        )

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "pedagogue_response.txt").write_text(raw_response, encoding="utf-8")

        quiz_data = self._parse_json(raw_response)

        # One repair attempt: force JSON-only again
        if not quiz_data:
            repair_prompt = (
                "Return ONLY the JSON array of question objects. "
                "Do not output any other text. "
                "If you cannot, return [].\n\n"
                "SCHEMA REMINDER: "
                "[{\"question\":...,\"options\":[...4 items...],\"answer\":\"A\",\"explanation\":...}, ...]\n\n"
                "ARBITRARY MODEL OUTPUT (extract JSON from it):\n"
                + raw_response
            )

            repair_resp = self._run_with_timeout(
                ollama.generate,
                model=self.model,
                prompt=repair_prompt,
                keep_alive=0,
                options={"temperature": 0.1, "num_ctx": 2048, "num_gpu": 0},
                timeout=min(60, self.timeout),
            )

            if repair_resp is not None:
                repaired = (
                    repair_resp.get("response", "")
                    if isinstance(repair_resp, dict)
                    else getattr(repair_resp, "response", "")
                )
                (OUTPUT_DIR / "pedagogue_response_repair.txt").write_text(repaired, encoding="utf-8")
                quiz_data = self._parse_json(repaired)

        if quiz_data and len(quiz_data) > num_questions:
            quiz_data = quiz_data[:num_questions]

        if quiz_data and output_path:
            self.save_as_markdown(quiz_data, output_path)

        return quiz_data

