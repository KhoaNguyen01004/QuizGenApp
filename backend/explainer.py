import concurrent.futures
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class ExplainerAgent:
    """Phase 4: Reasoning / Explanation.

    Receives validated quiz.
    For each question, generates exactly 2-sentence explanation using Knowledge Bricks.

    LaTeX constraint:
    - wrap math symbols/matrices in $...$ delimiters
    - use double backslashes (\\) for LaTeX commands
    """

    def __init__(self, model: str = "llama3.2:3b", timeout: int = 180):
        self.model = model
        self.timeout = timeout
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

    def _run_with_timeout(self, fn, *args, timeout: int = 180, **kwargs):
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

    def _postprocess_latex(self, text: str) -> str:
        """Best-effort postprocessing to respect constraints."""
        if not text:
            return text

        # Wrap likely inline math tokens that contain common math symbols/funcs in $...$.
        # This is heuristic; the prompt already enforces.
        if "$" not in text:
            # If it contains typical math punctuation, wrap the whole text.
            if re.search(r"[=+\-*/∈∑∫√]|\\(?:frac|cos|sin|tan|theta|phi|mathbf|begin|end|left|right)", text):
                text = f"${text}$"

        return text

    def generate_explanations(
        self,
        knowledge_bricks: str,
        quiz_data: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not quiz_data:
            return []

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)

        validated = []
        for idx, q in enumerate(quiz_data):
            if not isinstance(q, dict):
                continue

            question = str(q.get("question", ""))
            options = q.get("options", [])
            answer = str(q.get("answer", ""))
            explanation_old = q.get("explanation", "")

            if not self._check_ollama():
                q["explanation"] = explanation_old or "No explanation provided."
                validated.append(q)
                continue

            prompt = f"""
[SYSTEM: EXPLAINER]
Using ONLY the Knowledge Bricks, write an explanation for the following MCQ.
You MUST produce exactly 2 sentences.

IMPORTANT LATEX AND FORMAT RULES:
- Return ONLY valid JSON: {{"explanation": "..."}} (NO markdown code blocks, NO extra text).
- LATEX SAFETY RULES: Use ONLY valid KaTeX commands. NEVER invent, truncate, or hallucinate LaTeX commands (e.g., NO \\ullet, \\ext, \\heta). ONLY use standard operators like \\cdot, \\sin, \\cos, \\theta, \\frac, ^{{}}, _{{}}. 
- All mathematical expressions MUST use KaTeX-compatible LaTeX, wrap inline math with $...$, and be on a SINGLE LINE.
- Any LaTeX command MUST use double backslashes (\\) inside the explanation (e.g., \\\\cos, \\\\theta). If unsure, output plain text instead!
- Text inside LaTeX (like \\\\text{...}) MUST contain proper spaces. Do NOT merge words together.
- DO NOT break down equations into multiple lines (NO OCR-style formatting).
- DO NOT use emojis or decorative unicode symbols (e.g. ✀ ✦ ✨ ✔ ❌ ➜ ◆ ● ■ ★).
- The explanation must be clean, readable, markdown-safe, and use proper spacing.

Knowledge Bricks:
{knowledge_bricks}

Question:
{question}

Options:
{options}

Correct Answer:
{answer}
            """.strip()

            logging.info(f"Explaining question {idx+1}/{len(quiz_data)}...")
            resp = self._run_with_timeout(
                ollama.generate,
                model=self.model,
                prompt=prompt,
                options={"num_ctx": 4096},
                format="json",
                timeout=self.timeout,
            )

            raw = ""
            parsed: Optional[Dict[str, Any]] = None
            if resp is not None:
                if isinstance(resp, dict):
                    raw = resp.get("response", "") or ""
                else:
                    raw = getattr(resp, "response", "") or ""

                (OUTPUT_DIR / f"explainer_response_q{idx+1}.txt").write_text(raw, encoding="utf-8")

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

                sanitized_raw = _sanitize_invalid_json_escapes(raw.strip())
                try:
                    parsed = json.loads(sanitized_raw)
                except Exception:
                    m = re.search(r"\{[\s\S]*\}", sanitized_raw)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                        except Exception:
                            parsed = None

            explanation = ""
            if isinstance(parsed, dict) and isinstance(parsed.get("explanation"), str):
                explanation = parsed["explanation"]
            else:
                explanation = explanation_old or "No explanation provided."

            explanation = explanation.strip()
            explanation = self._postprocess_latex(explanation)

            q["explanation"] = explanation
            validated.append(q)

        if output_path:
            Path(output_path).write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")

        return validated

