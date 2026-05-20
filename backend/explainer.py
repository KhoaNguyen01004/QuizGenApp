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

        # Ensure LaTeX commands use double backslash.
        # For sequences like "\alpha" -> "\\alpha" (avoid turning already-double slashes into quadruple).
        text = re.sub(r"(?<!\\\\)\\([a-zA-Z])", r"\\\\\1", text)

        # Wrap likely inline math tokens that contain common math symbols/funcs in $...$.
        # This is heuristic; the prompt already enforces.
        if "$" not in text:
            # If it contains typical math punctuation, wrap the whole text.
            if re.search(r"[=+\-*/∈∑∫√]|\\(frac|cos|sin|tan|theta|phi|mathbf|begin|end|left|right)", text):
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
- DO NOT break down equations into multiple lines (NO OCR-style formatting).
- DO NOT use emojis or decorative unicode symbols (e.g. ✀ ✦ ✨ ✔ ❌ ➜ ◆ ● ■ ★).
- The explanation must be clean, markdown-safe, and without random line breaks.

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

                try:
                    parsed = json.loads(raw.strip())
                except Exception:
                    m = re.search(r"\{[\s\S]*\}", raw.strip())
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

