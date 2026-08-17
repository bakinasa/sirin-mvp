"""Background queue for source summarization (API BackgroundTasks + worker poll)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.domain.enums import ParseStatus
from app.models import ProjectSource

logger = logging.getLogger(__name__)

SUMMARY_STALE_SECONDS = 600


async def schedule_summary_job(source_id: UUID) -> None:
    """Fire-and-forget helper for FastAPI BackgroundTasks."""
    try:
        await run_summary_job(source_id)
    except Exception:  # noqa: BLE001
        logger.exception("Background summary job crashed for source %s", source_id)


async def run_summary_job(source_id: UUID) -> bool:
    async with AsyncSessionLocal() as db:
        try:
            handled = await execute_summary_job(db, source_id=source_id)
            await db.commit()
            return handled
        except Exception:  # noqa: BLE001
            await db.rollback()
            raise


async def poll_summary_jobs(limit: int = 3) -> int:
    handled = 0
    for _ in range(limit):
        async with AsyncSessionLocal() as db:
            try:
                source = await claim_summary_job(db)
                if source is None:
                    return handled
                await _run_claimed_job(db, source)
                await db.commit()
                handled += 1
            except Exception:  # noqa: BLE001
                logger.exception("Worker summary job failed")
                await db.rollback()
    return handled


async def execute_summary_job(db: AsyncSession, *, source_id: UUID) -> bool:
    result = await db.execute(
        select(ProjectSource).where(ProjectSource.id == source_id).with_for_update()
    )
    source = result.scalar_one_or_none()
    if source is None:
        return False
    if source.parse_status != ParseStatus.SUMMARIZING.value:
        return False
    job = _normalize_job(source.summary_job_json)
    if job.get("status") == "running" and not _job_is_stale(job):
        return False
    source.summary_job_json = _mark_job_running(job)
    await db.flush()
    await _run_claimed_job(db, source)
    return True


async def claim_summary_job(db: AsyncSession) -> ProjectSource | None:
    result = await db.execute(
        select(ProjectSource)
        .where(ProjectSource.parse_status == ParseStatus.SUMMARIZING.value)
        .order_by(ProjectSource.updated_at)
        .limit(10)
        .with_for_update(skip_locked=True)
    )
    for source in result.scalars():
        job = _normalize_job(source.summary_job_json)
        status = job.get("status", "queued")
        if status == "running" and not _job_is_stale(job):
            continue
        source.summary_job_json = _mark_job_running(job)
        await db.flush()
        return source
    return None


async def _run_claimed_job(db: AsyncSession, source: ProjectSource) -> None:
    from app.services.sources import finalize_summary_failure, summarize_source

    job = _normalize_job(source.summary_job_json)
    user_id = UUID(job["user_id"])
    primary = UUID(job["primary_model_id"]) if job.get("primary_model_id") else None
    fallback = UUID(job["fallback_model_id"]) if job.get("fallback_model_id") else None
    try:
        await summarize_source(
            db,
            source,
            user_id,
            primary_model_id=primary,
            fallback_model_id=fallback,
        )
        source.parse_status = ParseStatus.READY.value
        source.parse_error = ""
        source.summary_job_json = _mark_job_done(job)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary failed for source %s: %s", source.id, exc)
        await finalize_summary_failure(source, exc)
        job = _mark_job_failed(_normalize_job(source.summary_job_json), str(exc))
        source.summary_job_json = job


def build_summary_job(
    *,
    user_id: UUID,
    primary_model_id: Optional[UUID],
    fallback_model_id: Optional[UUID],
    part_total: int = 0,
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "user_id": str(user_id),
        "primary_model_id": str(primary_model_id) if primary_model_id else None,
        "fallback_model_id": str(fallback_model_id) if fallback_model_id else None,
        "status": "queued",
        "part_done": 0,
        "part_total": part_total,
        "message": "В очереди на выжимку",
        "updated_at": now,
        "started_at": None,
    }


def summary_progress(source: ProjectSource) -> dict[str, Any]:
    job = _normalize_job(source.summary_job_json)
    total = int(job.get("part_total") or 0)
    done = int(job.get("part_done") or 0)
    percent = int(done / total * 100) if total else 0
    return {
        "status": job.get("status") or "queued",
        "part_done": done,
        "part_total": total,
        "percent": percent,
        "message": job.get("message") or "",
    }


async def update_summary_progress(
    db: AsyncSession,
    source: ProjectSource,
    *,
    part_done: int,
    part_total: int,
    message: str = "",
) -> None:
    job = _normalize_job(source.summary_job_json)
    job["part_done"] = part_done
    job["part_total"] = part_total
    job["updated_at"] = _now_iso()
    if message:
        job["message"] = message
    elif part_total:
        job["message"] = f"Выжимка: часть {part_done}/{part_total}"
    source.summary_job_json = job
    if part_total and source.parse_status == ParseStatus.SUMMARIZING.value:
        source.parse_error = job["message"]
    await db.flush()


def _normalize_job(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _mark_job_running(job: dict[str, Any]) -> dict[str, Any]:
    updated = dict(job)
    updated["status"] = "running"
    updated["started_at"] = updated.get("started_at") or _now_iso()
    updated["updated_at"] = _now_iso()
    if not updated.get("message"):
        updated["message"] = "Выжимка запущена"
    return updated


def _mark_job_done(job: dict[str, Any]) -> dict[str, Any]:
    updated = dict(job)
    updated["status"] = "done"
    updated["updated_at"] = _now_iso()
    updated["message"] = "Готово"
    return updated


def _mark_job_failed(job: dict[str, Any], error: str) -> dict[str, Any]:
    updated = dict(job)
    updated["status"] = "failed"
    updated["updated_at"] = _now_iso()
    updated["message"] = error[:500]
    return updated


def _job_is_stale(job: dict[str, Any]) -> bool:
    updated_at = _parse_iso(job.get("updated_at"))
    if updated_at is None:
        return True
    return datetime.now(timezone.utc) - updated_at > timedelta(seconds=SUMMARY_STALE_SECONDS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
