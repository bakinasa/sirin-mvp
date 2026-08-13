from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Expert, ExpertFeedback, User
from app.schemas import ExpertCreate, ExpertFeedbackCreate, ExpertFeedbackOut, ExpertOut
from app.services.artifacts import approve_expert_feedback_step
from uuid import UUID

router = APIRouter(tags=["experts"])


@router.get("/projects/{project_id}/experts", response_model=list[ExpertOut])
async def list_experts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Expert).where(Expert.project_id == project_id))
    return result.scalars().all()


@router.post("/projects/{project_id}/experts", response_model=ExpertOut)
async def create_expert(
    project_id: UUID,
    body: ExpertCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expert = Expert(project_id=project_id, **body.model_dump())
    db.add(expert)
    await db.flush()
    await db.refresh(expert)
    return expert


@router.post("/projects/{project_id}/expert-feedback", response_model=ExpertFeedbackOut)
async def create_feedback(
    project_id: UUID,
    body: ExpertFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expert = await db.get(Expert, body.expert_id)
    if expert is None or expert.project_id != project_id:
        raise HTTPException(400, "Expert not found in project")
    fb = ExpertFeedback(
        expert_id=body.expert_id,
        project_id=project_id,
        content=body.content,
        structured_tags=body.structured_tags,
        attachments=body.attachments,
    )
    db.add(fb)
    expert.status = "received"
    await db.flush()
    await db.refresh(fb)
    return fb


@router.get("/projects/{project_id}/expert-feedback", response_model=list[ExpertFeedbackOut])
async def list_feedback(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ExpertFeedback).where(ExpertFeedback.project_id == project_id)
    )
    return result.scalars().all()


@router.post("/projects/{project_id}/experts/approve-step")
async def approve_experts_step(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    step = await approve_expert_feedback_step(db, project_id)
    return {"step_type": step.step_type, "status": step.status}


@router.post("/projects/{project_id}/attachments")
async def upload_attachment(
    project_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a reference file to MinIO; returns URL for feedback.attachments."""
    from uuid import uuid4

    from app.services.storage import upload_bytes

    raw = await file.read()
    name = file.filename or "file"
    object_name = f"projects/{project_id}/{uuid4().hex}_{name}"
    url = upload_bytes(object_name, raw, file.content_type or "application/octet-stream")
    return {"url": url, "filename": name, "size": len(raw)}
