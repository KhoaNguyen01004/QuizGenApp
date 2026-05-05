import concurrent.futures
import ollama
import logging
from pathlib import Path
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CuratorAgent:
    def __init__(self, model: str = "qwen3:1.7b", timeout: int = 180):
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

        logging.info("Extracting knowledge bricks...")
        if not self._check_ollama():
            logging.error("Ollama is not running or accessible. Please start Ollama and ensure the model is available.")
            return ""

        response = self._run_with_timeout(
            ollama.generate,
            model=self.model,
            prompt=prompt,
            timeout=self.timeout,
        )
        if response is None:
            return ""

        knowledge_bricks = response['response'].strip()

        # Save for debug
        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "knowledge_bricks.md").write_text(knowledge_bricks, encoding="utf-8")
        return knowledge_bricks

