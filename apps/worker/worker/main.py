"""Background worker: polls queued pipeline runs (backup to inline execution)."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

# Allow importing the API package when running in the worker container.
sys.path.insert(0, "/app/api_pkg")

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.domain.enums import RunStatus
from app.models import PipelineRun
from app.services.generation import execute_run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")


async def poll_once() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PipelineRun)
            .where(PipelineRun.status == RunStatus.QUEUED.value)
            .order_by(PipelineRun.created_at)
            .limit(5)
        )
        runs = result.scalars().all()
        for run in runs:
            logger.info("Executing queued run %s", run.id)
            try:
                await execute_run(db, run.id)
                await db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Run failed %s", run.id)
                await db.rollback()
        return len(runs)


async def main() -> None:
    logger.info("AI Studio 360 worker started")
    while True:
        try:
            n = await poll_once()
            if n == 0:
                await asyncio.sleep(3)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
