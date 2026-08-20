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
from app.operator_preset_defaults import OPERATOR_PRESETS
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
        "version": "4",
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
            "- visual_points: только те визуальные ориентиры, маркировки, схемы, таблицы, обозначения, цветовые признаки или элементы оформления, которые прямо описаны в тексте. "
            "Если в документе сказано, что должно быть видно крупно / акцент в кадре — сохраняй это как отдельный пункт.\n"
            "- constraints: явные ограничения, условия применимости, пределы, запреты, допуски, предписания, зависимости, а также ограничение анализа, если предоставлен только фрагмент документа. "
            "Если документ — сценарный/съёмочный план, а не нормативный регламент, явно укажи это.\n"
            "- terms: значимые термины и их смысл только по тексту документа. Если термин есть, но его значение прямо не раскрыто, укажи \"unclear\".\n"
            "- important_fragments: короткие дословные цитаты из документа, которые несут ключевую норму, запрет, условие, число, срок, критерий или исключение.\n"
            "\n"
            "Приоритеты извлечения для сценарных материалов:\n"
            "- В operations сохраняй названия сцен и этапов, если они есть в тексте, в исходном порядке.\n"
            "- В violations сохраняй формулировку нарушения вместе с категорией, если категория дана.\n"
            "- В visual_points отдельно сохраняй формулировки вида «что должно быть видно крупно / акцент».\n"
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
        "role_name": "pre_scenario_analyst",
        "version": "9",
        "content": (
            "Ты формируешь предсценарный сюжет диагностического VR/360-модуля.\n"
            "Вход: brief проекта, выжимки файлов, заметки, принятые решения.\n\n"
            "Документ содержит три РАЗДЕЛА (sections): work_storylines, assessment_points, expert_questions. "
            "«Три раздела» — это типы секций, а НЕ лимит «по три пункта». "
            "Количество items в каждом разделе определяется данными проекта, без искусственного ограничения тремя.\n"
            "Не добавляй why_it_matters, frames, evaluated_skills, work_variants, preliminary_storylines.\n\n"
            "Правила:\n"
            "1. Используй только данные проекта. Не выдумывай факты.\n"
            "2. Если в материалах мало данных — меньше карточек work_storylines/assessment_points; "
            "в expert_questions клади только реальные неясности, которые нельзя закрыть чтением документов "
            "(лучше 2–4 сильных вопроса, чем список очевидных).\n"
            "3. Не пиши markdown и пояснения. Верни только JSON.\n"
            "4. Не своди результат к «типовым трём сценариям» — извлекай все виды работ из материалов.\n\n"
            "Секции:\n"
            "- work_storylines «Варианты работ и сюжет»: вид работ + укрупнённый сюжет. "
            "Извлеки ВСЕ различимые виды работ из brief и выжимок (СОП, регламенты, инструкции, чек-листы). "
            "Если в материалах 5–10 процедур — создай 5–10 карточек. Не менее одного, без верхнего ограничения. "
            "Поля: title, description, story_steps[] (шаги), attention_focus (строка или короткий список — фокус внимания в кадре).\n"
            "- assessment_points «Навыки и точки оценки»: ровно одна карточка на каждый вид работ из work_storylines "
            "(title совпадает). description — краткий контекст. "
            "errors[] — все типичные наблюдаемые ошибки для этого вида работ из материалов, не менее 3 на карточку, "
            "без верхнего лимита: "
            "{error: что именно сделано неправильно, correct: как надо делать, visual_cues[]: как это видно в кадре}. "
            "Нет отдельных error_observation/correct_observation.\n"
            "- expert_questions «Вопросы экспертам»: цель — получить от эксперта то, чего НЕТ в документах "
            "и что нельзя надёжно додумать самому по материалам проекта. "
            "Задавай вопрос только если одновременно верно всё:\n"
            "  (a) в материалах есть конкретная неясность: противоречие между источниками, пропуск критичного шага/"
            "порога/критерия, спор «обязательно vs рекомендуемо», граничный случай без правила;\n"
            "  (b) внимательный читатель документов НЕ может сам выбрать правильный вариант без эксперта;\n"
            "  (c) ответ нужен для сюжета или диагностики конкретного вида работ (границы процедуры, "
            "обязательные шаги, что считать критичной ошибкой в кадре).\n"
            "НЕ спрашивай очевидное и НЕ заполняй квоту вопросов:\n"
            "  — то, что уже явно сказано в СОП/brief/выжимках;\n"
            "  — общие или «учебниковые» вопросы (СИЗ, «какие ошибки бывают», «как правильно делать»), "
            "если ответ уже следует из материалов или это стандарт отрасли без конфликта в документах;\n"
            "  — вопросы «на всякий случай», уточнения ради полноты, пересказ известных фактов в форме вопроса.\n"
            "Количество: 0–8. Если документы согласованы и достаточны — меньше вопросов или пустой список. "
            "Качество важнее количества.\n"
            "title — конкретный вопрос эксперту (не общий); description — что уже ясно из материалов и какая "
            "именно неясность остаётся (со ссылкой: «в СОП A сказано …, в инструкции B — … / не указано …»); "
            "why_needed — почему без ответа нельзя корректно собрать work_storylines или errors[] для этого вида работ; "
            "answer — пустая строка.\n\n"
            "Структура ответа:\n"
            "{\n"
            "  \"sections\": [\n"
            "    {\"id\": \"work_storylines\", \"title\": \"Варианты работ и сюжет\", \"items\": [\n"
            "      {\"id\": \"string\", \"title\": \"string\", \"description\": \"2–4 предложения\", "
            "\"story_steps\": [\"шаг\"], \"attention_focus\": \"что должно быть видно\"}\n"
            "    ]},\n"
            "    {\"id\": \"assessment_points\", \"title\": \"Навыки и точки оценки\", \"items\": [\n"
            "      {\"id\": \"string\", \"title\": \"string\", \"description\": \"string\", "
            "\"errors\": [{\"error\": \"string\", \"correct\": \"string\", \"visual_cues\": [\"string\"]}]}\n"
            "    ]},\n"
            "    {\"id\": \"expert_questions\", \"title\": \"Вопросы экспертам\", \"items\": [\n"
            "      {\"id\": \"string\", \"title\": \"string\", \"description\": \"string\", "
            "\"why_needed\": \"string\", \"answer\": \"\"}\n"
            "    ]}\n"
            "  ],\n"
            "  \"clarifications_needed\": []\n"
            "}"
        ),
    },
    {
        "step_type": "scenario_plan",
        "role_name": "scenario_director",
        "version": "8",
        "content": (
            "Ты создаёшь сценарий VR/360-модуля: только обучающие и диагностические сцены.\n"
            "Опирайся только на текущий сюжет шага 2 и блок «Вопросы экспертам и ответы». "
            "Не требуй сырые выжимки файлов, не раздувай brief, не придумывай паспорт, microtexts и съёмочный план.\n\n"
            "Верни только две секции: training_scenes и diagnostic_scenes.\n\n"
            "Соответствие сюжету (обязательно):\n"
            "- Для КАЖДОГО item в work_storylines создай ровно одну сцену в training_scenes "
            "и ровно одну в diagnostic_scenes с тем же title (дословно).\n"
            "- len(training_scenes) === len(diagnostic_scenes) === len(work_storylines). "
            "Не пропускай виды работ и не объединяй несколько в одну сцену.\n"
            "- Если для вида работ нет данных в assessment_points — укажи это в clarifications_needed, "
            "но сцену всё равно создай с минимальным каркасом кадров.\n\n"
            "Сжатость (важно для стабильного ответа):\n"
            "- На обучающую сцену: 4–6 кадров; audio_text 1–3 коротких предложения.\n"
            "- На диагностическую сцену: 5–7 кадров; минимум 2 кадра с непустым violation "
            "(3+ если ошибок в assessment_points больше).\n"
            "- Пиши кратко: action и accent — одна фраза; description в violation_categories — 1–2 предложения.\n"
            "- Не дублируй длинные тексты между сценами.\n\n"
            "Правила:\n"
            "1. Не выдумывай нормативы, роли и ограничения, которых нет в сюжете или ответах экспертов.\n"
            "2. Обучение и диагностика соответствуют одним этапам работы для каждого title.\n"
            "3. Ошибки визуально наблюдаемы и воспроизводимы актёрами в 360-видео.\n"
            "4. Не пиши markdown. Верни только JSON.\n"
            "5. Диагностика — это сценарий с намеренно показанными ошибками, а не повтор обучения.\n\n"
            "Обучающая сцена:\n"
            "title — вид работ; actors — текст; location — текст; "
            "frames[] — shot_no, action, accent; "
            "audio_text — краткая голосовая инструкция; "
            "regulations[] — названия документов/СОП; props — реквизит.\n\n"
            "Диагностическая сцена:\n"
            "title, actors, location; frames[]: shot_no, action, violation, accent.\n"
            "Часть кадров — норма (violation = \"\"), часть — с ошибкой (violation заполнено).\n"
            "В кадре с ошибкой: action — что делается неправильно; violation — краткая формулировка.\n"
            "ЗАПРЕЩЕНО: оставлять violation пустым во всех кадрах и переносить ошибки только в violation_categories.\n"
            "Ошибки бери из assessment_points/errors[].\n"
            "violation_categories[] — {title, violation, description}; regulations[]; props.\n\n"
            "Структура ответа: {\"sections\": ["
            "{\"id\": \"training_scenes\", \"title\": \"Обучающие сцены\", \"items\": [...]}, "
            "{\"id\": \"diagnostic_scenes\", \"title\": \"Диагностические сцены\", \"items\": [...]}"
            "], \"clarifications_needed\": []}"
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

        # System templates — upsert by (step_type, version); activate latest seeded version
        for tpl in SYSTEM_TEMPLATES:
            exists = await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.step_type == tpl["step_type"],
                    PromptTemplate.version == tpl["version"],
                )
            )
            row = exists.scalar_one_or_none()
            if row is None:
                if tpl.get("is_active", True):
                    old = await db.execute(
                        select(PromptTemplate).where(
                            PromptTemplate.step_type == tpl["step_type"],
                            PromptTemplate.is_active.is_(True),
                        )
                    )
                    for old_row in old.scalars().all():
                        old_row.is_active = False
                db.add(PromptTemplate(**tpl, is_active=True))
            else:
                row.role_name = tpl["role_name"]
                row.content = tpl["content"]
                if tpl.get("is_active", True):
                    row.is_active = True
                    old = await db.execute(
                        select(PromptTemplate).where(
                            PromptTemplate.step_type == tpl["step_type"],
                            PromptTemplate.is_active.is_(True),
                            PromptTemplate.id != row.id,
                        )
                    )
                    for old_row in old.scalars().all():
                        old_row.is_active = False
                print(f"Updated system template {tpl['step_type']} v{tpl['version']}")

        # Operator presets: create default if missing. Do not overwrite content —
        # operators edit these in the pipeline and seed must not clobber them.
        for preset in OPERATOR_PRESETS:
            exists = await db.execute(
                select(OperatorPromptPreset).where(
                    OperatorPromptPreset.step_type == preset["step_type"],
                    OperatorPromptPreset.is_default.is_(True),
                )
            )
            row = exists.scalars().first()
            if row is None:
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
