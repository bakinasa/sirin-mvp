"""Whether the previous pipeline step has enough data to generate the next one."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import PIPELINE_ORDER, StepType, previous_step_allows_generate
from app.models import PipelineStep


class PipelineGateError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def assert_can_run_step(
    db: AsyncSession, project_id, step_type: str
) -> PipelineStep:
    """
    Previous step must exist. Brief is enough as-is; later steps need a current artifact
    (approved/locked not required, so a step can be rebuilt after returning to an earlier one).
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
        if not previous_step_allows_generate(prev.value, bool(prev_step.current_artifact_id)):
            raise PipelineGateError(
                f"Шаг «{prev.value}» должен иметь документ перед запуском «{step_type}»."
            )

    return current
