"""Background worker: queued pipeline runs + source summarization."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

# Allow importing the API package when running in the worker container.
sys.path.insert(0, "/app/api_pkg")

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.domain.enums import RunStatus
from app.models import PipelineRun
from app.services.generation import execute_run
from app.services.source_jobs import poll_summary_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")


async def poll_pipeline_runs() -> int:
    """Pick queued runs one-by-one in fresh sessions (LLM can take many minutes)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PipelineRun.id)
            .where(PipelineRun.status == RunStatus.QUEUED.value)
            .order_by(PipelineRun.created_at)
            .limit(3)
        )
        run_ids = list(result.scalars().all())

    handled = 0
    for run_id in run_ids:
        async with AsyncSessionLocal() as db:
            try:
                run = await execute_run(db, run_id)
                await db.commit()
                if run is not None:
                    handled += 1
                    logger.info(
                        "Finished run %s status=%s model=%s",
                        run_id,
                        run.status,
                        run.model_name,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Run failed %s", run_id)
                await db.rollback()
                async with AsyncSessionLocal() as fail_db:
                    run = await fail_db.get(PipelineRun, run_id)
                    if run and run.status in (
                        RunStatus.QUEUED.value,
                        RunStatus.RUNNING.value,
                    ):
                        run.status = RunStatus.FAILED.value
                        run.error_message = str(exc)[:2000]
                        run.finished_at = datetime.now(timezone.utc)
                        await fail_db.commit()
    return handled


async def main() -> None:
    logger.info("AI Studio 360 worker started (pipeline + source jobs)")
    while True:
        try:
            summary_jobs = await poll_summary_jobs(limit=2)
            pipeline_runs = await poll_pipeline_runs()
            if summary_jobs == 0 and pipeline_runs == 0:
                await asyncio.sleep(2)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
