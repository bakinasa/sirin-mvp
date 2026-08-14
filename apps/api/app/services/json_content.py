"""Parse LLM JSON responses: fences, embedded objects, truncation repair."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_llm_json_content(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return {"raw": "", "clarifications_needed": ["Пустой ответ модели"]}

    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in seen:
            seen.add(c)
            candidates.append(c)

    add(text)
    add(_extract_from_markdown_fences(text))
    add(_extract_balanced_object(text))

    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is None:
            continue
        unwrapped = unwrap_block_document(parsed)
        if isinstance(unwrapped, dict) and isinstance(unwrapped.get("sections"), list):
            if unwrapped["sections"]:
                return unwrapped

    repaired = _repair_truncated_json(_extract_balanced_object(text) or text)
    if repaired:
        parsed = _try_parse(repaired)
        if parsed is not None:
            unwrapped = unwrap_block_document(parsed)
            if isinstance(unwrapped, dict) and unwrapped.get("sections"):
                return unwrapped

    # Last resort: first valid JSON object even without sections (chat / other steps).
    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is not None:
            return unwrap_block_document(parsed)

    return {"raw_text": text, "clarifications_needed": ["Ответ не в JSON или обрезан моделью"]}


def unwrap_block_document(parsed: Any) -> Any:
    """Recover sections[] when the model wrapped JSON in another object or string."""
    if not isinstance(parsed, dict):
        return parsed

    sections = parsed.get("sections")
    if isinstance(sections, list) and sections:
        return parsed

    for key in ("content", "body", "data", "result", "document", "output", "title"):
        val = parsed.get(key)
        if isinstance(val, dict):
            inner = unwrap_block_document(val)
            if isinstance(inner, dict) and inner.get("sections"):
                return inner
        if isinstance(val, str) and "sections" in val:
            inner = parse_llm_json_content(val)
            if isinstance(inner, dict) and inner.get("sections"):
                return inner

    return parsed


def recover_sections_from_payload(content: dict[str, Any]) -> dict[str, Any] | None:
    """If generation stored raw_text instead of sections, try to parse it again."""
    for key in ("raw_text", "raw"):
        raw = content.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        parsed = parse_llm_json_content(raw)
        if isinstance(parsed, dict) and parsed.get("sections"):
            merged = {**parsed}
            for meta_key in ("clarifications_needed", "_mock", "_generation"):
                if meta_key in content and meta_key not in merged:
                    merged[meta_key] = content[meta_key]
            return merged
    return None


def _try_parse(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_from_markdown_fences(text: str) -> str:
    if "```" not in text:
        return ""
    parts = text.split("```")
    for i, part in enumerate(parts):
        if i % 2 != 1:
            continue
        chunk = part.strip()
        if chunk.lower().startswith("json"):
            chunk = chunk[4:].strip()
        if chunk.startswith("{"):
            return chunk
    return ""


def _extract_balanced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _repair_truncated_json(text: str) -> str | None:
    text = text.strip()
    if not text.startswith("{"):
        return None

    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()

    repaired = text
    if in_string:
        repaired += '"'
    repaired = re.sub(r",\s*$", "", repaired)
    while stack:
        repaired += stack.pop()
    return repaired if _try_parse(repaired) is not None else None
