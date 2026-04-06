import ollama
from pathlib import Path

class CuratorAgent:
    def __init__(self, model="qwen3:1.7b"):
        self.model = model

    def extract_knowledge(self, md_content: str) -> str:
        """Extract key concepts as structured 'Knowledge Bricks' MD."""
        prompt = f"""
[SYSTEM: KNOWLEDGE CURATOR]
Extract ONLY the core concepts, definitions, formulas, and key facts from the source material.
Ignore examples, exercises, images, noise.

Format as clean Markdown bullet list:
- Concept 1: definition/formula
- Concept 2: ...

Use LaTeX for math. Match source language. No fluff.

SOURCE:
{md_content}
        """.strip()

        print("--- [CURATOR] Extracting knowledge bricks... ---")
        response = ollama.generate(model=self.model, prompt=prompt)
        knowledge_bricks = response['response'].strip()

        # Save for debug
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "knowledge_bricks.md").write_text(knowledge_bricks, encoding="utf-8")
        return knowledge_bricks

