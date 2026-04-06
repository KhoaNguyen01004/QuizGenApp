import json
import re
import ollama
from pathlib import Path

class PedagogueAgent:
    def __init__(self, model="phi4-mini:latest"):
        self.model = model

    def _parse_json(self, text):
        # Improved extraction: handle full array with balanced brackets
        def extract_full_array(s):
            start = 0
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

            if start == 0:
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

        json_str = extract_full_array(text)

        if not json_str or not json_str.startswith('['):
            print("Could not find a valid JSON array in the response.")
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
        json_str = re.sub(r'\\\\([a-zA-Z*(){}\\[\\]])', r'\\\1', json_str)  # LaTeX escapes \\\\cos -> \\cos

        # Save cleaned
        cleaned_path = OUTPUT_DIR / "cleaned_pedagogue.json"
        cleaned_path.write_text(json_str, encoding="utf-8")

        # Parse attempts
        attempts = [json_str, json_str.replace("'", '"')]
        for i, attempt in enumerate(attempts):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, list) and len(parsed) > 0 and 'question' in parsed[0]:
                    print(f"JSON parsed successfully on attempt {i+1} ({len(parsed)} items)")
                    return parsed
            except json.JSONDecodeError as e:
                print(f"Attempt {i+1} failed: {e}")

        print("Parsing failed. Check outputs/ files.")
        return []

    def save_as_markdown(self, quiz_data, output_path):
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

    def generate_quiz(self, knowledge_bricks: str, output_path: str = None):
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

        print(f"--- [PEDAGOGUE] Running {self.model}...")
        response = ollama.generate(model=self.model, prompt=prompt)
        raw_response = response['response']
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "pedagogue_response.txt").write_text(raw_response, encoding="utf-8")
        quiz_data = self._parse_json(raw_response)

        if quiz_data and output_path:
            self.save_as_markdown(quiz_data, output_path)

        return quiz_data

