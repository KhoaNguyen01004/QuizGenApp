"""Shared LLM backend.

Issue #6 fix: is_available() was calling ollama.list() (GET /api/tags)
before every generation. Result: dozens of redundant API calls per pipeline run.
Fix: check availability once at init, cache the result.

Issue #7 fix: keep_alive was 300s (5 min). Between Curator → Pedagogue →
Adversary the model could be evicted. Set keep_alive=3600 (1 hour) so the
model stays resident for the entire pipeline.
"""

import concurrent.futures
import logging
from typing import Any, Optional

try:
    import ollama  # type: ignore
except Exception:  # pragma: no cover
    ollama = None  # type: ignore

logger = logging.getLogger(__name__)

# Keep model loaded for 1 hour — covers the entire pipeline run
_KEEP_ALIVE_SECONDS = 3600


class LLMProvider:
    """Single shared Ollama LLM backend for all agents."""

    def __init__(self, model: str = "qwen3:4b", timeout: int = 600):
        self.model = model
        self.timeout = timeout

        # Issue #6: check availability ONCE at init, cache result
        self._available: Optional[bool] = None
        self._check_and_log()

    def _check_and_log(self) -> None:
        """Check model availability once and cache the result."""
        if ollama is None:
            self._available = False
            logger.warning("LLMProvider: 'ollama' python package not available.")
            return

        try:
            models = ollama.list()

            available = []
            if hasattr(models, "models"):
                available = [m.model for m in models.models]
            elif isinstance(models, dict):
                available = [m.get("name", "") for m in models.get("models", [])]

            self._available = True  # Ollama is reachable

            if self.model in available or any(self.model in m for m in available):
                logger.info(f"LLMProvider: Model '{self.model}' is available.")
            else:
                logger.warning(
                    f"LLMProvider: Model '{self.model}' not found. "
                    f"Available: {available}. Run: ollama pull {self.model}"
                )
        except Exception as e:
            logger.warning(f"LLMProvider: Could not reach Ollama: {e}")
            self._available = False

    def is_available(self) -> bool:
        """Return cached availability — no repeated GET /api/tags calls."""
        if self._available is None:
            self._check_and_log()
        return bool(self._available)

    def generate(
        self,
        prompt: str,
        options: Optional[dict] = None,
        format: Optional[str] = None,
        keep_alive: int = _KEEP_ALIVE_SECONDS,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        """Generate a response from the LLM."""
        if ollama is None:
            logger.error("LLMProvider: ollama python package not available.")
            return None

        if options is None:
            options = {}

        options.setdefault("num_gpu", -1)
        options.setdefault("num_ctx", 4096)

        call_timeout = timeout if timeout is not None else self.timeout

        kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "keep_alive": keep_alive,
            "options": options,
        }
        if format:
            kwargs["format"] = format

        def _call() -> Any:
            return ollama.generate(**kwargs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                resp = future.result(timeout=call_timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"LLMProvider: Request timed out after {call_timeout}s.")
                return None
            except Exception as exc:
                logger.error(f"LLMProvider: Request failed: {exc}")
                return None

        if resp is None:
            return None

        if isinstance(resp, dict):
            return resp.get("response", "") or ""
        return getattr(resp, "response", "") or ""

    def generate_batch(
        self,
        prompts: list[str],
        options: Optional[dict] = None,
        format: Optional[str] = None,
        max_workers: int = 3,
        timeout: Optional[int] = None,
    ) -> list[Optional[str]]:
        """Generate responses for multiple prompts in parallel."""
        if not prompts:
            return []

        results: list[Optional[str]] = [None] * len(prompts)

        def _task(idx: int, prompt: str) -> tuple[int, Optional[str]]:
            resp = self.generate(
                prompt=prompt,
                options=options,
                format=format,
                timeout=timeout,
            )
            return idx, resp

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_task, i, p): i for i, p in enumerate(prompts)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, resp = future.result()
                    results[idx] = resp
                except Exception as exc:
                    logger.error(f"LLMProvider batch call failed: {exc}")

        return results

