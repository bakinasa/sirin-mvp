"""Stage chat: ask / local_edit / global_edit without dumping full history into prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import ChatMode, PatchScope, PatchStatus, StepStatus
from app.models import ArtifactPatch, StageChatMessage, StageChatSession
from app.services.generation import _call_model, _parse_json_content, _resolve_models
from app.services.prompt_assembler import assemble_chat_prompt
from app.services.stages import StageEditError, get_current_artifact


async def list_sessions(
    db: AsyncSession, project_id: UUID, stage_type: str
) -> list[StageChatSession]:
    result = await db.execute(
        select(StageChatSession)
        .where(
            StageChatSession.project_id == project_id,
            StageChatSession.stage_type == stage_type,
        )
        .options(selectinload(StageChatSession.messages))
        .order_by(StageChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def chat(
    db: AsyncSession,
    *,
    project_id: UUID,
    stage_type: str,
    user_id: UUID,
    mode: str,
    body: str,
    target_id: Optional[str] = None,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> tuple[StageChatSession, StageChatMessage, ArtifactPatch | None]:
    if mode not in {m.value for m in ChatMode}:
        raise StageEditError("Неизвестный режим чата")

    session = await _get_or_create_session(db, project_id, stage_type, mode)
    db.add(
        StageChatMessage(session_id=session.id, role="user", body=body)
    )
    await db.flush()

    assembled = await assemble_chat_prompt(
        db, project_id, stage_type, mode, body, target_id=target_id, session=session
    )
    primary, fallback = await _resolve_models(
        db, user_id, project_id, stage_type, primary_model_id, fallback_model_id
    )

    reply_text = ""
    patch: ArtifactPatch | None = None
    last_error = ""
    result = None
    for model in (primary, fallback):
        if model is None:
            continue
        try:
            result = await _call_model(db, model, assembled)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    if result is None:
        reply_text = (
            "Модель недоступна. "
            + (last_error or "Добавьте ключ в разделе «Модели».")
        )
        if mode != ChatMode.ASK.value:
            current = await get_current_artifact(db, project_id, stage_type)
            item_id = target_id or ""
            patch = ArtifactPatch(
                project_id=project_id,
                stage_type=stage_type,
                artifact_id=current.id if current else None,
                artifact_version_id=current.id if current else None,
                scope=PatchScope.LOCAL.value if mode == ChatMode.LOCAL_EDIT.value else PatchScope.GLOBAL.value,
                target_id=item_id,
                instruction=body,
                patch_json={
                    "changes": [],
                    "note": "Модель не ответила, патч пустой",
                    "error": last_error,
                },
                status=PatchStatus.DRAFT.value,
                created_by=user_id,
            )
            db.add(patch)
            await db.flush()
            reply_text = json.dumps(patch.patch_json, ensure_ascii=False)
    else:
        if mode == ChatMode.ASK.value:
            parsed = _parse_json_content(result.content)
            if isinstance(parsed, dict) and parsed.get("answer"):
                reply_text = str(parsed["answer"])
            elif isinstance(parsed, dict) and parsed.get("raw_text"):
                reply_text = str(parsed["raw_text"])
            else:
                reply_text = result.content or ""
        else:
            parsed = _parse_json_content(result.content)
            if not isinstance(parsed, dict):
                parsed = {"changes": [], "raw": parsed}
            current = await get_current_artifact(db, project_id, stage_type)
            patch = ArtifactPatch(
                project_id=project_id,
                stage_type=stage_type,
                artifact_id=current.id if current else None,
                artifact_version_id=current.id if current else None,
                scope=PatchScope.LOCAL.value if mode == ChatMode.LOCAL_EDIT.value else PatchScope.GLOBAL.value,
                target_id=target_id or "",
                instruction=body,
                patch_json=parsed,
                status=PatchStatus.DRAFT.value,
                created_by=user_id,
            )
            db.add(patch)
            await db.flush()
            reply_text = json.dumps(parsed, ensure_ascii=False)

    assistant = StageChatMessage(
        session_id=session.id,
        role="assistant",
        body=reply_text,
        applied_patch_id=patch.id if patch else None,
    )
    db.add(assistant)
    _update_session_summary(session, mode, body, reply_text)
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(session)
    await db.refresh(assistant)
    return session, assistant, patch


async def promote_ask_to_patch(
    db: AsyncSession,
    *,
    project_id: UUID,
    stage_type: str,
    user_id: UUID,
    instruction: str,
    target_id: str = "",
    new_value: Any = None,
) -> ArtifactPatch:
    current = await get_current_artifact(db, project_id, stage_type)
    patch = ArtifactPatch(
        project_id=project_id,
        stage_type=stage_type,
        artifact_id=current.id if current else None,
        artifact_version_id=current.id if current else None,
        scope=PatchScope.LOCAL.value if target_id else PatchScope.GLOBAL.value,
        target_id=target_id,
        instruction=instruction,
        patch_json={"changes": [{"target_id": target_id, "new": new_value, "rationale": instruction}]},
        status=PatchStatus.DRAFT.value,
        created_by=user_id,
    )
    db.add(patch)
    await db.flush()
    await db.refresh(patch)
    return patch


async def _get_or_create_session(
    db: AsyncSession, project_id: UUID, stage_type: str, mode: str
) -> StageChatSession:
    result = await db.execute(
        select(StageChatSession).where(
            StageChatSession.project_id == project_id,
            StageChatSession.stage_type == stage_type,
            StageChatSession.mode == mode,
        )
    )
    session = result.scalar_one_or_none()
    if session:
        return session
    session = StageChatSession(
        project_id=project_id,
        stage_type=stage_type,
        mode=mode,
        summary_json={"summary": "", "accepted_decisions": [], "open_questions": []},
    )
    db.add(session)
    await db.flush()
    return session


def _update_session_summary(
    session: StageChatSession, mode: str, user_text: str, reply: str
) -> None:
    summary = dict(session.summary_json or {})
    prev = str(summary.get("summary") or "")
    line = f"{mode}: {user_text[:180]}"
    summary["summary"] = (prev + " | " + line)[-1200:]
    if mode == ChatMode.ASK.value:
        questions = list(summary.get("open_questions") or [])
        questions.append(user_text[:300])
        summary["open_questions"] = questions[-12:]
    session.summary_json = summary
    _ = reply


def session_to_out(session: StageChatSession) -> dict[str, Any]:
    messages = sorted(session.messages or [], key=lambda m: m.created_at)
    return {
        "id": session.id,
        "project_id": session.project_id,
        "stage_type": session.stage_type,
        "mode": session.mode,
        "summary_json": session.summary_json,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": messages,
    }


_ = StepStatus
