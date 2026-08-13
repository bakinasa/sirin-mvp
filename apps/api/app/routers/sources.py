from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db import get_db
from app.deps import get_current_user
from app.models import ProjectSource, User
from app.schemas import SourceDetailOut, SourceOut, SourceReprocessIn
from app.services.sources import (
    create_source_from_upload,
    list_sources,
    process_source,
    source_to_out,
)

router = APIRouter(tags=["sources"])


@router.get("/projects/{project_id}/sources", response_model=list[SourceOut])
async def get_sources(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sources = await list_sources(db, project_id)
    return [SourceOut.model_validate(source_to_out(s)) for s in sources]


@router.post("/projects/{project_id}/sources", response_model=SourceOut)
async def upload_source(
    project_id: UUID,
    file: UploadFile = File(...),
    source_type: str | None = Form(default=None),
    primary_model_id: str | None = Form(default=None),
    fallback_model_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    primary = UUID(primary_model_id) if primary_model_id else None
    fallback = UUID(fallback_model_id) if fallback_model_id else None
    try:
        source = await create_source_from_upload(
            db,
            project_id=project_id,
            user_id=user.id,
            filename=file.filename or "file",
            mime=file.content_type or "",
            data=raw,
            source_type=source_type,
            primary_model_id=primary,
            fallback_model_id=fallback,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Не удалось обработать файл: {exc}") from exc
    return SourceOut.model_validate(source_to_out(source))


@router.get("/sources/{source_id}", response_model=SourceDetailOut)
async def get_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProjectSource)
        .where(ProjectSource.id == source_id)
        .options(selectinload(ProjectSource.chunks))
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Source not found")
    return SourceDetailOut.model_validate(source_to_out(source, detail=True))


@router.post("/sources/{source_id}/reprocess", response_model=SourceOut)
async def reprocess(
    source_id: UUID,
    body: SourceReprocessIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProjectSource)
        .where(ProjectSource.id == source_id)
        .options(selectinload(ProjectSource.chunks))
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Source not found")
    source = await process_source(
        db,
        source,
        user_id=user.id,
        raw=None,
        primary_model_id=body.primary_model_id if body else None,
        fallback_model_id=body.fallback_model_id if body else None,
    )
    return SourceOut.model_validate(source_to_out(source))
