import re


def clean_markdown_output(text: str) -> str:
    """Post-process generated quiz Markdown to fix common LaTeX/OCR artifacts.

    Fixes implemented:
    - Remove duplicated option labels like "- **A**) A) Translation" -> "- **A**) Translation"
    - Repair common control-character corruption before LaTeX tokens (e.g. "\b" shown as backspace)
    - Replace OCR/LLM artifacts like "oldsymbol" -> "\\mathbf"
    - Normalize broken math whitespace: "$ oldsymbol{v} $" -> "$mathbf{v}$"

    Note: This is intentionally conservative; it only targets the patterns observed in this project.
    """

    if not isinstance(text, str) or not text:
        return text

    cleaned = text

    # --- 0) Normalize control-char corruption ---
    # Your output shows tokens like: "$ ˆoldsymbol{v} $" where ˆ is a backspace/control char.
    # In Python strings this is typically represented as \x08 (backspace).
    # We strip these control chars rather than trying to interpret them.
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", cleaned)

    # Also sometimes the corruption manifests as a literal \b character sequence.
    cleaned = cleaned.replace("\\b", "")

    # --- 1) Option label deduplication ---
    # Example: "- **A**) A) Translation" -> "- **A**) Translation"
    cleaned = re.sub(
        r"(\*\*([A-D])\*\*\)\s*)\2\)\s*",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Another variant: "- **A**) A) $...$" -> keep the math
    cleaned = re.sub(
        r"(\*\*([A-D])\*\*\)\)\s*)\2\)\s*",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )

    # --- 2) LaTeX artifact cleanup: oldsymbol -> \\mathbf ---
    # Fix spacing corruption before oldsymbol.
    cleaned = re.sub(r"\\\s*oldsymbol", r"\\mathbf", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("oldsymbol", "\\mathbf")

    # Also handle cases where generator outputs "\\mathbf{ v }" with odd spaces.
    cleaned = re.sub(r"\\mathbf\s*\{\s*", r"\\mathbf{", cleaned)
    # Only remove space before closing brace if it's right after a single character (like \mathbf{v })
    cleaned = re.sub(r"(\\mathbf{[A-Za-z0-9])\s*\}", r"\1}", cleaned)

    # --- 3) Fix common broken math wrappers / missing braces ---
    cleaned = re.sub(r"\$\s+", r"$", cleaned)
    cleaned = re.sub(r"\s+\$", r"$", cleaned)

    # If we see "$ \\mathbf v $" (missing braces), convert to "$\\mathbf{v}$"
    cleaned = re.sub(r"\\mathbf\s+([A-Za-z])", r"\\mathbf{\1}", cleaned)

    # Repair space-separated commands inside math e.g. "\\ theta" -> "\\theta"
    cleaned = re.sub(r"\\\s+([a-zA-Z]+)", r"\\\1", cleaned)

    # --- 4) Cleanup repeated whitespace (not inside math too aggressively) ---
    cleaned = re.sub(r"[\t ]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip() + ("\n" if text.endswith("\n") else "")

