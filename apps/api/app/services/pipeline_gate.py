"""HITL gate: next AI step cannot run until previous step is Approved."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PIPELINE_ORDER, StepStatus, StepType
from app.models import PipelineStep


class PipelineGateError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def assert_can_run_step(
    db: AsyncSession, project_id, step_type: str
) -> PipelineStep:
    """
    Invariant: for step at index i > 0, step i-1 must be Approved (or Locked).
    Brief is filled manually; export only needs storyboard approved.
    """
    try:
        target = StepType(step_type)
    except ValueError as exc:
        raise PipelineGateError(f"Unknown step_type: {step_type}") from exc

    if target not in PIPELINE_ORDER:
        raise PipelineGateError(f"Step not in pipeline: {step_type}")

    result = await db.execute(
        select(PipelineStep).where(PipelineStep.project_id == project_id)
    )
    steps = {s.step_type: s for s in result.scalars().all()}

    current = steps.get(target.value)
    if current is None:
        raise PipelineGateError(f"Pipeline step not initialized: {step_type}")

    idx = PIPELINE_ORDER.index(target)
    if idx > 0:
        prev = PIPELINE_ORDER[idx - 1]
        prev_step = steps.get(prev.value)
        if prev_step is None:
            raise PipelineGateError(f"Previous step missing: {prev.value}")
        if prev_step.status not in (StepStatus.APPROVED, StepStatus.LOCKED):
            raise PipelineGateError(
                f"Шаг «{prev.value}» должен быть Approved перед запуском «{step_type}». "
                f"Текущий статус: {prev_step.status}"
            )

    return current
