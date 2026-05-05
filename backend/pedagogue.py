import concurrent.futures
import json
import re
import ollama
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PedagogueAgent:
    def __init__(self, model: str = "phi4-mini:latest", timeout: int = 180):
        self.model = model
        self.timeout = timeout
        self._log_gpu_status()

    def _log_gpu_status(self):
        """Log GPU availability for Ollama."""
        try:
            # Check if Ollama has GPU info
            info = ollama.ps()
            gpu_info = "GPU support unknown"
            # Ollama doesn't expose GPU info directly, but we can check if models are loaded
            if info and len(info) > 0:
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
        """Check if Ollama is running and accessible."""
        try:
            ollama.list()
            return True
        except Exception:
            return False

    def _parse_json(self, text: str) -> List[Dict[str, Any]]:
        # Improved extraction: handle full array with balanced brackets
        def extract_full_array(s):
            start = -1
            bracket_count = 0
            i = 0
            n = len(s)
            in_string = False
            escape = False

            # Find start of array
            while i < n:
                c = s[i]
                if c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == '[':
                        start = i
                        bracket_count = 1
                        break
                escape = c == '\\' and not escape
                i += 1

            if start == -1:
                return None

            # Balance to find end
            i = start + 1
            while i < n:
                c = s[i]
                if c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == '[':
                        bracket_count += 1
                    elif c == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            return s[start:i+1].strip()
                escape = c == '\\' and not escape
                i += 1

            # If unbalanced, take from start to end if array-like
            if bracket_count > 0:
                # Auto-repair: append closing ]
                return s[start:].strip() + ']'

            return None

        # Remove common markdown/code fences that models add (```json, ```)
        text = text.replace('```json', '').replace('```', '')

        json_str = extract_full_array(text)

        if not json_str or not json_str.startswith('['):
            logging.warning("Could not find a valid JSON array in the response.")
            return []

        # Save raw extracted
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        raw_path = OUTPUT_DIR / "raw_extracted_pedagogue.json"
        raw_path.write_text(json_str, encoding="utf-8")

        # Minimal fixes
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)  # trailing commas
        json_str = json_str.replace('\\ n', '\\n')  # artifacts
        json_str = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', ' ', json_str)  # control chars
        json_str = re.sub(r'\\\\([a-zA-Z*(){}\\[\\]])', r'\\\\\1', json_str)  # LaTeX escapes \\\\cos -> \\\cos

        # Attempt to robustly double-escape stray single backslashes inside JSON string literals
        def _escape_backslashes_in_strings(s: str) -> str:
            def _repl(m):
                inner = m.group(1)
                # Replace single backslashes that are not already doubled with double backslashes
                inner_fixed = re.sub(r'(?<!\\\\)\\(?!\\\\)', r'\\\\', inner)
                return '"' + inner_fixed + '"'
            try:
                return re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', _repl, s)
            except re.error:
                return s

        # Save cleaned (pre-escape)
        cleaned_path = OUTPUT_DIR / "cleaned_pedagogue.json"
        cleaned_path.write_text(json_str, encoding="utf-8")

        # Also create an escaped variant to help with parsing
        escaped_variant = _escape_backslashes_in_strings(json_str)

        # Parse attempts: try original, escaped, and single-quote-fixed variants
        attempts = [json_str, escaped_variant, json_str.replace("'", '"'), escaped_variant.replace("'", '"')]
        for i, attempt in enumerate(attempts):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, list) and len(parsed) > 0 and 'question' in parsed[0]:
                    logging.info(f"JSON parsed successfully on attempt {i+1} ({len(parsed)} items)")
                    return parsed
            except json.JSONDecodeError as e:
                logging.warning(f"Attempt {i+1} failed: {e}")

        logging.error("Parsing failed. Check outputs/ files.")
        return []

    def save_as_markdown(self, quiz_data: List[Dict[str, Any]], output_path: str) -> None:
        md_content = "# Generated Quiz\n\n"
        for i, q in enumerate(quiz_data, 1):
            md_content += f"### Question {i}\\n{q['question']}\\n\\n"
            for idx, opt in enumerate(q['options']):
                label = chr(65 + idx)
                clean_opt = re.sub(r'^([A-D][\\.])\\s*', '', str(opt)).strip()
                md_content += f"- **{label}**) {clean_opt}\\n"
            md_content += f"\\n> **Correct Answer:** {q['answer'].upper()}\\n"
            md_content += f"> **Explanation:** {q.get('explanation', 'N/A')}\\n\\n---\\n\\n"
        Path(output_path).write_text(md_content, encoding="utf-8")

    def generate_quiz(self, knowledge_bricks: str, output_path: Optional[str] = None) -> List[Dict[str, Any]]:
        prompt = f"""[SYSTEM: PEDAGOGUE]
Generate 5 MCQs from ONLY these knowledge bricks.

Strict rules:
- 4 options per Q (A B C D), 1 correct.
- LaTeX math ONLY.
- Double escape backslashes: \\\\cos \\\\theta
- NO chit-chat, markdown, codeblocks.

Knowledge:
{knowledge_bricks}

VALID JSON ARRAY ONLY:
[{{"question":"Q?", "options":["A) ","B) ","C) ","D) "], "answer":"A", "explanation":"..."}},{{"question":"..."}}]"""

        logging.info(f"Running {self.model} to generate quiz...")
        if not self._check_ollama():
            logging.error("Ollama is not running or accessible. Please start Ollama and ensure the model is available.")
            return []

        # Request structured JSON where supported and use low temperature for determinism
        response = self._run_with_timeout(
            ollama.generate,
            model=self.model,
            prompt=prompt,
            timeout=self.timeout,
        )
        if response is None:
            return []

        raw_response = response['response']

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "pedagogue_response.txt").write_text(raw_response, encoding="utf-8")
        # Try parsing the response. If parsing fails, attempt a targeted "repair" generation
        quiz_data = self._parse_json(raw_response)

        if not quiz_data:
            logging.info("Initial parse failed — attempting repair generation to force strict JSON output.")
            repair_prompt = (
                "You will be given an arbitrary model output. Extract and return ONLY a valid JSON array that matches the schema:\n"
                "[{\"question\":\"...\", \"options\":[\"A) ...\",\"B) ...\",\"C) ...\",\"D) ...\"], \"answer\":\"A\", \"explanation\":\"...\"}, ...]\n"
                "If you cannot produce a valid array, return an empty array: []\n\nOUTPUT_TO_FIX:\n" + raw_response
            )

            repair_resp = self._run_with_timeout(
                ollama.generate,
                model=self.model,
                prompt=repair_prompt,
                timeout=min(60, self.timeout),
            )

            if repair_resp is not None:
                repaired = repair_resp.get('response', '')
                (OUTPUT_DIR / "pedagogue_response_repair.txt").write_text(repaired, encoding="utf-8")
                quiz_data = self._parse_json(repaired)

        # As a last resort, call Ollama HTTP API directly with format=json to force strict JSON
        if not quiz_data:
            try:
                import requests
                logging.info("Attempting HTTP fallback to Ollama /api/generate with format=json")
                http_payload = {"model": self.model, "prompt": prompt, "format": "json"}
                r = requests.post("http://127.0.0.1:11434/api/generate", json=http_payload, timeout=min(60, self.timeout))
                if r.ok:
                    raw_text = r.text
                    # Ollama HTTP may stream chunks as JSON lines with a 'response' field.
                    # If so, assemble the 'response' parts; otherwise use the full text.
                    assembled = []
                    for line in raw_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            part = json.loads(line)
                            if isinstance(part, dict) and 'response' in part:
                                assembled.append(str(part.get('response', '')))
                            else:
                                assembled.append(line)
                        except Exception:
                            assembled.append(line)

                    http_response_text = "".join(assembled) if assembled else raw_text
                    (OUTPUT_DIR / "pedagogue_response_http.txt").write_text(http_response_text, encoding="utf-8")
                    quiz_data = self._parse_json(http_response_text)
            except Exception as e:
                logging.warning(f"HTTP fallback failed: {e}")

        if quiz_data and output_path:
            self.save_as_markdown(quiz_data, output_path)

        return quiz_data

