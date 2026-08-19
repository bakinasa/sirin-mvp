from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.domain.enums import ProjectStatus, StepType
from app.models import Brief, HumanEdit, PipelineRun, Project, User
from app.schemas import (
    BriefOut,
    BriefUpdate,
    ProjectCreate,
    ProjectMetricsOut,
    ProjectOut,
    ProjectUpdate,
)
from app.services.artifacts import approve_brief
from app.services.projects import create_project_with_pipeline
from app.services.stages import unlock_step_and_outdate_later

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.status != ProjectStatus.ARCHIVED.value).order_by(Project.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await create_project_with_pipeline(db, user.id, body.model_dump())
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    await unlock_step_and_outdate_later(db, project_id, StepType.BRIEF.value, required=False)
    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete: archive so the project disappears from the dashboard."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    project.status = ProjectStatus.ARCHIVED.value
    await db.flush()
    return {"ok": True, "id": str(project_id), "status": project.status}


@router.get("/{project_id}/brief", response_model=BriefOut)
async def get_brief(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Brief).where(Brief.project_id == project_id))
    brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(404, "Brief not found")
    return brief


@router.put("/{project_id}/brief", response_model=BriefOut)
async def put_brief(
    project_id: UUID,
    body: BriefUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Brief).where(Brief.project_id == project_id))
    brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(404, "Brief not found")
    brief.content_json = body.content_json
    brief.version += 1
    if body.status:
        brief.status = body.status
    await unlock_step_and_outdate_later(db, project_id, StepType.BRIEF.value, required=False)
    await db.flush()
    await db.refresh(brief)
    return brief


@router.post("/{project_id}/brief/approve", response_model=BriefOut)
async def approve_project_brief(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await approve_brief(db, project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{project_id}/metrics", response_model=ProjectMetricsOut)
async def project_metrics(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models import Artifact

    runs = (
        await db.execute(select(PipelineRun).where(PipelineRun.project_id == project_id))
    ).scalars().all()

    art_ids = (
        await db.execute(select(Artifact.id).where(Artifact.project_id == project_id))
    ).scalars().all()
    edit_count = 0
    if art_ids:
        edit_count = (
            await db.execute(
                select(func.count()).select_from(HumanEdit).where(HumanEdit.artifact_id.in_(art_ids))
            )
        ).scalar() or 0

    latencies = [r.latency_ms for r in runs if r.latency_ms]
    costs = [r.estimated_cost or 0 for r in runs]
    regenerations = max(0, len(runs) - len({r.pipeline_step_id for r in runs}))

    return ProjectMetricsOut(
        project_id=project_id,
        total_runs=len(runs),
        regenerations=regenerations,
        manual_edits=edit_count,
        total_cost=sum(costs),
        avg_latency_ms=(sum(latencies) / len(latencies)) if latencies else 0.0,
        approved_without_heavy_edit=0,
    )
