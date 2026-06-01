"""Shared JSON parsing utilities used by all agents."""

import json
import logging
import re
from typing import Any, Dict, List, Optional


def sanitize_invalid_json_escapes(s: str) -> str:
    r"""Replace invalid JSON backslash escapes with double-escaped versions.

    Valid JSON string escapes: \" \\ \/ \b \f \n \r \t \uXXXX
    Everything else (e.g. \\theta, \\frac) must be double-escaped.
    """
    out: List[str] = []
    i = 0
    valid_after = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "u":
                # Keep valid \uXXXX sequences
                if i + 5 < n and all(
                    c in "0123456789abcdefABCDEF" for c in s[i + 2 : i + 6]
                ):
                    out.append("\\u" + s[i + 2 : i + 6])
                    i += 6
                    continue
            if nxt in valid_after:
                out.append("\\" + nxt)
                i += 2
                continue
            # Invalid escape: double-escape the backslash
            out.append("\\\\" + nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_last_json_array(text: str) -> Optional[str]:
    """Extract the last complete top-level JSON array from arbitrary text."""
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

        if c == "[":
            if depth == 0:
                start = i
            depth += 1
        elif c == "]":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = s[start : i + 1].strip()
                    last = candidate
                    start = None

        escape = (c == "\\") and not escape

    return last


def extract_json_object(text: str) -> Optional[str]:
    """Extract the first complete top-level JSON object from arbitrary text."""
    s = text.strip()
    if not s:
        return None

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

        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return s[start : i + 1].strip()

        escape = (c == "\\") and not escape

    return None


def safe_parse_json(raw: str) -> Optional[Any]:
    """Try to parse JSON from raw LLM output, with escape sanitization."""
    if not raw:
        return None

    cleaned = raw.replace("```json", "").replace("```", "").strip()
    # Normalize literal newlines inside strings
    cleaned = cleaned.replace("\\\r\n", "\\\\n")
    cleaned = cleaned.replace("\\\n", "\\\\n")
    cleaned = cleaned.replace("\\\r", "\\\\n")

    sanitized = sanitize_invalid_json_escapes(cleaned)

    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass

    # Try extracting array
    arr_candidate = extract_last_json_array(sanitized)
    if arr_candidate:
        try:
            return json.loads(arr_candidate)
        except json.JSONDecodeError:
            pass

    # Try extracting object
    obj_candidate = extract_json_object(sanitized)
    if obj_candidate:
        try:
            return json.loads(obj_candidate)
        except json.JSONDecodeError:
            pass

    logging.error("safe_parse_json: all parse attempts failed.")
    return None
