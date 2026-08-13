"""Artifact approve / reject / edit helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from diff_match_patch import diff_match_patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ArtifactStatus, StepStatus, StepType
from app.models import Artifact, Brief, HumanEdit, PipelineStep


async def update_artifact(
    db: AsyncSession,
    artifact: Artifact,
    editor_id: UUID,
    new_content,
    comment: str = "",
) -> Artifact:
    if getattr(artifact, "frozen", False):
        raise ValueError("Версия зафиксирована")
    before = artifact.content
    dmp = diff_match_patch()
    before_s = json.dumps(before, ensure_ascii=False, sort_keys=True)
    after_s = json.dumps(new_content, ensure_ascii=False, sort_keys=True)
    diffs = dmp.diff_main(before_s, after_s)
    dmp.diff_cleanupSemantic(diffs)
    patch = dmp.patch_toText(dmp.patch_make(before_s, diffs))

    db.add(
        HumanEdit(
            artifact_id=artifact.id,
            editor_id=editor_id,
            diff=patch,
            before_content=before,
            after_content=new_content,
            comment=comment,
        )
    )
    artifact.content = new_content
    artifact.status = ArtifactStatus.EDITED.value
    if getattr(artifact, "frozen", False):
        raise ValueError("Версия зафиксирована")
    artifact.change_type = "manual"
    await _set_step_status(db, artifact.project_id, artifact.step_type, StepStatus.UNDER_REVIEW)
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def approve_artifact(
    db: AsyncSession, artifact: Artifact, user_id: UUID, comment: str = ""
) -> Artifact:
    artifact.status = ArtifactStatus.APPROVED.value
    artifact.approved_by = user_id
    artifact.approved_at = datetime.now(timezone.utc)
    if comment:
        db.add(
            HumanEdit(
                artifact_id=artifact.id,
                editor_id=user_id,
                diff="",
                before_content=artifact.content,
                after_content=artifact.content,
                comment=f"APPROVED: {comment}",
            )
        )

    result = await db.execute(
        select(PipelineStep).where(
            PipelineStep.project_id == artifact.project_id,
            PipelineStep.step_type == artifact.step_type,
        )
    )
    step = result.scalar_one_or_none()
    if step:
        step.approved_artifact_id = artifact.id
        step.current_artifact_id = artifact.id
        step.status = StepStatus.APPROVED.value

    # Keep brief status in sync when approving brief via artifact path (n/a) —
    # brief approve is separate endpoint helper.
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def reject_artifact(
    db: AsyncSession, artifact: Artifact, user_id: UUID, comment: str = ""
) -> Artifact:
    artifact.status = ArtifactStatus.REJECTED.value
    db.add(
        HumanEdit(
            artifact_id=artifact.id,
            editor_id=user_id,
            diff="",
            before_content=artifact.content,
            after_content=artifact.content,
            comment=f"REJECTED: {comment}",
        )
    )
    await _set_step_status(db, artifact.project_id, artifact.step_type, StepStatus.NEEDS_REVISION)
    await db.flush()
    await db.refresh(artifact)
    return artifact


async def approve_brief(db: AsyncSession, project_id: UUID) -> Brief:
    result = await db.execute(select(Brief).where(Brief.project_id == project_id))
    brief = result.scalar_one_or_none()
    if brief is None:
        raise ValueError("Brief not found")
    brief.status = StepStatus.APPROVED.value
    await _set_step_status(db, project_id, StepType.BRIEF.value, StepStatus.APPROVED)
    await db.flush()
    await db.refresh(brief)
    return brief


async def approve_expert_feedback_step(db: AsyncSession, project_id: UUID) -> PipelineStep:
    """Mark expert feedback collection as approved when operator finishes gathering."""
    result = await db.execute(
        select(PipelineStep).where(
            PipelineStep.project_id == project_id,
            PipelineStep.step_type == StepType.EXPERT_FEEDBACK.value,
        )
    )
    step = result.scalar_one()
    step.status = StepStatus.APPROVED.value
    await db.flush()
    return step


async def _set_step_status(
    db: AsyncSession, project_id: UUID, step_type: str, status: StepStatus
) -> None:
    result = await db.execute(
        select(PipelineStep).where(
            PipelineStep.project_id == project_id,
            PipelineStep.step_type == step_type,
        )
    )
    step = result.scalar_one_or_none()
    if step:
        step.status = status.value
