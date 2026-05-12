import concurrent.futures
import logging
from pathlib import Path
from typing import Optional

import ollama


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class CuratorAgent:
    def __init__(self, model: str = "qwen3:1.7b", timeout: int = 180):
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
        """Extract key concepts as structured 'Knowledge Bricks' MD.

        Robustness:
        - The initial extraction can time out on long PDFs.
        - If the primary attempt fails, fall back to chunk-based extraction + merge.
        """

        def _build_prompt(source: str) -> str:
            return f"""
[SYSTEM: KNOWLEDGE CURATOR]
Extract ONLY the core concepts, definitions, formulas, and key facts from the source material.
Ignore examples, exercises, images, noise.

Format as clean Markdown bullet list:
- Concept 1: definition/formula
- Concept 2: ...

Use LaTeX for math. Match source language. No fluff.

SOURCE:
{source}
            """.strip()

        def _chunk_text(text: str, chunk_size: int = 3000, overlap: int = 300) -> list[str]:
            text = text or ""
            if len(text) <= chunk_size:
                return [text]

            chunks: list[str] = []
            start = 0
            n = len(text)
            while start < n:
                end = min(n, start + chunk_size)
                chunks.append(text[start:end])
                if end >= n:
                    break
                start = max(0, end - overlap)
            return chunks

        prompt = _build_prompt(md_content)


        logging.info("Extracting knowledge bricks...")
        if not self._check_ollama():
            logging.error(
                "Ollama is not running or accessible. Please start Ollama and ensure the model is available."
            )
            return ""

        response = self._run_with_timeout(
            ollama.generate,
            model=self.model,
            prompt=prompt,
            keep_alive=0,
            options={"num_ctx": 4096, "num_gpu": 0},
            timeout=self.timeout,
        )

        def _extract_from_response(resp) -> str:
            if resp is None:
                return ""
            if isinstance(resp, dict):
                kb = resp.get("response", "")
                if not kb.strip():
                    kb = resp.get("thinking", "")
                return (kb or "").strip()
            kb = getattr(resp, "response", "") or ""
            if not kb.strip():
                kb = getattr(resp, "thinking", "") or ""
            return (kb or "").strip()

        # Primary attempt
        knowledge_bricks = _extract_from_response(response)

        # Fallback: chunk-based extraction + merge
        if not knowledge_bricks:
            logging.warning("Primary knowledge extraction failed/empty. Falling back to chunk-based extraction.")
            chunks = _chunk_text(md_content, chunk_size=3000, overlap=300)

            partials: list[str] = []
            for i, ch in enumerate(chunks, 1):
                logging.info("Extracting chunk %s/%s...", i, len(chunks))
                ch_prompt = _build_prompt(ch)
                ch_resp = self._run_with_timeout(
                    ollama.generate,
                    model=self.model,
                    prompt=ch_prompt,
                    keep_alive=0,
                    options={"num_ctx": 2048, "num_gpu": 0},
                    timeout=min(self.timeout, 240),
                )
                kb = _extract_from_response(ch_resp)
                if kb:
                    partials.append(kb)

            merged_source = "\n".join(partials)
            if not merged_source.strip():
                return ""

            merge_prompt = f"""
[SYSTEM: KNOWLEDGE CURATOR]
You are given multiple partial knowledge-brick bullet lists.
Deduplicate and merge them into ONE clean Markdown bullet list of core concepts.
Rules:
- Keep key definitions/formulas.
- Remove redundancy.
- Output only bullet lines starting with '- '.

PARTIALS:
{merged_source}
            """.strip()

            merge_resp = self._run_with_timeout(
                ollama.generate,
                model=self.model,
                prompt=merge_prompt,
                keep_alive=0,
                options={"num_ctx": 2048, "num_gpu": 0},
                timeout=min(self.timeout, 240),
            )

            knowledge_bricks = _extract_from_response(merge_resp)

        OUTPUT_DIR = Path("outputs")
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / "knowledge_bricks.md").write_text(knowledge_bricks or "", encoding="utf-8")
        return knowledge_bricks or ""

