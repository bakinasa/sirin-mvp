"""Parse LLM JSON responses: fences, embedded objects, truncation repair."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_llm_json_content(text: str) -> Any:
    """Parse JSON for profession map / scenario documents (prefers sections[])."""
    return _parse_json_candidates(text, prefer_summary=False)


def parse_summary_json_content(text: str) -> Any:
    """Parse JSON for source summaries (prefers brief_points and related fields)."""
    return _parse_json_candidates(text, prefer_summary=True)


def _parse_json_candidates(text: str, *, prefer_summary: bool) -> Any:
    text = (text or "").strip()
    if not text:
        return {"raw": "", "clarifications_needed": ["Пустой ответ модели"]}

    candidates = _collect_json_candidates(text)

    if prefer_summary:
        for candidate in candidates:
            parsed = _try_parse(candidate)
            if parsed is None:
                continue
            if _payload_has_summary_keys(parsed):
                return parsed

    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is None:
            continue
        unwrapped = unwrap_block_document(parsed)
        if not prefer_summary and isinstance(unwrapped, dict) and unwrapped.get("sections"):
            return unwrapped

    for candidate in candidates:
        parsed = _try_parse(candidate)
        if parsed is not None:
            return unwrap_block_document(parsed) if not prefer_summary else parsed

    return {"raw_text": text, "clarifications_needed": ["Ответ не в JSON или обрезан моделью"]}


def _collect_json_candidates(text: str) -> list[str]:
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

    repaired = _repair_truncated_json(_extract_balanced_object(text) or text)
    if repaired:
        add(repaired)

    return candidates


def _payload_has_summary_keys(payload: Any) -> bool:
    if isinstance(payload, list) and payload:
        return True
    if not isinstance(payload, dict):
        return False
    if any(key in payload for key in _SUMMARY_KEYS):
        return True
    normalized = _normalize_summary_payload(payload)
    return any(normalized.get(key) for key in _SUMMARY_KEYS if key != "short")


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


_SUMMARY_KEYS = (
    "brief_points",
    "operations",
    "skills",
    "violations",
    "visual_points",
    "constraints",
    "terms",
    "important_fragments",
    "short",
)

_SUMMARY_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "brief_points": (
        "briefPoints",
        "brief",
        "summary",
        "key_points",
        "points",
        "highlights",
        "краткие_пункты",
        "пункты",
        "выжимка",
        "основные_пункты",
    ),
    "operations": (
        "operation",
        "procedures",
        "procedure",
        "steps",
        "actions",
        "этапы",
        "операции",
        "действия",
        "процедуры",
    ),
    "skills": ("skill", "competencies", "competence", "навыки", "компетенции", "требования"),
    "violations": (
        "violation",
        "errors",
        "mistakes",
        "prohibitions",
        "нарушения",
        "ошибки",
        "запреты",
    ),
    "visual_points": (
        "visualPoints",
        "visual",
        "visuals",
        "visual_cues",
        "визуальные_точки",
        "визуальные_ориентиры",
    ),
    "constraints": ("constraint", "limitations", "limits", "ограничения", "условия"),
    "terms": ("term", "glossary", "definitions", "термины", "глоссарий"),
    "important_fragments": (
        "importantFragments",
        "fragments",
        "quotes",
        "citations",
        "цитаты",
        "важные_фрагменты",
        "фрагменты",
    ),
    "short": ("summary_short", "short_summary", "кратко"),
}


def extract_source_summary(payload: Any) -> dict[str, Any]:
    """Normalize a source-summary JSON payload into the stored field shape."""
    if isinstance(payload, list):
        return _empty_summary(brief_points=_flatten_text_list(payload))

    data = _unwrap_summary_dict(payload)
    if isinstance(data, dict) and data.get("sections") and not _dict_has_summary_fields(data):
        converted = _summary_from_sections(data)
        if summary_has_content(converted):
            return converted

    normalized = _normalize_summary_payload(data if isinstance(data, dict) else {})
    brief = normalized["brief_points"] or normalized["short"]
    return {
        "brief_points": brief,
        "operations": normalized["operations"],
        "skills": normalized["skills"],
        "violations": normalized["violations"],
        "visual_points": normalized["visual_points"],
        "constraints": normalized["constraints"],
        "terms": normalized["terms"],
        "important_fragments": normalized["important_fragments"],
    }


def _empty_summary(**fields: list[str]) -> dict[str, Any]:
    base = {key: [] for key in _SUMMARY_KEYS if key != "short"}
    base.update(fields)
    return base


def _dict_has_summary_fields(data: dict[str, Any]) -> bool:
    normalized = _normalize_summary_payload(data)
    return any(normalized.get(key) for key in _SUMMARY_KEYS if key != "short")


def _normalize_summary_payload(data: dict[str, Any]) -> dict[str, list[str]]:
    out = {key: [] for key in _SUMMARY_KEYS if key != "short"}
    out["short"] = []
    if not data:
        return out

    alias_to_key: dict[str, str] = {}
    for key, aliases in _SUMMARY_FIELD_ALIASES.items():
        alias_to_key[key] = key
        for alias in aliases:
            alias_to_key[alias] = key
            alias_to_key[alias.lower()] = key

    for raw_key, value in data.items():
        if value is None:
            continue
        key = alias_to_key.get(raw_key) or alias_to_key.get(str(raw_key).lower())
        if not key:
            continue
        target = "short" if key == "short" else key
        out[target] = _merge_text_lists(out[target], _flatten_text_list(value))

    return out


def _merge_text_lists(left: list[str], right: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in left + right:
        marker = item.strip()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        merged.append(marker)
    return merged


def _summary_from_sections(data: dict[str, Any]) -> dict[str, Any]:
    sections = data.get("sections")
    if not isinstance(sections, list):
        return _empty_summary()

    buckets = {key: [] for key in _SUMMARY_KEYS if key != "short"}
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").lower()
        texts = _flatten_text_list(section.get("items") or section.get("content") or section.get("points"))
        if not texts:
            continue
        if any(word in title for word in ("операц", "этап", "действ", "процедур", "шаг")):
            buckets["operations"] = _merge_text_lists(buckets["operations"], texts)
        elif any(word in title for word in ("навык", "компетен", "умени", "skill")):
            buckets["skills"] = _merge_text_lists(buckets["skills"], texts)
        elif any(word in title for word in ("наруш", "ошиб", "запрет", "violation")):
            buckets["violations"] = _merge_text_lists(buckets["violations"], texts)
        elif any(word in title for word in ("визуал", "маркир", "visual")):
            buckets["visual_points"] = _merge_text_lists(buckets["visual_points"], texts)
        elif any(word in title for word in ("огранич", "услов", "constraint")):
            buckets["constraints"] = _merge_text_lists(buckets["constraints"], texts)
        elif any(word in title for word in ("термин", "глосс", "term")):
            buckets["terms"] = _merge_text_lists(buckets["terms"], texts)
        elif any(word in title for word in ("цитат", "фрагмент", "quote")):
            buckets["important_fragments"] = _merge_text_lists(buckets["important_fragments"], texts)
        else:
            buckets["brief_points"] = _merge_text_lists(buckets["brief_points"], texts)

    if not any(buckets.values()):
        for section in sections:
            if isinstance(section, dict):
                buckets["brief_points"] = _merge_text_lists(
                    buckets["brief_points"],
                    _flatten_text_list(section.get("items") or section.get("content")),
                )
    return buckets


def summary_has_content(summary: dict[str, Any]) -> bool:
    return any(summary.get(key) for key in _SUMMARY_KEYS if key != "short")


def _unwrap_summary_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = parse_summary_json_content(payload)
    if not isinstance(payload, dict):
        return {}
    if _dict_has_summary_fields(payload):
        return payload
    for key in ("raw_text", "raw"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            inner = parse_summary_json_content(raw)
            if isinstance(inner, dict) and (_dict_has_summary_fields(inner) or inner.get("sections")):
                return inner
            continue
    for key in ("content", "body", "data", "result", "document", "output", "summary"):
        val = payload.get(key)
        if isinstance(val, dict):
            found = _unwrap_summary_dict(val)
            if found:
                return found
        if isinstance(val, str) and val.strip():
            inner = parse_summary_json_content(val)
            if isinstance(inner, dict) and (_dict_has_summary_fields(inner) or inner.get("sections")):
                return inner
    if payload.get("sections"):
        return payload
    return payload


def _flatten_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        for key in ("text", "content", "description", "title", "point", "value", "body"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return [inner.strip()]
        parts = [str(v).strip() for v in value.values() if isinstance(v, (str, int, float)) and str(v).strip()]
        return ["; ".join(parts)] if parts else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out = _merge_text_lists(out, _flatten_text_list(item))
        return out
    text = str(value).strip()
    return [text] if text else []


def _as_list(value: Any) -> list:
    return _flatten_text_list(value)


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
    attempts = [text, re.sub(r",\s*([}\]])", r"\1", text)]
    for candidate in attempts:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
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
