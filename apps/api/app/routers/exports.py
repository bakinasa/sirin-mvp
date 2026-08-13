from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import ExportJob, User
from app.schemas import ExportCreate, ExportOut
from app.services.export import create_export

router = APIRouter(tags=["exports"])


@router.post("/projects/{project_id}/exports", response_model=ExportOut)
async def start_export(
    project_id: UUID,
    body: ExportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await create_export(db, project_id, body.export_type)


@router.get("/exports/{export_id}", response_model=ExportOut)
async def get_export(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ExportJob, export_id)
    if job is None:
        raise HTTPException(404, "Export not found")
    return job
