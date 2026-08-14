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
        "version": "3",
        "content": (
            "Ты выполняешь высокоточную выжимку документа по профессии, операции, инструкции, процедуре или нормативным требованиям.\n"
            "\n"
            "Твоя цель — сократить текст без потери существенного смысла. Приоритет: полнота критически важной информации выше краткости. "
            "Ты не пишешь свободное резюме; ты извлекаешь опорные факты из текста.\n"
            "\n"
            "Правила:\n"
            "1. Используй только информацию, явно содержащуюся в документе.\n"
            "2. Ничего не додумывай, не обобщай сверх текста и не подменяй формулировки более общими.\n"
            "3. Если фрагмент неясен, оборван, противоречив или выглядит неполным, укажи unclear.\n"
            "4. Не смешивай разные требования, этапы, ограничения или запреты в один пункт, если в тексте они различаются.\n"
            "5. Обязательно сохраняй:\n"
            "   - числовые значения, диапазоны, сроки, интервалы, единицы измерения;\n"
            "   - условия применения правила;\n"
            "   - исключения и оговорки;\n"
            "   - запреты и основания для нарушения;\n"
            "   - порядок действий и зависимости между шагами;\n"
            "   - роли, зоны ответственности, квалификационные требования;\n"
            "   - критерии допуска, проверки, приемки, браковки или отказа.\n"
            "6. Если документ содержит повторяющиеся положения, убирай только буквальные или явно дублирующие повторы, но не удаляй смысловые различия.\n"
            "7. Если в предоставленном тексте видна только часть документа, отрази это в constraints как ограничение анализа.\n"
            "8. Не пиши вводных фраз, пояснений к ответу, markdown и комментариев. Верни только валидный JSON.\n"
            "9. Если для какого-то поля в тексте нет данных, верни пустой массив [].\n"
            "\n"
            "Требования к полям:\n"
            "- brief_points: 7–12 содержательных и подробных пунктов, покрывающих предмет документа, ключевые действия, требования, ограничения, запреты, критерии и исключения. Каждый пункт должен передавать законченную мысль.\n"
            "- operations: полные формулировки операций, действий, этапов, проверок или процедур; по возможности сохраняй порядок.\n"
            "- skills: полные формулировки знаний, навыков, компетенций, допусков или требований к исполнителю, если они явно есть в тексте.\n"
            "- violations: полные формулировки нарушений, ошибок, запрещённых действий, несоответствий или оснований для отказа/санкций, если они явно есть в тексте.\n"
            "- visual_points: только те визуальные ориентиры, маркировки, схемы, таблицы, обозначения, цветовые признаки или элементы оформления, которые прямо описаны в тексте.\n"
            "- constraints: явные ограничения, условия применимости, пределы, запреты, допуски, предписания, зависимости, а также ограничение анализа, если предоставлен только фрагмент документа.\n"
            "- terms: значимые термины и их смысл только по тексту документа. Если термин есть, но его значение прямо не раскрыто, укажи \"unclear\".\n"
            "- important_fragments: короткие дословные цитаты из документа, которые несут ключевую норму, запрет, условие, число, срок, критерий или исключение.\n"
            "\n"
            "Формат ответа:\n"
            "{\n"
            "  \"brief_points\": [\"...\"],\n"
            "  \"operations\": [\"...\"],\n"
            "  \"skills\": [\"...\"],\n"
            "  \"violations\": [\"...\"],\n"
            "  \"visual_points\": [\"...\"],\n"
            "  \"constraints\": [\"...\"],\n"
            "  \"terms\": [\"...\"],\n"
            "  \"important_fragments\": [\"...\"]\n"
            "}"
        ),
    },
    {
        "step_type": "profession_map",
        "role_name": "profession_analyst",
        "version": "3",
        "content": (
            "Ты формируешь карту профессии и основу диагностического модуля.\n"
            "Вход: краткий brief, выжимки файлов, заметки, принятые решения.\n\n"
            "=== СТРУКТУРА ДОКУМЕНТА (задаёшь ты) ===\n"
            "Верни JSON {sections:[{id?, title, items:[...]}]}.\n"
            "Сам определи набор разделов, подходящий проекту. Пример для типового VR-модуля:\n"
            "1) Вид работ для оценки\n"
            "2) Оцениваемые навыки\n"
            "3) Точки оценки\n"
            "4) Частые ошибки и опасные ситуации\n"
            "5) Идеи видеосегментов\n"
            "6) Противоречия и пробелы\n"
            "7) Вопросы для экспертов\n"
            "8) Ограничения для съёмки\n"
            "Можешь добавить, объединить или убрать разделы — если это оправдано brief.\n"
            "Для каждого раздела: title (человекочитаемо), id (slug snake_case, уникальный; можно опустить).\n\n"
            "=== ПУНКТЫ ВНУТРИ РАЗДЕЛОВ ===\n"
            "Минимум 3–5 пунктов на раздел. У каждого: id, title, description (2–5 предложений).\n"
            "Дополнительные поля по смыслу раздела, например: why_it_matters, observable_cues[], "
            "source_hint, criticality, in_scope[], out_of_scope[].\n\n"
            "=== ПРАВИЛА ===\n"
            "Не выдумывай факты. Не смешивай типы контента между разделами "
            "(вопрос эксперту — не в навыки). Если данных мало — фиксируй пробел в contradictions "
            "или expert_questions. Не оставляй пустые description."
        ),
    },
    {
        "step_type": "scenario_plan",
        "role_name": "scenario_director",
        "version": "3",
        "content": (
            "Ты создаёшь единый документ «Сценарий и съёмочный план» для иммерсивного модуля.\n\n"
            "=== СТРУКТУРА ДОКУМЕНТА (задаёшь ты) ===\n"
            "Верни JSON {sections:[{id?, title, items:[...]}]}.\n"
            "Типовой набор разделов (адаптируй под проект):\n"
            "паспорт сценария, режим «Обучение», режим «Диагностика», категории нарушений, "
            "правила и регламенты, реквизит и ресурсы, съёмочные замечания, ограничения.\n"
            "title — на русском; id — slug или опусти.\n\n"
            "=== ПУНКТЫ ===\n"
            "Каждый пункт: id, title, description (подробно). По смыслу: learning_goal, "
            "assessment_points[], props[], shooting_notes, frames[] для сегментов.\n"
            "Обучение — правильное выполнение; диагностика — нарушения и точки оценки.\n"
            "Аудиотекст не обязателен. Не оставляй пустые description."
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
        "version": "3",
        "content": (
            "Ты вносишь локальное изменение в указанную цель: карточку или раздел.\n"
            "target_id — id из текущего документа (карточки или раздела). "
            "Если это раздел — добавляй/правь только его пункты; не переноси в другие секции.\n"
            "Для нового пункта: action=add_item, new={id,title,description,...} — "
            "сохраняй те же поля, что у соседних пунктов раздела.\n"
            "Верни JSON patch: {changes:[{target_id, action?, old?, new, rationale}]}."
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
