"""Block-structured artifact helpers: stable ids, item lookup, patches."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Optional

from app.domain.enums import ItemStatus, StepType

PROFESSION_MAP_SECTIONS = [
    ("work_type", "Вид работ для оценки"),
    ("skills", "Оцениваемые навыки"),
    ("assessment_points", "Точки оценки"),
    ("errors", "Частые ошибки и опасные ситуации"),
    ("segment_ideas", "Идеи видеосегментов"),
    ("contradictions", "Противоречия и пробелы"),
    ("expert_questions", "Вопросы для экспертов"),
    ("shooting_constraints", "Ограничения для съёмки"),
]

SCENARIO_PLAN_SECTIONS = [
    ("passport", "Паспорт сценария"),
    ("training_mode", "Режим «Обучение»"),
    ("diagnostic_mode", "Режим «Диагностика»"),
    ("violation_categories", "Категории нарушений"),
    ("regulations", "Правила и регламенты"),
    ("props", "Реквизит и ресурсы"),
    ("shooting_notes", "Съёмочные замечания"),
    ("constraints", "Ограничения"),
]


def empty_document(step_type: str) -> dict[str, Any]:
    specs = (
        PROFESSION_MAP_SECTIONS
        if step_type == StepType.PROFESSION_MAP.value
        else SCENARIO_PLAN_SECTIONS
    )
    return {
        "sections": [
            {"id": sid, "title": title, "items": []}
            for sid, title in specs
        ]
    }


def ensure_ids(content: Any, step_type: str) -> dict[str, Any]:
    """Normalize LLM output into a sections[] document with stable ids."""
    if not isinstance(content, dict):
        content = {"raw": content}

    specs = (
        PROFESSION_MAP_SECTIONS
        if step_type == StepType.PROFESSION_MAP.value
        else SCENARIO_PLAN_SECTIONS
        if step_type == StepType.SCENARIO_PLAN.value
        else None
    )
    if specs is None:
        return content

    doc = copy.deepcopy(content)
    sections = doc.get("sections")
    if not isinstance(sections, list) or not sections:
        sections = _promote_keys_to_sections(doc, specs)
    by_id = {s.get("id"): s for s in sections if isinstance(s, dict) and s.get("id")}
    ordered: list[dict[str, Any]] = []
    for sid, title in specs:
        section = by_id.get(sid) or {"id": sid, "title": title, "items": []}
        section["id"] = sid
        section.setdefault("title", title)
        items = section.get("items")
        if not isinstance(items, list):
            items = _wrap_as_items(items, sid)
        section["items"] = [_normalize_item(it, sid, i) for i, it in enumerate(items)]
        _ensure_nested_ids(section["items"], sid)
        ordered.append(section)
    doc["sections"] = ordered
    return doc


def find_item(content: dict[str, Any], item_id: str) -> Optional[dict[str, Any]]:
    for section in content.get("sections") or []:
        for item in _walk_items(section.get("items") or []):
            if item.get("id") == item_id:
                return item
        if section.get("id") == item_id:
            return section
    return None


def find_item_with_neighbors(
    content: dict[str, Any], item_id: str
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Return (item, neighbors, parent_section)."""
    for section in content.get("sections") or []:
        items = section.get("items") or []
        for idx, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == item_id:
                neighbors = []
                if idx > 0 and isinstance(items[idx - 1], dict):
                    neighbors.append(items[idx - 1])
                if idx + 1 < len(items) and isinstance(items[idx + 1], dict):
                    neighbors.append(items[idx + 1])
                return item, neighbors, section
            nested = item.get("items") if isinstance(item, dict) else None
            if isinstance(nested, list):
                for nidx, child in enumerate(nested):
                    if isinstance(child, dict) and child.get("id") == item_id:
                        neighbors = []
                        if nidx > 0:
                            neighbors.append(nested[nidx - 1])
                        if nidx + 1 < len(nested):
                            neighbors.append(nested[nidx + 1])
                        return child, neighbors, item
            frames = item.get("frames") if isinstance(item, dict) else None
            if isinstance(frames, list):
                for fidx, frame in enumerate(frames):
                    if isinstance(frame, dict) and frame.get("id") == item_id:
                        neighbors = []
                        if fidx > 0:
                            neighbors.append(frames[fidx - 1])
                        if fidx + 1 < len(frames):
                            neighbors.append(frames[fidx + 1])
                        return frame, neighbors, item
        if section.get("id") == item_id:
            return section, [], None
    return None, [], None


def set_item_status(content: dict[str, Any], item_id: str, status: str) -> bool:
    item = find_item(content, item_id)
    if item is None:
        return False
    item["status"] = status
    return True


def replace_item(content: dict[str, Any], item_id: str, new_value: Any) -> bool:
    """Replace an item (or section.items) in-place. Returns True if found."""
    sections = content.get("sections") or []
    for sidx, section in enumerate(sections):
        if section.get("id") == item_id:
            if isinstance(new_value, dict):
                new_value.setdefault("id", item_id)
                sections[sidx] = new_value
            return True
        items = section.get("items") or []
        for iidx, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == item_id:
                if isinstance(new_value, dict):
                    new_value.setdefault("id", item_id)
                    new_value.setdefault("status", item.get("status", ItemStatus.EDITED.value))
                items[iidx] = new_value
                return True
            nested = item.get("items") if isinstance(item, dict) else None
            if isinstance(nested, list):
                for nidx, child in enumerate(nested):
                    if isinstance(child, dict) and child.get("id") == item_id:
                        if isinstance(new_value, dict):
                            new_value.setdefault("id", item_id)
                        nested[nidx] = new_value
                        return True
            frames = item.get("frames") if isinstance(item, dict) else None
            if isinstance(frames, list):
                for fidx, frame in enumerate(frames):
                    if isinstance(frame, dict) and frame.get("id") == item_id:
                        if isinstance(new_value, dict):
                            new_value.setdefault("id", item_id)
                        frames[fidx] = new_value
                        return True
    return False


def apply_patch_json(content: dict[str, Any], patch_json: Any) -> dict[str, Any]:
    """Apply local/global patch payload. Mutates a copy and returns it."""
    doc = copy.deepcopy(content)
    changes = []
    if isinstance(patch_json, dict):
        if "changes" in patch_json:
            changes = patch_json["changes"]
        elif "target_id" in patch_json:
            changes = [patch_json]
        elif "sections" in patch_json:
            return ensure_ids(patch_json, _guess_step(patch_json))
    elif isinstance(patch_json, list):
        changes = patch_json

    for change in changes:
        if not isinstance(change, dict):
            continue
        target = change.get("target_id") or change.get("id") or ""
        if not target:
            continue
        action = str(change.get("action") or "replace")
        new_val = change.get("new") if "new" in change else change.get("new_value")

        if action in ("add_item", "append_item") and isinstance(new_val, dict):
            _append_items(doc, target, [new_val])
            continue
        if action in ("add_items", "append_items") and isinstance(new_val, list):
            _append_items(doc, target, [x for x in new_val if isinstance(x, dict)])
            continue
        if new_val is None:
            continue
        replace_item(doc, target, new_val)
    return doc


def append_section_items(
    content: dict[str, Any],
    section_id: str,
    new_items: list[dict[str, Any]],
    *,
    default_status: str = ItemStatus.PROPOSED.value,
) -> list[str]:
    """Append items into a top-level section. Returns ids of created items."""
    created: list[str] = []
    for section in content.get("sections") or []:
        if section.get("id") != section_id:
            continue
        items = section.setdefault("items", [])
        if not isinstance(items, list):
            section["items"] = []
            items = section["items"]
        for it in new_items:
            item = dict(it)
            item.setdefault("id", f"{section_id}-{uuid.uuid4().hex[:8]}")
            item.setdefault("status", default_status)
            items.append(item)
            created.append(str(item["id"]))
        return created
    return created


def item_field_template(section_items: list[Any]) -> dict[str, Any]:
    """Empty field shell matching the first sibling item in a section."""
    skip = {"id", "status", "items", "frames", "segments"}
    template: dict[str, Any] = {"title": "", "description": ""}
    for item in section_items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in skip:
                continue
            if isinstance(value, str) or value is None:
                template.setdefault(key, "")
            elif isinstance(value, (int, float)):
                template.setdefault(key, value)
        break
    return template


def _append_items(content: dict[str, Any], section_or_item_id: str, new_items: list[dict[str, Any]]) -> bool:
    """Append items into a section (or nested items list)."""
    for section in content.get("sections") or []:
        if section.get("id") == section_or_item_id:
            append_section_items(content, section_or_item_id, new_items)
            return True
        items = section.get("items") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("id") == section_or_item_id:
                nested = item.setdefault("items", [])
                if not isinstance(nested, list):
                    item["items"] = []
                    nested = item["items"]
                for it in new_items:
                    it = dict(it)
                    it.setdefault("id", f"{section_or_item_id}-{uuid.uuid4().hex[:8]}")
                    nested.append(it)
                return True
    return False


def document_outline(content: dict[str, Any]) -> list[dict[str, Any]]:
    outline = []
    for section in content.get("sections") or []:
        items = section.get("items") or []
        outline.append(
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "item_count": len(items) if isinstance(items, list) else 0,
                "item_titles": [
                    it.get("title") or it.get("id")
                    for it in items
                    if isinstance(it, dict)
                ][:12],
            }
        )
    return outline


def section_summaries(content: dict[str, Any], limit_chars: int = 400) -> list[dict[str, Any]]:
    out = []
    for section in content.get("sections") or []:
        items = section.get("items") or []
        titles = []
        for it in items:
            if isinstance(it, dict):
                titles.append(str(it.get("title") or it.get("id") or ""))
        blob = "; ".join(t for t in titles if t)
        out.append(
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "summary": blob[:limit_chars],
            }
        )
    return out


def _walk_items(items: list) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        found.append(item)
        for key in ("items", "frames", "segments"):
            nested = item.get(key)
            if isinstance(nested, list):
                found.extend(_walk_items(nested))
    return found


def _normalize_item(item: Any, parent_id: str, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": str(item), "content": item}
    item.setdefault("id", f"{parent_id}_{index + 1}_{uuid.uuid4().hex[:6]}")
    item.setdefault("status", ItemStatus.PROPOSED.value)
    if "title" not in item:
        item["title"] = item.get("name") or item.get("id")
    return item


def _ensure_nested_ids(items: list, parent_id: str) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("items", "frames", "segments"):
            nested = item.get(key)
            if not isinstance(nested, list):
                continue
            normalized = []
            for i, child in enumerate(nested):
                child_id_prefix = f"{item.get('id') or parent_id}_{key}"
                if not isinstance(child, dict):
                    child = {"title": str(child)}
                child.setdefault("id", f"{child_id_prefix}_{i + 1}_{uuid.uuid4().hex[:6]}")
                normalized.append(child)
            item[key] = normalized
            _ensure_nested_ids(normalized, item["id"])


def _wrap_as_items(value: Any, section_id: str) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [{**value, "id": value.get("id") or f"{section_id}_1"}]
    return [{"id": f"{section_id}_1", "title": str(value), "content": value}]


def _promote_keys_to_sections(doc: dict[str, Any], specs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    sections = []
    for sid, title in specs:
        raw = doc.get(sid)
        items = _wrap_as_items(raw, sid) if raw is not None else []
        sections.append({"id": sid, "title": title, "items": items})
    return sections


def _guess_step(doc: dict[str, Any]) -> str:
    ids = {s.get("id") for s in (doc.get("sections") or []) if isinstance(s, dict)}
    if "training_mode" in ids or "passport" in ids:
        return StepType.SCENARIO_PLAN.value
    return StepType.PROFESSION_MAP.value
