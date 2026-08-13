"""Comment threads on document blocks."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import CommentStatus
from app.models import CommentMessage, CommentThread
from app.services.stages import get_current_artifact


async def list_threads(
    db: AsyncSession, project_id: UUID, stage_type: str | None = None
) -> list[CommentThread]:
    q = (
        select(CommentThread)
        .where(CommentThread.project_id == project_id)
        .options(selectinload(CommentThread.messages))
        .order_by(CommentThread.created_at.desc())
    )
    if stage_type:
        q = q.where(CommentThread.stage_type == stage_type)
    return list((await db.execute(q)).scalars().all())


async def create_comment(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    stage_type: str,
    body: str,
    target_type: str = "block",
    target_id: str = "",
    artifact_id: UUID | None = None,
) -> CommentThread:
    if artifact_id is None:
        art = await get_current_artifact(db, project_id, stage_type)
        artifact_id = art.id if art else None
    thread = CommentThread(
        project_id=project_id,
        stage_type=stage_type,
        artifact_id=artifact_id,
        artifact_version_id=artifact_id,
        target_type=target_type,
        target_id=target_id,
        status=CommentStatus.OPEN.value,
        created_by=user_id,
    )
    db.add(thread)
    await db.flush()
    db.add(
        CommentMessage(
            thread_id=thread.id,
            body=body,
            message_type="comment",
            decision="none",
            created_by=user_id,
        )
    )
    await db.flush()
    result = await db.execute(
        select(CommentThread)
        .where(CommentThread.id == thread.id)
        .options(selectinload(CommentThread.messages))
    )
    return result.scalar_one()


async def resolve_thread(db: AsyncSession, thread: CommentThread) -> CommentThread:
    thread.status = CommentStatus.RESOLVED.value
    await db.flush()
    result = await db.execute(
        select(CommentThread)
        .where(CommentThread.id == thread.id)
        .options(selectinload(CommentThread.messages))
    )
    return result.scalar_one()
