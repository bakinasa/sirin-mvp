from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.deps import get_current_user
from app.domain.enums import ItemStatus, StepType
from app.models import Artifact, ArtifactPatch, CommentThread, StageChatSession, User
from app.schemas import (
    ArtifactOut,
    ChatRequest,
    ChatResponse,
    ChatSessionOut,
    CommentCreate,
    CommentThreadOut,
    GenerateStageIn,
    ItemPatchIn,
    PatchOut,
    SectionItemCreateIn,
    SectionItemCreateOut,
    PipelineRunOut,
    SaveVersionIn,
)
from app.services.chat import chat, list_sessions, promote_ask_to_patch
from app.services.comments import create_comment, list_threads, resolve_thread
from app.services.generation import create_pipeline_run
from app.services.pipeline_gate import PipelineGateError
from app.services.stages import (
    StageEditError,
    apply_patch,
    discard_patch,
    freeze_artifact,
    get_current_artifact,
    new_map_edition,
    add_section_item,
    patch_item,
    restore_version,
    save_version,
    set_item_decision,
)

router = APIRouter(tags=["studio"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, StageEditError):
        return HTTPException(400, exc.message)
    if isinstance(exc, PipelineGateError):
        return HTTPException(400, exc.message)
    return HTTPException(500, str(exc))


@router.get("/projects/{project_id}/profession-map", response_model=ArtifactOut | None)
async def get_profession_map(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_current_artifact(db, project_id, StepType.PROFESSION_MAP.value)


@router.post("/projects/{project_id}/profession-map/generate", response_model=PipelineRunOut)
async def generate_profession_map(
    project_id: UUID,
    body: GenerateStageIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    body = body or GenerateStageIn()
    try:
        return await create_pipeline_run(
            db,
            project_id=project_id,
            user_id=user.id,
            step_type=StepType.PROFESSION_MAP.value,
            operator_prompt=body.operator_prompt,
            primary_model_id=body.primary_model_id,
            fallback_model_id=body.fallback_model_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post(
    "/projects/{project_id}/profession-map/sections/{section_id}/items",
    response_model=SectionItemCreateOut,
)
async def create_map_section_item(
    project_id: UUID,
    section_id: str,
    body: SectionItemCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ = user
    try:
        artifact, item = await add_section_item(
            db,
            project_id,
            StepType.PROFESSION_MAP.value,
            section_id,
            title=body.title,
            description=body.description,
            extra=body.extra or None,
        )
        return SectionItemCreateOut(artifact=artifact, item=item)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.patch("/projects/{project_id}/profession-map/items/{item_id}", response_model=ArtifactOut)
async def patch_map_item(
    project_id: UUID,
    item_id: str,
    body: ItemPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await patch_item(
            db, project_id, StepType.PROFESSION_MAP.value, item_id, body.content
        )
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post(
    "/projects/{project_id}/profession-map/items/{item_id}/accept",
    response_model=ArtifactOut,
)
async def accept_map_item(
    project_id: UUID,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await set_item_decision(
            db, project_id, StepType.PROFESSION_MAP.value, item_id, ItemStatus.ACCEPTED.value
        )
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post(
    "/projects/{project_id}/profession-map/items/{item_id}/reject",
    response_model=ArtifactOut,
)
async def reject_map_item(
    project_id: UUID,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await set_item_decision(
            db, project_id, StepType.PROFESSION_MAP.value, item_id, ItemStatus.REJECTED.value
        )
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post("/projects/{project_id}/profession-map/freeze", response_model=ArtifactOut)
async def freeze_map(
    project_id: UUID,
    body: SaveVersionIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    art = await get_current_artifact(db, project_id, StepType.PROFESSION_MAP.value)
    if art is None:
        raise HTTPException(404, "Нет карты профессии")
    return await freeze_artifact(db, art, (body.change_summary if body else "") or "Frozen")


@router.post("/projects/{project_id}/profession-map/new-edition")
async def map_new_edition(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await new_map_edition(db, project_id)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.get("/projects/{project_id}/scenario", response_model=ArtifactOut | None)
async def get_scenario(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_current_artifact(db, project_id, StepType.SCENARIO_PLAN.value)


@router.post("/projects/{project_id}/scenario/generate", response_model=PipelineRunOut)
async def generate_scenario(
    project_id: UUID,
    body: GenerateStageIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    body = body or GenerateStageIn()
    try:
        return await create_pipeline_run(
            db,
            project_id=project_id,
            user_id=user.id,
            step_type=StepType.SCENARIO_PLAN.value,
            operator_prompt=body.operator_prompt,
            primary_model_id=body.primary_model_id,
            fallback_model_id=body.fallback_model_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post(
    "/projects/{project_id}/scenario/sections/{section_id}/items",
    response_model=SectionItemCreateOut,
)
async def create_scenario_section_item(
    project_id: UUID,
    section_id: str,
    body: SectionItemCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ = user
    try:
        artifact, item = await add_section_item(
            db,
            project_id,
            StepType.SCENARIO_PLAN.value,
            section_id,
            title=body.title,
            description=body.description,
            extra=body.extra or None,
        )
        return SectionItemCreateOut(artifact=artifact, item=item)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.patch("/projects/{project_id}/scenario/items/{item_id}", response_model=ArtifactOut)
async def patch_scenario_item(
    project_id: UUID,
    item_id: str,
    body: ItemPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await patch_item(
            db, project_id, StepType.SCENARIO_PLAN.value, item_id, body.content
        )
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post("/projects/{project_id}/scenario/freeze", response_model=ArtifactOut)
async def freeze_scenario(
    project_id: UUID,
    body: SaveVersionIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    art = await get_current_artifact(db, project_id, StepType.SCENARIO_PLAN.value)
    if art is None:
        raise HTTPException(404, "Нет сценария")
    return await freeze_artifact(db, art, (body.change_summary if body else "") or "Frozen")


@router.post("/projects/{project_id}/stages/{stage}/chat", response_model=ChatResponse)
async def stage_chat(
    project_id: UUID,
    stage: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        session, message, patch = await chat(
            db,
            project_id=project_id,
            stage_type=stage,
            user_id=user.id,
            mode=body.mode,
            body=body.body,
            target_id=body.target_id,
            primary_model_id=body.primary_model_id,
            fallback_model_id=body.fallback_model_id,
        )
        session_full = (
            await db.execute(
                select(StageChatSession)
                .where(StageChatSession.id == session.id)
                .options(selectinload(StageChatSession.messages))
            )
        ).scalar_one()
        return ChatResponse(
            session=session_full,
            message=message,
            patch=patch,
        )
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.get("/projects/{project_id}/stages/{stage}/chat/sessions", response_model=list[ChatSessionOut])
async def stage_chat_sessions(
    project_id: UUID,
    stage: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = await list_sessions(db, project_id, stage)
    return sessions


@router.post("/projects/{project_id}/stages/{stage}/chat/promote-patch", response_model=PatchOut)
async def promote_patch(
    project_id: UUID,
    stage: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patch = await promote_ask_to_patch(
        db,
        project_id=project_id,
        stage_type=stage,
        user_id=user.id,
        instruction=body.body,
        target_id=body.target_id or "",
    )
    return patch


@router.post("/patches/{patch_id}/apply", response_model=ArtifactOut)
async def apply_patch_route(
    patch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patch = await db.get(ArtifactPatch, patch_id)
    if patch is None:
        raise HTTPException(404, "Patch not found")
    try:
        return await apply_patch(db, patch, user.id)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post("/patches/{patch_id}/discard", response_model=PatchOut)
async def discard_patch_route(
    patch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patch = await db.get(ArtifactPatch, patch_id)
    if patch is None:
        raise HTTPException(404, "Patch not found")
    try:
        return await discard_patch(db, patch)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.get("/projects/{project_id}/comments", response_model=list[CommentThreadOut])
async def get_comments(
    project_id: UUID,
    stage: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_threads(db, project_id, stage)


@router.post("/projects/{project_id}/comments", response_model=CommentThreadOut)
async def post_comment(
    project_id: UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await create_comment(
        db,
        project_id=project_id,
        user_id=user.id,
        stage_type=body.stage_type,
        body=body.body,
        target_type=body.target_type,
        target_id=body.target_id,
        artifact_id=body.artifact_id,
    )


@router.post("/comments/{thread_id}/resolve", response_model=CommentThreadOut)
async def resolve_comment(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = await db.get(CommentThread, thread_id)
    if thread is None:
        raise HTTPException(404, "Comment not found")
    return await resolve_thread(db, thread)


@router.post("/artifacts/{artifact_id}/freeze", response_model=ArtifactOut)
async def freeze_route(
    artifact_id: UUID,
    body: SaveVersionIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return await freeze_artifact(db, artifact, (body.change_summary if body else "") or "Frozen")


@router.post("/artifacts/{artifact_id}/save-version", response_model=ArtifactOut)
async def save_version_route(
    artifact_id: UUID,
    body: SaveVersionIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    try:
        return await save_version(db, artifact, body.change_summary if body else "")
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc


@router.post("/artifacts/{artifact_id}/restore/{version_id}", response_model=ArtifactOut)
async def restore_route(
    artifact_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    current = await db.get(Artifact, artifact_id)
    source = await db.get(Artifact, version_id)
    if current is None or source is None:
        raise HTTPException(404, "Artifact not found")
    try:
        return await restore_version(db, current, source)
    except StageEditError as exc:
        raise HTTPException(400, exc.message) from exc
