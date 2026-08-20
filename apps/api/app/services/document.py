"""Block-structured artifact helpers: stable ids, item lookup, patches."""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Optional

from app.domain.enums import ItemStatus, StepType
from app.services.json_content import recover_sections_from_payload

_BLOCK_STEP_TYPES = frozenset(
    {StepType.PROFESSION_MAP.value, StepType.SCENARIO_PLAN.value}
)

# Canonical section order for generation. Extra sections from old artifacts are kept at the end.
FIXED_SECTIONS: dict[str, list[tuple[str, str]]] = {
    StepType.PROFESSION_MAP.value: [
        ("work_storylines", "Варианты работ и сюжет"),
        ("assessment_points", "Навыки и точки оценки"),
        ("expert_questions", "Вопросы экспертам"),
    ],
    StepType.SCENARIO_PLAN.value: [
        ("training_scenes", "Обучающие сцены"),
        ("diagnostic_scenes", "Диагностические сцены"),
    ],
}

_SECTION_ALIASES: dict[str, str] = {
    "work_type": "work_storylines",
    "work_variants": "work_storylines",
    "preliminary_storylines": "work_storylines",
    "skills": "assessment_points",
    "evaluated_skills": "assessment_points",
    "errors": "assessment_points",
    "segment_ideas": "work_storylines",
    "passport": "scenario_passport",
    "training_mode": "training_scenes",
    "diagnostic_mode": "diagnostic_scenes",
    "regulations": "rules_and_regulations",
    "props": "props_and_locations",
    "shooting_notes": "shooting_plan",
    "constraints": "shooting_plan",
}

# Top-level keys that are not promoted into sections when parsing legacy shapes.
_DOC_META_KEYS = frozenset(
    {
        "sections",
        "title",
        "clarifications_needed",
        "_mock",
        "_generation",
        "raw",
        "raw_text",
        "summary",
        "summary_ru",
    }
)


def empty_document(step_type: str) -> dict[str, Any]:
    spec = FIXED_SECTIONS.get(step_type)
    if spec:
        return {
            "sections": [{"id": sid, "title": title, "items": []} for sid, title in spec],
            "clarifications_needed": [],
        }
    return {"sections": []}


def ensure_ids(content: Any, step_type: str) -> dict[str, Any]:
    """Normalize LLM output into a sections[] document with stable ids.

    Known pipeline stages use a fixed section order from the prompt.
    Extra sections from older artifacts are kept after the canonical ones.
    """
    if not isinstance(content, dict):
        content = {"raw": content}

    if step_type not in _BLOCK_STEP_TYPES:
        return content

    doc = copy.deepcopy(content)
    recovered = recover_sections_from_payload(doc)
    if recovered is not None:
        doc = recovered

    sections = doc.get("sections")
    if not isinstance(sections, list) or not sections:
        sections = _promote_keys_to_sections(doc)

    used_section_ids: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for idx, section in enumerate(sections):
        if not isinstance(section, dict):
            section = {"title": str(section), "items": []}
        ordered.append(_normalize_section(section, idx, used_section_ids))

    spec = FIXED_SECTIONS.get(step_type)
    if spec:
        ordered = _apply_canonical_sections(ordered, spec)

    doc["sections"] = ordered
    if "clarifications_needed" not in doc:
        doc["clarifications_needed"] = []
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


_SECTION_ITEM_DEFAULTS: dict[str, dict[str, Any]] = {
    "work_storylines": {"story_steps": [], "attention_focus": ""},
    "assessment_points": {"errors": []},
    "expert_questions": {"why_needed": "", "answer": ""},
    "training_scenes": {
        "actors": "",
        "location": "",
        "frames": [],
        "audio_text": "",
        "regulations": "",
        "props": "",
    },
    "diagnostic_scenes": {
        "actors": "",
        "location": "",
        "frames": [],
        "violation_categories": [],
        "regulations": "",
        "props": "",
    },
}


def item_field_template(section_items: list[Any], section_id: str = "") -> dict[str, Any]:
    """Empty field shell matching the first sibling item in a section."""
    skip = {"id", "status"}
    template: dict[str, Any] = {"title": "", "description": ""}
    template.update(_SECTION_ITEM_DEFAULTS.get(section_id, {}))
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
            elif isinstance(value, list):
                template.setdefault(key, [])
        break
    return template


def extract_expert_qa(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Expert questions with answers; empty answer becomes an explicit placeholder."""
    items: list[dict[str, Any]] = []
    for section in content.get("sections") or []:
        if not isinstance(section, dict) or section.get("id") != "expert_questions":
            continue
        for it in section.get("items") or []:
            if not isinstance(it, dict):
                continue
            answer = str(it.get("answer") or "").strip()
            items.append(
                {
                    "title": it.get("title") or "",
                    "description": it.get("description") or "",
                    "why_needed": it.get("why_needed") or "",
                    "answer": answer if answer else "ответа нет",
                }
            )
    return items


def _section_item_titles(content: dict[str, Any], section_id: str) -> list[str]:
    titles: list[str] = []
    for section in content.get("sections") or []:
        if not isinstance(section, dict) or section.get("id") != section_id:
            continue
        for it in section.get("items") or []:
            if isinstance(it, dict):
                title = str(it.get("title") or "").strip()
                if title:
                    titles.append(title)
    return titles


def compact_profession_map_for_scenario(content: dict[str, Any]) -> dict[str, Any]:
    """Shrink plot JSON for scenario generation — keep titles/errors, drop noise."""
    sections_out: list[dict[str, Any]] = []
    for section in content.get("sections") or []:
        if not isinstance(section, dict):
            continue
        sid = section.get("id")
        items_in = section.get("items") or []
        items_out: list[dict[str, Any]] = []
        for it in items_in:
            if not isinstance(it, dict):
                continue
            if sid == "work_storylines":
                steps = it.get("story_steps") or []
                if isinstance(steps, list) and len(steps) > 8:
                    steps = steps[:8]
                items_out.append(
                    {
                        "title": it.get("title") or "",
                        "description": str(it.get("description") or "")[:400],
                        "story_steps": steps,
                        "attention_focus": str(it.get("attention_focus") or "")[:240],
                    }
                )
            elif sid == "assessment_points":
                errors = it.get("errors") or []
                if isinstance(errors, list) and len(errors) > 6:
                    errors = errors[:6]
                slim_errors = []
                for err in errors:
                    if not isinstance(err, dict):
                        continue
                    cues = err.get("visual_cues") or []
                    if isinstance(cues, list) and len(cues) > 3:
                        cues = cues[:3]
                    slim_errors.append(
                        {
                            "error": str(err.get("error") or "")[:220],
                            "correct": str(err.get("correct") or "")[:220],
                            "visual_cues": cues,
                        }
                    )
                items_out.append(
                    {
                        "title": it.get("title") or "",
                        "description": str(it.get("description") or "")[:240],
                        "errors": slim_errors,
                    }
                )
            elif sid == "expert_questions":
                items_out.append(
                    {
                        "title": it.get("title") or "",
                        "why_needed": str(it.get("why_needed") or "")[:200],
                        "answer": str(it.get("answer") or "")[:500],
                    }
                )
        if sid in ("work_storylines", "assessment_points", "expert_questions"):
            sections_out.append({"id": sid, "title": section.get("title") or sid, "items": items_out})
    return {"sections": sections_out}


def validate_scenario_parity(
    map_content: dict[str, Any], scenario_content: dict[str, Any]
) -> list[str]:
    """Compare work_storylines count/titles vs training/diagnostic scenes."""
    warnings: list[str] = []
    storylines = _section_item_titles(map_content, "work_storylines")
    training = _section_item_titles(scenario_content, "training_scenes")
    diagnostic = _section_item_titles(scenario_content, "diagnostic_scenes")

    if not storylines:
        return warnings

    expected = len(storylines)
    if len(training) != expected:
        warnings.append(
            f"Обучающих сцен {len(training)}, а видов работ в сюжете {expected}. "
            "Ожидается по одной обучающей сцене на каждый вид работ."
        )
    if len(diagnostic) != expected:
        warnings.append(
            f"Диагностических сцен {len(diagnostic)}, а видов работ в сюжете {expected}. "
            "Ожидается по одной диагностической сцене на каждый вид работ."
        )

    story_set = set(storylines)
    train_set = set(training)
    diag_set = set(diagnostic)
    missing_train = story_set - train_set
    missing_diag = story_set - diag_set
    if missing_train:
        warnings.append(f"Пропущены обучающие сцены для видов работ: {', '.join(sorted(missing_train))}")
    if missing_diag:
        warnings.append(f"Пропущены диагностические сцены для видов работ: {', '.join(sorted(missing_diag))}")

    extra_train = train_set - story_set
    extra_diag = diag_set - story_set
    if extra_train:
        warnings.append(f"Лишние обучающие сцены (нет в сюжете): {', '.join(sorted(extra_train))}")
    if extra_diag:
        warnings.append(f"Лишние диагностические сцены (нет в сюжете): {', '.join(sorted(extra_diag))}")

    return warnings


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


def _normalize_section(section: dict[str, Any], index: int, used_ids: set[str]) -> dict[str, Any]:
    section = copy.deepcopy(section)
    title = str(section.get("title") or section.get("name") or f"Раздел {index + 1}").strip()
    sid = section.get("id")
    if sid:
        sid = str(sid).strip()
    else:
        sid = _slug_id(title, f"section_{index + 1}")
    sid = _unique_id(sid, used_ids)
    used_ids.add(sid)

    section["id"] = sid
    section["title"] = title
    items = section.get("items")
    if not isinstance(items, list):
        items = _wrap_as_items(items, sid)
    section["items"] = [_normalize_item(it, sid, i) for i, it in enumerate(items)]
    _ensure_nested_ids(section["items"], sid)
    return section


def _slug_id(text: str, fallback: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s\-]+", "_", s).strip("_")
    return (s or fallback)[:80]


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


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


def _promote_keys_to_sections(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Legacy: top-level keys become sections when sections[] is missing."""
    sections = []
    for key, raw in doc.items():
        if key in _DOC_META_KEYS:
            continue
        title = str(key).replace("_", " ").strip().title()
        items = _wrap_as_items(raw, str(key))
        sections.append({"id": str(key), "title": title, "items": items})
    return sections


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


def _guess_step(doc: dict[str, Any]) -> str:
    """Best-effort step type when only document JSON is available."""
    ids = {s.get("id") for s in (doc.get("sections") or []) if isinstance(s, dict)}
    titles = " ".join(
        str(s.get("title") or "") for s in (doc.get("sections") or []) if isinstance(s, dict)
    ).lower()
    scenario_ids = {
        "scenario_passport",
        "training_scenes",
        "diagnostic_scenes",
        "passport",
        "training_mode",
        "diagnostic_mode",
        "microtexts",
        "shooting_plan",
    }
    if ids & scenario_ids or "сценар" in titles or "обучен" in titles:
        return StepType.SCENARIO_PLAN.value
    return StepType.PROFESSION_MAP.value


def _apply_canonical_sections(
    sections: list[dict[str, Any]], spec: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in sections:
        sid = str(section.get("id") or "")
        sid = _SECTION_ALIASES.get(sid, sid)
        section = {**section, "id": sid}
        if sid in seen:
            existing = next(s for s in remapped if s.get("id") == sid)
            extra_items = section.get("items") or []
            if extra_items:
                existing.setdefault("items", []).extend(extra_items)
            continue
        seen.add(sid)
        remapped.append(section)

    by_id = {str(s.get("id")): s for s in remapped}
    ordered: list[dict[str, Any]] = []
    used: set[str] = set()
    for sid, title in spec:
        if sid in by_id:
            sec = by_id[sid]
            sec["id"] = sid
            if not str(sec.get("title") or "").strip():
                sec["title"] = title
            ordered.append(sec)
        else:
            ordered.append({"id": sid, "title": title, "items": []})
        used.add(sid)
    for section in remapped:
        sid = str(section.get("id") or "")
        if sid and sid not in used:
            ordered.append(section)
            used.add(sid)
    return ordered
