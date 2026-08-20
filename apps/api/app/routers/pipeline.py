from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Artifact, PipelineRun, PipelineStep, PromptEditHistory, User
from app.services.artifacts import approve_artifact, reject_artifact, update_artifact
from app.services.generation import create_pipeline_run
from app.services.pipeline_gate import PipelineGateError
from app.services.prompt_assembler import assemble_prompt
from app.services.projects import ensure_v2_pipeline, visible_steps
from app.schemas import (
    ArtifactAction,
    ArtifactOut,
    ArtifactUpdate,
    ContextBundleOut,
    PipelineRunOut,
    PipelineRunRequest,
    PipelineStepOut,
)

router = APIRouter(tags=["pipeline"])


@router.get("/projects/{project_id}/pipeline", response_model=list)
async def get_pipeline(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PipelineStep)
        .where(PipelineStep.project_id == project_id)
        .order_by(PipelineStep.order_index)
    )
    existing = list(result.scalars().all())
    if not existing:
        raise HTTPException(404, "Pipeline not found")
    steps = await ensure_v2_pipeline(db, project_id)
    return [PipelineStepOut.model_validate(s) for s in visible_steps(steps)]


@router.post("/projects/{project_id}/pipeline/run", response_model=PipelineRunOut)
async def run_pipeline_step(
    project_id: UUID,
    body: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await create_pipeline_run(
            db,
            project_id=project_id,
            user_id=user.id,
            step_type=body.step_type,
            operator_prompt=body.operator_prompt,
            primary_model_id=body.primary_model_id,
            fallback_model_id=body.fallback_model_id,
            wait=False,
        )
    except PipelineGateError as exc:
        raise HTTPException(400, exc.message) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@router.get("/projects/{project_id}/pipeline/runs/{run_id}", response_model=PipelineRunOut)
async def get_run(
    project_id: UUID,
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ = user
    run = await db.get(PipelineRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/projects/{project_id}/pipeline/runs", response_model=list[PipelineRunOut])
async def list_runs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
    )
    return result.scalars().all()


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(
    project_id: UUID,
    step_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Artifact).where(Artifact.project_id == project_id)
    if step_type:
        q = q.where(Artifact.step_type == step_type)
    q = q.order_by(Artifact.version.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return artifact


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def patch_artifact(
    artifact_id: UUID,
    body: ArtifactUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    try:
        return await update_artifact(db, artifact, user.id, body.content, body.comment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/artifacts/{artifact_id}/approve", response_model=ArtifactOut)
async def approve(
    artifact_id: UUID,
    body: ArtifactAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return await approve_artifact(db, artifact, user.id, body.comment)


@router.post("/artifacts/{artifact_id}/reject", response_model=ArtifactOut)
async def reject(
    artifact_id: UUID,
    body: ArtifactAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return await reject_artifact(db, artifact, user.id, body.comment)


@router.post("/artifacts/{artifact_id}/regenerate", response_model=PipelineRunOut)
async def regenerate(
    artifact_id: UUID,
    body: PipelineRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    try:
        return await create_pipeline_run(
            db,
            project_id=artifact.project_id,
            user_id=user.id,
            step_type=artifact.step_type,
            operator_prompt=body.operator_prompt if body else None,
            primary_model_id=body.primary_model_id if body else None,
            fallback_model_id=body.fallback_model_id if body else None,
            wait=False,
        )
    except PipelineGateError as exc:
        raise HTTPException(400, exc.message) from exc


@router.get("/projects/{project_id}/prompt-preview", response_model=ContextBundleOut)
async def prompt_preview(
    project_id: UUID,
    step_type: str,
    operator_prompt: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assembled = await assemble_prompt(db, project_id, step_type, operator_prompt)
    return ContextBundleOut(
        step_type=step_type,
        blocks=assembled["context_bundle"]["blocks"],
        prompt_template_version=assembled["prompt_template_version"],
        system_prompt=assembled["system_prompt"],
        operator_prompt=assembled["operator_prompt"],
        context_text=assembled.get("context_text") or "",
        user_message=assembled.get("user_message") or "",
    )


@router.get("/projects/{project_id}/prompt-history")
async def prompt_history(
    project_id: UUID,
    step_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(PromptEditHistory).where(PromptEditHistory.project_id == project_id)
    if step_type:
        q = q.where(PromptEditHistory.step_type == step_type)
    q = q.order_by(PromptEditHistory.created_at.desc()).limit(20)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "step_type": r.step_type,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
