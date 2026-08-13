"""Enqueue and (optionally sync) execute pipeline AI runs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ArtifactStatus, ChangeType, RunStatus, StepStatus, StepType
from app.llm.registry import build_provider
from app.models import Artifact, PipelineRun, PipelineStep, PromptEditHistory, UserModel
from app.security.crypto import decrypt_secret
from app.services.document import ensure_ids
from app.services.pipeline_gate import PipelineGateError, assert_can_run_step
from app.services.prompt_assembler import assemble_prompt
from app.llm.base import GenerateRequest

logger = logging.getLogger(__name__)


async def create_pipeline_run(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    step_type: str,
    operator_prompt: Optional[str] = None,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> PipelineRun:
    step = await assert_can_run_step(db, project_id, step_type)
    if step.status == StepStatus.LOCKED.value:
        raise PipelineGateError(
            "Шаг зафиксирован. Чтобы изменить его, создайте новую редакцию."
        )

    # Expert feedback is human-collected; no AI run needed to "complete" collection,
    # but synthesis/other generative steps are AI.
    assembled = await assemble_prompt(db, project_id, step_type, operator_prompt)

    db.add(
        PromptEditHistory(
            project_id=project_id,
            step_type=step_type,
            editor_id=user_id,
            content=assembled["operator_prompt"],
        )
    )

    primary, fallback = await _resolve_models(
        db,
        user_id,
        project_id,
        step_type,
        primary_model_id,
        fallback_model_id,
    )

    run = PipelineRun(
        project_id=project_id,
        pipeline_step_id=step.id,
        status=RunStatus.QUEUED.value,
        provider_name="",
        model_name=primary.model_id if primary else "",
        prompt_template_version=assembled["prompt_template_version"],
        operator_prompt_text=assembled["operator_prompt"],
        context_snapshot={
            "bundle": assembled["context_bundle"],
            "system_prompt": assembled["system_prompt"],
            "output_schema": assembled["output_schema"],
            "primary_user_model_id": str(primary.id) if primary else None,
            "fallback_user_model_id": str(fallback.id) if fallback else None,
            "user_message_preview": assembled["user_message"][:4000],
        },
    )
    db.add(run)
    await db.flush()

    # Execute inline for MVP reliability (worker can also pick up queued jobs).
    await execute_run(db, run.id)
    await db.refresh(run)
    return run


async def execute_run(db: AsyncSession, run_id: UUID) -> PipelineRun:
    run = await db.get(PipelineRun, run_id)
    if run is None:
        raise ValueError("Run not found")

    step = await db.get(PipelineStep, run.pipeline_step_id)
    assembled = await assemble_prompt(
        db, run.project_id, step.step_type, run.operator_prompt_text
    )

    snap = run.context_snapshot or {}
    primary_id = snap.get("primary_user_model_id")
    fallback_id = snap.get("fallback_user_model_id")

    primary = await db.get(UserModel, UUID(primary_id)) if primary_id else None
    fallback = await db.get(UserModel, UUID(fallback_id)) if fallback_id else None

    run.status = RunStatus.RUNNING.value
    run.started_at = datetime.now(timezone.utc)
    await db.flush()

    last_error = ""
    result = None
    used_fallback = False
    used_model = primary

    for attempt, model in enumerate([primary, fallback]):
        if model is None:
            continue
        try:
            result = await _call_model(db, model, assembled)
            used_model = model
            used_fallback = attempt > 0
            break
        except Exception as exc:  # noqa: BLE001 — record and try fallback
            last_error = str(exc)
            logger.warning("Model call failed (%s): %s", model.model_id, exc)

    if result is None:
        # Offline/dev mock so the pipeline is demoable without keys.
        result_content = _mock_artifact(step.step_type, assembled, reason=last_error)
        run.status = RunStatus.SUCCEEDED.value
        run.error_message = last_error or "Used mock generator (no working API key/model)"
        run.provider_name = "mock"
        run.model_name = "mock-local"
        run.latency_ms = 1
        run.token_input = 0
        run.token_output = 0
        run.estimated_cost = 0.0
        run.fallback_used = False
        content = result_content
    else:
        run.status = RunStatus.SUCCEEDED.value
        run.provider_name = used_model.provider_name  # type: ignore[union-attr]
        run.model_name = used_model.model_id  # type: ignore[union-attr]
        run.latency_ms = result.latency_ms
        run.token_input = result.token_input
        run.token_output = result.token_output
        run.estimated_cost = (
            (used_model.input_price or 0) * result.token_input / 1_000_000
            + (used_model.output_price or 0) * result.token_output / 1_000_000
        )
        run.fallback_used = used_fallback
        content = _parse_json_content(result.content)

    if step.step_type in (StepType.PROFESSION_MAP.value, StepType.SCENARIO_PLAN.value):
        content = ensure_ids(content, step.step_type)

    run.finished_at = datetime.now(timezone.utc)

    # Version artifact
    version = await _next_version(db, run.project_id, step.step_type)
    parent_id = step.current_artifact_id
    artifact = Artifact(
        project_id=run.project_id,
        step_type=step.step_type,
        source_run_id=run.id,
        parent_artifact_id=parent_id,
        content=content,
        format="json",
        version=version,
        status=ArtifactStatus.AI_GENERATED.value,
        change_type=ChangeType.AI_GENERATE.value,
        change_summary="AI generation",
        frozen=False,
    )
    db.add(artifact)
    await db.flush()

    step.current_artifact_id = artifact.id
    step.status = StepStatus.AI_GENERATED.value

    if step.step_type == StepType.SCENARIO_PLAN.value:
        await _lock_previous_map(db, run.project_id)

    await db.flush()
    await db.refresh(run)
    return run


async def _call_model(db: AsyncSession, model: UserModel, assembled: dict):
    # UserModel stores the full upstream connection config + encrypted BYOK.
    api_key = decrypt_secret(model.encrypted_api_key)
    if not api_key:
        raise RuntimeError("No API key for user model")

    adapter = build_provider(
        model.provider_type, model.provider_name, model.base_url, model.capabilities_json
    )
    req = GenerateRequest(
        model=model.model_id,
        system=assembled["system_prompt"],
        user=assembled["user_message"],
        temperature=0.2,
        max_tokens=4096,
        response_json=True,
    )
    return await adapter.generate(api_key, req)


async def _resolve_models(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    step_type: str,
    primary_model_id: Optional[UUID],
    fallback_model_id: Optional[UUID],
):
    # Ignore old StepModelConfig + provider catalog: primary/fallback are resolved
    # purely from the user-owned model connections passed from the UI.
    result = await db.execute(
        select(UserModel).where(UserModel.owner_id == user_id, UserModel.is_enabled.is_(True))
    )
    models = result.scalars().all()
    by_id = {m.id: m for m in models}

    primary = primary_model_id and by_id.get(primary_model_id)
    fallback = fallback_model_id and by_id.get(fallback_model_id)

    if primary is None and models:
        free = [m for m in models if m.is_free]
        primary = free[0] if free else models[0]

    if primary is not None and fallback is not None and fallback.id == primary.id:
        fallback = None

    if fallback is None and models:
        for m in models:
            if primary is None or m.id != primary.id:
                fallback = m
                break

    return primary, fallback


async def _lock_previous_map(db: AsyncSession, project_id: UUID) -> None:
    result = await db.execute(
        select(PipelineStep).where(
            PipelineStep.project_id == project_id,
            PipelineStep.step_type == StepType.PROFESSION_MAP.value,
        )
    )
    step = result.scalar_one_or_none()
    if step is None:
        return
    step.status = StepStatus.LOCKED.value
    if step.current_artifact_id:
        art = await db.get(Artifact, step.current_artifact_id)
        if art:
            art.frozen = True
            if not step.approved_artifact_id:
                step.approved_artifact_id = art.id


async def _next_version(db: AsyncSession, project_id: UUID, step_type: str) -> int:
    result = await db.execute(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.step_type == step_type)
        .order_by(Artifact.version.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    return (latest.version + 1) if latest else 1


def _parse_json_content(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return {"raw": "", "clarifications_needed": ["Пустой ответ модели"]}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Strip markdown fences if present
        if "```" in text:
            inner = text.split("```")[1]
            if inner.startswith("json"):
                inner = inner[4:]
            try:
                return json.loads(inner.strip())
            except json.JSONDecodeError:
                pass
        return {"raw_text": text, "clarifications_needed": ["Ответ не в JSON"]}


def _mock_artifact(step_type: str, assembled: dict, reason: str = "") -> dict:
    """
    Local fallback when no working provider key is available.
    Uses project/brief context so the draft is not a random unrelated template.
    This is NOT a real LLM answer.
    """
    meta, brief = _extract_context_bits(assembled)
    title = meta.get("title") or "Модуль без названия"
    profession = meta.get("profession") or "не указана"
    audience = meta.get("audience") or "не указана"
    topic = (
        brief.get("learning_objectives")
        or profession
        or title
        or "тема не задана"
    )
    work_ctx = brief.get("work_context") or meta.get("source_materials") or ""
    tools = brief.get("tools_and_equipment") or ""
    safety = brief.get("safety_constraints") or meta.get("constraints") or ""
    pains = brief.get("known_pain_points") or ""
    success = brief.get("success_criteria") or ""

    why = reason or "Не найден рабочий API-ключ провайдера"
    generation_meta = {
        "mode": "mock",
        "is_real_ai": False,
        "reason": why,
        "explanation_ru": (
            "Это НЕ ответ нейросети. Реальный вызов модели не удался "
            f"({why}). «Бесплатная модель» в каталоге всё равно требует API-ключ "
            "провайдера (например OpenRouter): бесплатно = без оплаты токенов, "
            "но ключ нужен. Добавьте ключ в «Модели» → Проверить ключ → снова "
            "«Запустить AI»."
        ),
        "what_to_do": [
            "Откройте раздел «Модели»",
            "Выберите провайдера (часто OpenRouter для free-моделей)",
            "Вставьте свой API-ключ и сохраните",
            "Нажмите «Проверить ключ» — должно быть OK",
            "Вернитесь сюда и снова нажмите «Запустить AI»",
        ],
    }

    base = {
        "title": f"[ЗАГЛУШКА] {title}",
        "_mock": True,
        "_generation": generation_meta,
        "step_type": step_type,
        "clarifications_needed": [
            "Нужен рабочий API-ключ, иначе результат останется заглушкой",
            "Проверьте, что в Model Selector выбрана модель провайдера, для которого сохранён ключ",
        ],
    }

    if step_type == "draft_tz":
        goals = []
        if brief.get("learning_objectives"):
            goals.append(str(brief["learning_objectives"]))
        else:
            goals.append(f"Отработать сценарий: {topic}")
        if audience and audience != "не указана":
            goals.append(f"Учесть аудиторию: {audience}")

        steps = [
            {
                "order": 1,
                "name": "Подготовка",
                "actions": [
                    a
                    for a in [
                        f"Ознакомиться с задачей: {topic}",
                        f"Подготовить инструменты: {tools}" if tools else "Подготовить нужный инвентарь",
                        f"Учесть ограничения: {safety}" if safety else "",
                    ]
                    if a
                ],
            },
            {
                "order": 2,
                "name": "Основная операция",
                "actions": [
                    a
                    for a in [
                        f"Выполнить ключевые действия по теме: {topic}",
                        f"Контекст: {work_ctx}" if work_ctx else "Выполнить шаги по сценарию из brief/проекта",
                    ]
                    if a
                ],
            },
            {
                "order": 3,
                "name": "Завершение и контроль",
                "actions": [
                    a
                    for a in [
                        f"Проверить результат: {success}" if success else "Зафиксировать выполнение работы",
                        "Сверить действия с чек-листом модуля",
                    ]
                    if a
                ],
            },
        ]
        return {
            **base,
            "summary_ru": (
                f"Черновик-заглушка по проекту «{title}» (профессия/сценарий: {profession}). "
                "Текст собран из ваших данных проекта и brief без вызова ИИ."
            ),
            "learning_goals": goals,
            "workflow_steps": steps,
            "typical_errors": [pains] if pains else ["Типичные ошибки не указаны в brief — уточните"],
            "critical_risks": [safety] if safety else ["Критичные риски не указаны в brief — уточните"],
            "observable_actions": [
                "Действия сотрудника, которые можно увидеть в 360°-кадре (уточните в brief)",
            ],
            "used_inputs": {
                "project_title": title,
                "profession": profession,
                "audience": audience,
                "brief_present": bool(brief),
            },
        }

    if step_type == "expert_synthesis":
        return {
            **base,
            "summary_ru": f"Заглушка сведения фидбека для «{title}».",
            "updated_tz": {"summary": f"Согласованная версия по теме: {topic} (mock)"},
            "agreements": ["Нужно подтвердить ключевые шаги сценария экспертами"],
            "conflicts": [],
            "critical_requirements": [safety] if safety else [],
            "profession_critical_elements": [profession] if profession != "не указана" else [],
        }

    if step_type == "final_tz":
        return {
            **base,
            "summary_ru": f"Заглушка итогового ТЗ для «{title}».",
            "sections": [
                {"heading": "Тема", "body": str(topic)},
                {"heading": "Контекст", "body": work_ctx or "не заполнен"},
                {"heading": "Цели", "body": brief.get("learning_objectives") or "не заполнены"},
            ],
        }

    if step_type == "scene_breakdown":
        return {
            **base,
            "summary_ru": f"Заглушка разбиения на сцены для «{title}».",
            "steps": [
                {
                    "id": "s1",
                    "name": "Старт сценария",
                    "scenes": [
                        {
                            "id": "sc1",
                            "goal": f"Показать начало: {topic}",
                            "attention_point": "Ключевые объекты из brief",
                            "risk_360": safety or "уточнить риски съёмки",
                            "timing_sec": 30,
                            "shots": [{"id": "sh1", "description": f"Обзор 360° рабочей зоны: {topic}"}],
                            "production_hint": "real",
                        }
                    ],
                }
            ],
        }

    if step_type == "production_planning":
        return {
            **base,
            "summary_ru": f"Заглушка production-плана для «{title}».",
            "scenes": [
                {"id": "sc1", "method": "real", "notes": f"Снять на локации по теме: {topic}"},
                {"id": "sc2", "method": "hybrid", "notes": "При необходимости дополнить AI-фоном"},
            ],
        }

    if step_type == "storyboard":
        return {
            **base,
            "summary_ru": f"Заглушка раскадровки для «{title}».",
            "frames": [
                {
                    "id": "f1",
                    "scene_id": "sc1",
                    "order": 1,
                    "description": f"Кадр 1: обзор — {topic}",
                    "narration": f"Начните с осмотра зоны для: {topic}",
                    "interaction": None,
                    "comment": "",
                }
            ],
        }
    if step_type == "profession_map":
        from app.services.document import empty_document, ensure_ids

        doc = empty_document("profession_map")
        doc["sections"][0]["items"] = [
            {
                "id": "work_type_1",
                "title": topic,
                "description": work_ctx or f"Вид работ по проекту «{title}»",
                "why": "Собрано из brief без вызова модели",
                "in_scope": [topic],
                "out_of_scope": [],
                "sources": [],
                "status": "proposed",
            }
        ]
        doc["sections"][1]["items"] = [
            {
                "id": "skill_1",
                "title": "Безопасное выполнение операции",
                "description": f"Базовый навык для: {topic}",
                "criticality": "high",
                "status": "proposed",
            }
        ]
        doc["sections"][2]["items"] = [
            {
                "id": "point_1",
                "skill_id": "skill_1",
                "title": "Соблюдение порядка действий",
                "observe": "Последовательность операций в кадре",
                "correct": "Действия по регламенту",
                "violation": "Пропуск шага или нарушение порядка",
                "visual": "средняя",
                "can_360": True,
                "status": "proposed",
            }
        ]
        doc["sections"][6]["items"] = [
            {
                "id": "q_1",
                "title": "Какие нарушения эксперты считают критичными?",
                "why": "В brief недостаточно данных",
                "status": "proposed",
            }
        ]
        return {**ensure_ids(doc, "profession_map"), **{k: base[k] for k in ("_mock", "_generation", "title")}}

    if step_type == "scenario_plan":
        from app.services.document import empty_document, ensure_ids

        doc = empty_document("scenario_plan")
        doc["sections"][0]["items"] = [
            {
                "id": "passport_1",
                "title": title,
                "profession": profession,
                "operation": topic,
                "format": meta.get("delivery_format") or "VR / планшет",
                "goal": brief.get("learning_objectives") or "",
                "status": "proposed",
            }
        ]
        doc["sections"][1]["items"] = [
            {
                "id": "train_seg_1",
                "title": "Правильное выполнение",
                "location": work_ctx or "рабочая площадка",
                "frames": [
                    {
                        "id": "tf_1",
                        "action": f"Показать корректное выполнение: {topic}",
                        "focus": "Ключевые действия и СИЗ",
                    }
                ],
                "status": "proposed",
            }
        ]
        doc["sections"][2]["items"] = [
            {
                "id": "diag_seg_1",
                "title": "Поиск нарушений",
                "violation": pains or "Типовое нарушение порядка",
                "stop_at": "момент, когда нарушение видно в кадре",
                "assessment_points": ["point_1"],
                "status": "proposed",
            }
        ]
        return {**ensure_ids(doc, "scenario_plan"), **{k: base[k] for k in ("_mock", "_generation", "title")}}
    return base


def _extract_context_bits(assembled: dict) -> tuple[dict, dict]:
    bundle = assembled.get("context_bundle") or {}
    meta: dict = {}
    brief: dict = {}
    for block in bundle.get("blocks") or []:
        if block.get("id") == "project_metadata":
            meta = block.get("content") or {}
        elif block.get("id") == "brief":
            content = block.get("content") or {}
            if isinstance(content, dict):
                brief = content
    return meta, brief
