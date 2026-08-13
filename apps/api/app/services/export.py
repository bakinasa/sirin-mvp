"""Export approved project artifacts to markdown / json / text bundle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ExportStatus, ExportType
from app.models import Artifact, Brief, ExportJob, Expert, ExpertFeedback, Project


async def create_export(
    db: AsyncSession, project_id: UUID, export_type: str
) -> ExportJob:
    job = ExportJob(
        project_id=project_id,
        export_type=export_type,
        status=ExportStatus.RUNNING.value,
    )
    db.add(job)
    await db.flush()

    try:
        project = await db.get(Project, project_id)
        if project is None:
            raise ValueError("Project not found")

        payload = await _collect(db, project)

        if export_type == ExportType.JSON.value:
            content = payload
            path = f"exports/{project_id}/{job.id}.json"
        elif export_type == ExportType.TEXT_BUNDLE.value:
            content = {"files": _as_text_files(payload)}
            path = f"exports/{project_id}/{job.id}_bundle.json"
        else:
            content = {"markdown": _as_markdown(payload)}
            path = f"exports/{project_id}/{job.id}.md"

        job.result_content = content
        job.result_path = path
        job.status = ExportStatus.READY.value
    except Exception as exc:  # noqa: BLE001
        job.status = ExportStatus.FAILED.value
        job.error_message = str(exc)

    job.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)
    return job


async def _collect(db: AsyncSession, project: Project) -> dict:
    brief = (
        await db.execute(select(Brief).where(Brief.project_id == project.id))
    ).scalar_one_or_none()
    artifacts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.project_id == project.id, Artifact.status == "approved")
            .order_by(Artifact.step_type, Artifact.version.desc())
        )
    ).scalars().all()

    # Keep highest version per step
    latest: dict[str, Artifact] = {}
    for a in artifacts:
        if a.step_type not in latest:
            latest[a.step_type] = a

    experts = (
        await db.execute(select(Expert).where(Expert.project_id == project.id))
    ).scalars().all()
    feedback = (
        await db.execute(
            select(ExpertFeedback).where(ExpertFeedback.project_id == project.id)
        )
    ).scalars().all()

    preferred = ("profession_map", "scenario_plan")
    if any(k in latest for k in preferred):
        artifact_payload = {
            k: {"version": latest[k].version, "content": latest[k].content}
            for k in preferred
            if k in latest
        }
    else:
        artifact_payload = {
            k: {"version": v.version, "content": v.content} for k, v in latest.items()
        }

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": str(project.id),
            "title": project.title,
            "client_name": project.client_name,
            "profession": project.profession,
            "audience": project.audience,
            "delivery_format": project.delivery_format,
            "expected_duration": project.expected_duration,
            "constraints": project.constraints,
        },
        "brief": brief.content_json if brief else {},
        "experts": [
            {"name": e.name, "role": e.role, "status": e.status} for e in experts
        ],
        "expert_feedback": [
            {"expert_id": str(f.expert_id), "content": f.content, "tags": f.structured_tags}
            for f in feedback
        ],
        "artifacts": artifact_payload,
    }


def _as_markdown(payload: dict) -> str:
    p = payload["project"]
    lines = [
        f"# {p['title']}",
        "",
        f"**Заказчик:** {p['client_name']}  ",
        f"**Профессия:** {p['profession']}  ",
        f"**Аудитория:** {p['audience']}  ",
        f"**Формат:** {p['delivery_format']}  ",
        f"**Длительность:** {p['expected_duration']}",
        "",
        "## Brief",
        "```json",
        json.dumps(payload.get("brief") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Утверждённые артефакты",
    ]
    for step, art in (payload.get("artifacts") or {}).items():
        lines.append(f"### {step} (v{art['version']})")
        lines.append("```json")
        lines.append(json.dumps(art["content"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _as_text_files(payload: dict) -> dict[str, str]:
    files = {
        "project.json": json.dumps(payload["project"], ensure_ascii=False, indent=2),
        "brief.json": json.dumps(payload.get("brief") or {}, ensure_ascii=False, indent=2),
        "README.md": _as_markdown(payload),
    }
    for step, art in (payload.get("artifacts") or {}).items():
        files[f"{step}.json"] = json.dumps(art["content"], ensure_ascii=False, indent=2)
    return files
