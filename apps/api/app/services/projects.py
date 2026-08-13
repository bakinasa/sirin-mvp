"""Project lifecycle helpers: create project + initialize pipeline steps."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PIPELINE_ORDER, StepStatus, StepType, VISIBLE_STEP_TYPES
from app.models import Brief, PipelineStep, Project

DEFAULT_LEARNING_OBJECTIVES = (
    "Обучение безопасному и корректному выполнению рабочей операции. "
    "Диагностика навыка через поиск нарушений."
)

DEFAULT_BRIEF = {
    "work_operation": "",
    "task_description": "",
    "learning_objectives": DEFAULT_LEARNING_OBJECTIVES,
    "notes": "",
    "customer_notes": "",
}


async def create_project_with_pipeline(
    db: AsyncSession, owner_id: UUID, data: dict
) -> Project:
    project = Project(owner_id=owner_id, **data)
    db.add(project)
    await db.flush()

    brief = Brief(
        project_id=project.id,
        content_json=dict(DEFAULT_BRIEF),
        version=1,
        status=StepStatus.DRAFT.value,
    )
    db.add(brief)

    for idx, step_type in enumerate(PIPELINE_ORDER):
        step = PipelineStep(
            project_id=project.id,
            step_type=step_type.value,
            order_index=idx,
            status=StepStatus.DRAFT.value,
        )
        db.add(step)

    await db.flush()
    return project


async def ensure_v2_pipeline(db: AsyncSession, project_id: UUID) -> list[PipelineStep]:
    """Add missing v2 steps for projects created before the 4-step pipeline."""
    result = await db.execute(
        select(PipelineStep).where(PipelineStep.project_id == project_id)
    )
    steps = list(result.scalars().all())
    by_type = {s.step_type: s for s in steps}

    changed = False
    for idx, step_type in enumerate(PIPELINE_ORDER):
        existing = by_type.get(step_type.value)
        if existing is None:
            step = PipelineStep(
                project_id=project_id,
                step_type=step_type.value,
                order_index=idx,
                status=StepStatus.DRAFT.value,
            )
            db.add(step)
            steps.append(step)
            changed = True
        elif existing.order_index != idx:
            existing.order_index = idx
            changed = True

    if changed:
        await db.flush()
        result = await db.execute(
            select(PipelineStep).where(PipelineStep.project_id == project_id)
        )
        steps = list(result.scalars().all())
    return steps


def visible_steps(steps: list[PipelineStep]) -> list[PipelineStep]:
    filtered = [s for s in steps if s.step_type in VISIBLE_STEP_TYPES]
    return sorted(filtered, key=lambda s: s.order_index)
