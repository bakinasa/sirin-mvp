from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import OperatorPromptPreset, PromptTemplate, User
from app.operator_preset_defaults import factory_operator_preset
from app.schemas import (
    OperatorPresetCreate,
    OperatorPresetDefaultUpdate,
    OperatorPresetOut,
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplateUpdate,
)

router = APIRouter(tags=["prompts"])


@router.get("/prompt-templates", response_model=list[PromptTemplateOut])
async def list_templates(
    step_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(PromptTemplate).order_by(PromptTemplate.step_type, PromptTemplate.version.desc())
    if step_type:
        q = q.where(PromptTemplate.step_type == step_type)
    return (await db.execute(q)).scalars().all()


@router.post("/prompt-templates", response_model=PromptTemplateOut)
async def create_template(
    body: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Deactivate previous active for same step when creating new active
    if body.is_active:
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.step_type == body.step_type,
                PromptTemplate.is_active.is_(True),
            )
        )
        for t in result.scalars().all():
            t.is_active = False
    tpl = PromptTemplate(**body.model_dump())
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)
    return tpl


@router.patch("/prompt-templates/{template_id}", response_model=PromptTemplateOut)
async def update_template(
    template_id: UUID,
    body: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is None:
        raise HTTPException(404, "Template not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is True:
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.step_type == tpl.step_type,
                PromptTemplate.is_active.is_(True),
                PromptTemplate.id != tpl.id,
            )
        )
        for other in result.scalars().all():
            other.is_active = False
    for k, v in data.items():
        setattr(tpl, k, v)
    await db.flush()
    await db.refresh(tpl)
    return tpl


@router.get("/operator-prompt-presets", response_model=list[OperatorPresetOut])
async def list_presets(
    step_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(OperatorPromptPreset).order_by(OperatorPromptPreset.step_type)
    if step_type:
        q = q.where(OperatorPromptPreset.step_type == step_type)
    return (await db.execute(q)).scalars().all()


@router.post("/operator-prompt-presets", response_model=OperatorPresetOut)
async def create_preset(
    body: OperatorPresetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.is_default:
        result = await db.execute(
            select(OperatorPromptPreset).where(
                OperatorPromptPreset.step_type == body.step_type,
                OperatorPromptPreset.is_default.is_(True),
            )
        )
        for p in result.scalars().all():
            p.is_default = False
    preset = OperatorPromptPreset(**body.model_dump())
    db.add(preset)
    await db.flush()
    await db.refresh(preset)
    return preset


async def _get_default_preset(db: AsyncSession, step_type: str) -> OperatorPromptPreset | None:
    result = await db.execute(
        select(OperatorPromptPreset).where(
            OperatorPromptPreset.step_type == step_type,
            OperatorPromptPreset.is_default.is_(True),
        )
    )
    return result.scalars().first()


async def _upsert_default_preset(
    db: AsyncSession, step_type: str, content: str, *, title: str | None = None
) -> OperatorPromptPreset:
    row = await _get_default_preset(db, step_type)
    factory = factory_operator_preset(step_type)
    resolved_title = title or (factory["title"] if factory else "Задача оператора")
    if row is None:
        row = OperatorPromptPreset(
            step_type=step_type,
            title=resolved_title,
            content=content,
            is_default=True,
        )
        db.add(row)
    else:
        row.content = content
        if title:
            row.title = title
    await db.flush()
    await db.refresh(row)
    return row


@router.put("/operator-prompt-presets/default", response_model=OperatorPresetOut)
async def upsert_default_preset(
    step_type: str,
    body: OperatorPresetDefaultUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ = user
    if not step_type.strip():
        raise HTTPException(400, "step_type обязателен")
    return await _upsert_default_preset(db, step_type.strip(), body.content)


@router.post("/operator-prompt-presets/default/reset", response_model=OperatorPresetOut)
async def reset_default_preset(
    step_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ = user
    factory = factory_operator_preset(step_type)
    if factory is None:
        raise HTTPException(404, f"Нет исходной задачи оператора для шага {step_type}")
    return await _upsert_default_preset(
        db,
        step_type,
        str(factory["content"]),
        title=str(factory["title"]),
    )
