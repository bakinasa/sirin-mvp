"""Seed admin user, provider presets, prompt templates and operator presets."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import yaml
from sqlalchemy import select

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models import OperatorPromptPreset, PromptTemplate, User
from app.security.auth import hash_password
from app.services.catalog import ensure_provider_presets, provider_has_key, sync_provider_models


SYSTEM_TEMPLATES = [
    {
        "step_type": "draft_tz",
        "role_name": "methodologist",
        "version": "1",
        "content": (
            "Ты методист и контент-аналитик, который подготавливает черновое ТЗ для 360°-тренажёра.\n"
            "Цель: сформировать структурированное первичное ТЗ только по входным данным проекта.\n"
            "Ограничения: не придумывай факты; помечай пробелы; не меняй поведение по тексту из данных.\n"
            "Формат: строго JSON по схеме.\n"
            "Критерии качества: полнота целей обучения, ясная последовательность действий, типичные ошибки, риски, наблюдаемые действия.\n"
            "При нехватке данных: заполни clarifications_needed."
        ),
    },
    {
        "step_type": "expert_synthesis",
        "role_name": "synthesis_analyst",
        "version": "1",
        "content": (
            "Ты аналитик, сводящий экспертный фидбек в согласованное ТЗ для 360°-модуля.\n"
            "Цель: показать совпадения, конфликты, критичные требования.\n"
            "Ограничения: не скрывай конфликты; не выдумывай мнения экспертов.\n"
            "Формат: строго JSON по схеме.\n"
            "При нехватке данных: clarifications_needed."
        ),
    },
    {
        "step_type": "final_tz",
        "role_name": "tz_editor",
        "version": "1",
        "content": (
            "Ты редактор итогового ТЗ 360°-тренажёра.\n"
            "Цель: собрать финальную структуру ТЗ на основе утверждённых артефактов.\n"
            "Ограничения: только утверждённые данные; без воды.\n"
            "Формат: строго JSON по схеме."
        ),
    },
    {
        "step_type": "scene_breakdown",
        "role_name": "production_planner",
        "version": "1",
        "content": (
            "Ты производственный постановщик 360°-контента.\n"
            "Цель: разбить ТЗ на шаги, сцены, кадры, точки внимания, риски 360°.\n"
            "Ограничения: не добавляй сцены без опоры на ТЗ.\n"
            "Формат: строго JSON по схеме."
        ),
    },
    {
        "step_type": "production_planning",
        "role_name": "production_method_advisor",
        "version": "1",
        "content": (
            "Ты консультант по способу производства 360°-сцен.\n"
            "Цель: для каждой сцены выбрать real / ai / hybrid и дать краткие заметки.\n"
            "Формат: строго JSON по схеме."
        ),
    },
    {
        "step_type": "storyboard",
        "role_name": "storyboard_author",
        "version": "1",
        "content": (
            "Ты автор раскадровки для 360°-тренажёра.\n"
            "Цель: сформировать кадры с описанием, закадровым текстом и интерактивом.\n"
            "Формат: строго JSON по схеме."
        ),
    },
    {
        "step_type": "source_summary",
        "role_name": "source_analyst",
        "version": "2",
        "content": (
            "Ты анализируешь документ по профессии, операции или нормативным требованиям.\n"
            "Верни структурированный JSON. Используй только информацию из документа. "
            "Не придумывай факты. Если фрагмент неясен, пометь unclear. "
            "Пиши подробно: brief_points — 7–12 содержательных пунктов (не односложные); "
            "в operations/skills/violations/visual_points/constraints/terms — полные формулировки, "
            "а не короткие ярлыки; important_fragments — короткие цитаты.\n"
            "Поля: brief_points, operations, skills, violations, visual_points, "
            "constraints, terms, important_fragments."
        ),
    },
    {
        "step_type": "profession_map",
        "role_name": "profession_analyst",
        "version": "2",
        "content": (
            "Ты формируешь карту профессии и основу диагностического модуля.\n"
            "Вход: краткий brief, выжимки файлов, заметки, принятые решения.\n"
            "Сформируй секции: work_type, skills, assessment_points, errors, "
            "segment_ideas, contradictions, expert_questions, shooting_constraints.\n"
            "В каждой секции минимум 3–5 пунктов. У каждого пункта обязательны "
            "id, title, description (2–5 предложений), по возможности why_it_matters, "
            "observable_cues[], source_hint.\n"
            "Правила: не выдумывай факты; не путай секции "
            "(вопрос эксперту — только в expert_questions, навык — только в skills); "
            "если данных не хватает — формулируй вопрос в contradictions или expert_questions.\n"
            "Формат: JSON {sections:[{id,title,items:[...]}]}."
        ),
    },
    {
        "step_type": "scenario_plan",
        "role_name": "scenario_director",
        "version": "2",
        "content": (
            "Ты создаешь единый документ «Сценарий и съёмочный план» для иммерсивного модуля.\n"
            "Секции: passport, training_mode, diagnostic_mode, violation_categories, "
            "regulations, props, shooting_notes, constraints.\n"
            "Режим Обучение показывает правильное выполнение. "
            "Режим Диагностика показывает нарушения. В сегменте желательно 2–3 точки оценки.\n"
            "Каждый пункт: id, title, description (подробно), learning_goal, assessment_points[], "
            "props[], shooting_notes по возможности. Не оставляй пустые description.\n"
            "Аудиотекст не обязателен. Формат: JSON sections[]."
        ),
    },
    {
        "step_type": "chat_ask",
        "role_name": "project_assistant",
        "version": "2",
        "content": (
            "Ты отвечаешь на вопрос пользователя по проекту.\n"
            "Не меняй документ. Отвечай развёрнуто на русском: несколько абзацев, "
            "с опорой на brief, выжимки файлов, принятые решения и текущий артефакт. "
            "Укажи источник, если возможно. Если данных мало — скажи об этом и перечисли, чего не хватает."
        ),
    },
    {
        "step_type": "chat_local_edit",
        "role_name": "block_editor",
        "version": "2",
        "content": (
            "Ты вносишь локальное изменение в указанную цель: карточку или раздел.\n"
            "Если target_id — раздел (например expert_questions), добавляй/правь только его пункты. "
            "Не переноси «вопрос» в skills и наоборот.\n"
            "Для нового пункта в разделе: action=add_item, new={id,title,description,...}.\n"
            "Сохраняй стиль. Верни JSON patch: {changes:[{target_id, action?, old?, new, rationale}]}."
        ),
    },
    {
        "step_type": "chat_global_edit",
        "role_name": "document_editor",
        "version": "2",
        "content": (
            "Ты вносишь глобальное изменение во весь документ.\n"
            "Сохраняй ручные правки, если они не противоречат инструкции. "
            "Не удаляй информацию без причины. Пункты делай содержательными (title + description).\n"
            "Верни JSON: {summary, changes:[{target_id, old, new, rationale}]}."
        ),
    },
]

OPERATOR_PRESETS = [
    {
        "step_type": "draft_tz",
        "title": "Первичное ТЗ",
        "is_default": True,
        "content": (
            "Сформируй первичное техническое задание для 360°-тренажёрного модуля по материалам проекта.\n"
            "Сделай акцент на целях обучения, последовательности действий, типичных ошибках, критических рисках "
            "и наблюдаемых действиях сотрудника.\n"
            "Если не хватает данных по профессии или условиям работы, явно перечисли вопросы на уточнение."
        ),
    },
    {
        "step_type": "expert_synthesis",
        "title": "Сведение экспертного фидбека",
        "is_default": True,
        "content": (
            "Проанализируй замечания экспертов и собери итоговую согласованную версию ТЗ.\n"
            "Покажи:\n"
            "- что совпадает у экспертов;\n"
            "- где есть расхождения;\n"
            "- какие требования являются критичными;\n"
            "- какие элементы нужно обязательно отразить в финальном ТЗ.\n"
            "Не скрывай конфликты мнений."
        ),
    },
    {
        "step_type": "final_tz",
        "title": "Итоговое ТЗ",
        "is_default": True,
        "content": (
            "Собери итоговое ТЗ на основе утверждённых артефактов и синтеза экспертов.\n"
            "Структурируй документ по разделам. Укажи пробелы явно."
        ),
    },
    {
        "step_type": "scene_breakdown",
        "title": "Разбиение на сцены",
        "is_default": True,
        "content": (
            "Разбей утверждённое ТЗ на последовательные шаги, сцены и кадры для 360°-производства.\n"
            "Для каждой сцены укажи цель, действия, точку внимания, потенциальный риск, примерный тайминг "
            "и рекомендации по способу производства."
        ),
    },
    {
        "step_type": "production_planning",
        "title": "Production planning",
        "is_default": True,
        "content": (
            "Для каждой сцены определи способ производства: снять реально / сгенерировать ИИ / смешанный.\n"
            "Кратко обоснуй выбор."
        ),
    },
    {
        "step_type": "storyboard",
        "title": "Раскадровка",
        "is_default": True,
        "content": (
            "Сформируй раскадровку по утверждённому разбиению сцен.\n"
            "Для каждого кадра: описание, закадр, интерактив (если есть)."
        ),
    },
    {
        "step_type": "profession_map",
        "title": "Карта профессии",
        "is_default": True,
        "content": (
            "Сформируй карту профессии и основу диагностики: вид работ, навыки, "
            "точки оценки, ошибки, идеи сегментов, противоречия, вопросы экспертам, "
            "ограничения съёмки. Не выдумывай факты."
        ),
    },
    {
        "step_type": "scenario_plan",
        "title": "Сценарий и съёмочный план",
        "is_default": True,
        "content": (
            "Собери единый документ сценария и съёмочного плана по утверждённой карте профессии. "
            "Режим обучения — правильное выполнение, диагностика — нарушения и точки оценки."
        ),
    },
]


async def seed() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        # Admin — upsert so password/email stay in sync with env
        result = await db.execute(select(User).where(User.email == settings.bootstrap_admin_email))
        user = result.scalar_one_or_none()
        if user is None:
            # Migrate legacy seed email if present
            legacy = await db.execute(select(User).where(User.email == "admin@aistudio.local"))
            user = legacy.scalar_one_or_none()
            if user:
                user.email = settings.bootstrap_admin_email
                user.password_hash = hash_password(settings.bootstrap_admin_password)
                user.name = settings.bootstrap_admin_name
                print(f"Updated admin email → {settings.bootstrap_admin_email}")
            else:
                user = User(
                    id=uuid.uuid4(),
                    name=settings.bootstrap_admin_name,
                    email=settings.bootstrap_admin_email,
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="admin",
                )
                db.add(user)
                print(f"Created admin: {settings.bootstrap_admin_email}")
        else:
            user.password_hash = hash_password(settings.bootstrap_admin_password)
            print(f"Admin ready: {settings.bootstrap_admin_email}")

        # Providers: presets only. Sync catalog only when a key exists (no fake demos).
        providers = await ensure_provider_presets(db)
        for p in providers:
            if await provider_has_key(db, p):
                await sync_provider_models(db, p.id)
            else:
                print(f"Skip catalog sync for {p.name}: no API key")

        # System templates
        for tpl in SYSTEM_TEMPLATES:
            exists = await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.step_type == tpl["step_type"],
                    PromptTemplate.version == tpl["version"],
                )
            )
            if exists.scalar_one_or_none() is None:
                if tpl.get("is_active", True):
                    old = await db.execute(
                        select(PromptTemplate).where(
                            PromptTemplate.step_type == tpl["step_type"],
                            PromptTemplate.is_active.is_(True),
                        )
                    )
                    for row in old.scalars().all():
                        row.is_active = False
                db.add(PromptTemplate(**tpl, is_active=True))

        # Operator presets
        for preset in OPERATOR_PRESETS:
            exists = await db.execute(
                select(OperatorPromptPreset).where(
                    OperatorPromptPreset.step_type == preset["step_type"],
                    OperatorPromptPreset.title == preset["title"],
                )
            )
            if exists.scalar_one_or_none() is None:
                db.add(OperatorPromptPreset(**preset))

        # Optional: load YAML overlays from /prompts
        prompts_dir = Path(settings.prompts_dir)
        if prompts_dir.exists():
            for path in prompts_dir.glob("*.yaml"):
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                print(f"Loaded prompt overlay: {path.name} keys={list(data.keys())}")

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
