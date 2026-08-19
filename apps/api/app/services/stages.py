"""Profession map / scenario document operations: items, freeze, restore."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ArtifactStatus, ChangeType, ItemStatus, StepStatus, StepType, later_pipeline_steps
from app.models import Artifact, ArtifactPatch, PipelineStep
from app.services.document import (
    append_section_items,
    apply_patch_json,
    ensure_ids,
    find_item,
    item_field_template,
    set_item_status,
)
from app.services.generation import _next_version
from app.services.pipeline_gate import PipelineGateError


class StageEditError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def get_current_artifact(
    db: AsyncSession, project_id: UUID, step_type: str
) -> Artifact | None:
    step = await _get_step(db, project_id, step_type)
    if step and step.current_artifact_id:
        return await db.get(Artifact, step.current_artifact_id)
    result = await db.execute(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.step_type == step_type)
        .order_by(Artifact.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def add_section_item(
    db: AsyncSession,
    project_id: UUID,
    step_type: str,
    section_id: str,
    *,
    title: str,
    description: str = "",
    extra: dict | None = None,
) -> tuple[Artifact, dict]:
    artifact = await _editable_artifact(db, project_id, step_type)
    content = copy.deepcopy(artifact.content) if isinstance(artifact.content, dict) else {}
    section = next(
        (s for s in (content.get("sections") or []) if isinstance(s, dict) and s.get("id") == section_id),
        None,
    )
    if section is None:
        raise StageEditError(f"Раздел {section_id} не найден")

    items = section.get("items") or []
    if not isinstance(items, list):
        items = []
    new_item = item_field_template(items, section_id)
    new_item["title"] = title.strip()
    new_item["description"] = description.strip()
    if extra:
        new_item.update(extra)

    created_ids = append_section_items(
        content,
        section_id,
        [new_item],
        default_status=ItemStatus.EDITED.value,
    )
    if not created_ids:
        raise StageEditError(f"Не удалось добавить пункт в раздел {section_id}")

    artifact.content = content
    artifact.status = ArtifactStatus.EDITED.value
    await db.flush()
    await db.refresh(artifact)

    saved = find_item(content, created_ids[0])
    if saved is None:
        raise StageEditError("Пункт создан, но не найден в документе")
    return artifact, saved


async def patch_item(
    db: AsyncSession,
    project_id: UUID,
    step_type: str,
    item_id: str,
    new_item: dict,
) -> Artifact:
    artifact = await _editable_artifact(db, project_id, step_type)
    content = copy.deepcopy(artifact.content) if isinstance(artifact.content, dict) else {}
    item = find_item(content, item_id)
    if item is None:
        raise StageEditError(f"Элемент {item_id} не найден")
    item.update(new_item)
    item["id"] = item_id
    item["status"] = ItemStatus.EDITED.value
    artifact.content = content
    artifact.status = ArtifactStatus.EDITED.value
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def set_item_decision(
    db: AsyncSession, project_id: UUID, step_type: str, item_id: str, status: str
) -> Artifact:
    artifact = await _editable_artifact(db, project_id, step_type)
    content = copy.deepcopy(artifact.content) if isinstance(artifact.content, dict) else {}
    if not set_item_status(content, item_id, status):
        raise StageEditError(f"Элемент {item_id} не найден")
    artifact.content = content
    artifact.status = ArtifactStatus.EDITED.value
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def freeze_artifact(
    db: AsyncSession, artifact: Artifact, summary: str = ""
) -> Artifact:
    artifact.frozen = True
    if summary:
        artifact.change_summary = summary
    step = await _get_step(db, artifact.project_id, artifact.step_type)
    if step:
        step.approved_artifact_id = artifact.id
        step.current_artifact_id = artifact.id
        step.status = StepStatus.LOCKED.value
    artifact.status = ArtifactStatus.APPROVED.value
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def save_version(
    db: AsyncSession, artifact: Artifact, summary: str = ""
) -> Artifact:
    version = await _next_version(db, artifact.project_id, artifact.step_type)
    snapshot = Artifact(
        project_id=artifact.project_id,
        step_type=artifact.step_type,
        parent_artifact_id=artifact.id,
        content=copy.deepcopy(artifact.content),
        format=artifact.format,
        version=version,
        status=ArtifactStatus.EDITED.value,
        change_type=ChangeType.MANUAL.value,
        change_summary=summary or "Saved version",
        frozen=False,
    )
    db.add(snapshot)
    await db.flush()
    step = await _get_step(db, artifact.project_id, artifact.step_type)
    if step:
        step.current_artifact_id = snapshot.id
        if step.status == StepStatus.LOCKED.value:
            pass
        else:
            step.status = StepStatus.UNDER_REVIEW.value
    await db.refresh(snapshot)
    return snapshot


async def restore_version(
    db: AsyncSession, current: Artifact, source: Artifact
) -> Artifact:
    if source.project_id != current.project_id or source.step_type != current.step_type:
        raise StageEditError("Версия относится к другому документу")
    version = await _next_version(db, current.project_id, current.step_type)
    restored = Artifact(
        project_id=current.project_id,
        step_type=current.step_type,
        parent_artifact_id=source.id,
        content=copy.deepcopy(source.content),
        format=source.format,
        version=version,
        status=ArtifactStatus.EDITED.value,
        change_type=ChangeType.RESTORE.value,
        change_summary=f"Restored from v{source.version}",
        frozen=False,
    )
    db.add(restored)
    await db.flush()
    step = await _get_step(db, current.project_id, current.step_type)
    if step:
        if step.status == StepStatus.LOCKED.value:
            await unlock_step_and_outdate_later(db, current.project_id, current.step_type)
        step.current_artifact_id = restored.id
        step.status = StepStatus.UNDER_REVIEW.value
    await db.refresh(restored)
    return restored


async def new_map_edition(db: AsyncSession, project_id: UUID) -> dict:
    """Unlock profession_map and mark later steps outdated (artifacts kept)."""
    return await unlock_step_and_outdate_later(
        db, project_id, StepType.PROFESSION_MAP.value, required=True
    )


async def unlock_step_and_outdate_later(
    db: AsyncSession,
    project_id: UUID,
    step_type: str,
    *,
    required: bool = True,
    unfreeze_current: bool = True,
) -> dict:
    """Re-open a step in place and mark subsequent steps with artifacts as outdated.

    Does not clear current_artifact_id — previous documents stay available.
    """
    result = await db.execute(select(PipelineStep).where(PipelineStep.project_id == project_id))
    steps = {s.step_type: s for s in result.scalars().all()}
    current = steps.get(step_type)
    if current is None:
        if required:
            raise StageEditError(f"Шаг {step_type} не найден")
        return {"unlocked": None, "outdated": [], "warning": None}

    if step_type != StepType.BRIEF.value:
        current.status = StepStatus.UNDER_REVIEW.value
        if unfreeze_current and current.current_artifact_id:
            art = await db.get(Artifact, current.current_artifact_id)
            if art:
                art.frozen = False

    outdated = await mark_later_steps_outdated(db, project_id, step_type, steps=steps)
    await db.flush()
    warning = None
    if outdated:
        warning = "Последующие шаги помечены как устаревшие; артефакты сохранены."
    return {
        "unlocked": step_type,
        "status": current.status,
        "outdated": outdated,
        "profession_map_status": steps.get(StepType.PROFESSION_MAP.value).status
        if steps.get(StepType.PROFESSION_MAP.value)
        else None,
        "scenario_plan_status": steps.get(StepType.SCENARIO_PLAN.value).status
        if steps.get(StepType.SCENARIO_PLAN.value)
        else None,
        "warning": warning,
    }


async def mark_later_steps_outdated(
    db: AsyncSession,
    project_id: UUID,
    step_type: str,
    *,
    steps: dict[str, PipelineStep] | None = None,
) -> list[str]:
    """Set later pipeline steps that already have an artifact to outdated. Keep artifact ids."""
    if steps is None:
        result = await db.execute(select(PipelineStep).where(PipelineStep.project_id == project_id))
        steps = {s.step_type: s for s in result.scalars().all()}
    outdated: list[str] = []
    for later in later_pipeline_steps(step_type):
        step = steps.get(later)
        if step is None:
            continue
        if step.current_artifact_id or step.approved_artifact_id:
            step.status = StepStatus.OUTDATED.value
            outdated.append(later)
    await db.flush()
    return outdated


async def apply_patch(
    db: AsyncSession, patch: ArtifactPatch, user_id: UUID
) -> Artifact:
    if patch.status != "draft":
        raise StageEditError("Патч уже обработан")
    artifact = await _editable_artifact(db, patch.project_id, patch.stage_type)
    content = copy.deepcopy(artifact.content) if isinstance(artifact.content, dict) else {}
    new_content = apply_patch_json(content, patch.patch_json)
    new_content = ensure_ids(new_content, patch.stage_type)

    version = await _next_version(db, patch.project_id, patch.stage_type)
    new_art = Artifact(
        project_id=patch.project_id,
        step_type=patch.stage_type,
        parent_artifact_id=artifact.id,
        content=new_content,
        format="json",
        version=version,
        status=ArtifactStatus.EDITED.value,
        change_type=ChangeType.AI_PATCH.value,
        change_summary=(patch.instruction or "AI patch")[:500],
        frozen=False,
    )
    db.add(new_art)
    await db.flush()
    patch.status = "applied"
    patch.artifact_id = new_art.id
    step = await _get_step(db, patch.project_id, patch.stage_type)
    if step:
        step.current_artifact_id = new_art.id
        step.status = StepStatus.UNDER_REVIEW.value
    await _append_decision(
        db, patch.project_id, patch.stage_type, patch.instruction, user_id
    )
    await db.refresh(new_art)
    return new_art


async def discard_patch(db: AsyncSession, patch: ArtifactPatch) -> ArtifactPatch:
    if patch.status != "draft":
        raise StageEditError("Патч уже обработан")
    patch.status = "discarded"
    await db.flush()
    return patch


async def _editable_artifact(
    db: AsyncSession, project_id: UUID, step_type: str
) -> Artifact:
    artifact = await get_current_artifact(db, project_id, step_type)
    if artifact is None:
        raise StageEditError("Нет текущего документа")
    step = await _get_step(db, project_id, step_type)
    needs_unlock = bool(artifact.frozen) or (step is not None and step.status == StepStatus.LOCKED.value)
    if needs_unlock:
        await unlock_step_and_outdate_later(db, project_id, step_type)
        await db.refresh(artifact)
    return artifact


async def _get_step(
    db: AsyncSession, project_id: UUID, step_type: str
) -> PipelineStep | None:
    result = await db.execute(
        select(PipelineStep).where(
            PipelineStep.project_id == project_id, PipelineStep.step_type == step_type
        )
    )
    return result.scalar_one_or_none()


async def _append_decision(
    db: AsyncSession, project_id: UUID, stage_type: str, text: str, user_id: UUID
) -> None:
    from app.models import StageChatSession

    result = await db.execute(
        select(StageChatSession).where(
            StageChatSession.project_id == project_id,
            StageChatSession.stage_type == stage_type,
        )
    )
    sessions = result.scalars().all()
    for session in sessions:
        summary = dict(session.summary_json or {})
        decisions = list(summary.get("accepted_decisions") or [])
        decisions.append({"text": text, "at": datetime.now(timezone.utc).isoformat()})
        summary["accepted_decisions"] = decisions[-30:]
        session.summary_json = summary
    _ = user_id
    _ = PipelineGateError
