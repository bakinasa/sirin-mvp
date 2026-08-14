"""Upload, parse, chunk and summarize project source files."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import ParseStatus, SourceType
from app.models import ProjectSource, ProjectSourceChunk
from app.services.storage import upload_bytes

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1100
CHUNK_OVERLAP = 150

SOURCE_SUMMARY_PROMPT = """Ты выполняешь высокоточную выжимку документа по профессии, операции, инструкции, процедуре или нормативным требованиям.

Твоя цель — сократить текст без потери существенного смысла. Приоритет: полнота критически важной информации выше краткости. Ты не пишешь свободное резюме; ты извлекаешь опорные факты из текста.

Правила:
1. Используй только информацию, явно содержащуюся в документе.
2. Ничего не додумывай, не обобщай сверх текста и не подменяй формулировки более общими.
3. Если фрагмент неясен, оборван, противоречив или выглядит неполным, укажи unclear.
4. Не смешивай разные требования, этапы, ограничения или запреты в один пункт, если в тексте они различаются.
5. Обязательно сохраняй:
   - числовые значения, диапазоны, сроки, интервалы, единицы измерения;
   - условия применения правила;
   - исключения и оговорки;
   - запреты и основания для нарушения;
   - порядок действий и зависимости между шагами;
   - роли, зоны ответственности, квалификационные требования;
   - критерии допуска, проверки, приемки, браковки или отказа.
6. Если документ содержит повторяющиеся положения, убирай только буквальные или явно дублирующие повторы, но не удаляй смысловые различия.
7. Если в предоставленном тексте видна только часть документа, отрази это в constraints как ограничение анализа.
8. Не пиши вводных фраз, пояснений к ответу, markdown и комментариев. Верни только валидный JSON.
9. Если для какого-то поля в тексте нет данных, верни пустой массив [].

Требования к полям:
- brief_points: 7–12 содержательных и подробных пунктов, покрывающих предмет документа, ключевые действия, требования, ограничения, запреты, критерии и исключения. Каждый пункт должен передавать законченную мысль.
- operations: полные формулировки операций, действий, этапов, проверок или процедур; по возможности сохраняй порядок.
- skills: полные формулировки знаний, навыков, компетенций, допусков или требований к исполнителю, если они явно есть в тексте.
- violations: полные формулировки нарушений, ошибок, запрещённых действий, несоответствий или оснований для отказа/санкций, если они явно есть в тексте.
- visual_points: только те визуальные ориентиры, маркировки, схемы, таблицы, обозначения, цветовые признаки или элементы оформления, которые прямо описаны в тексте.
- constraints: явные ограничения, условия применимости, пределы, запреты, допуски, предписания, зависимости, а также ограничение анализа, если предоставлен только фрагмент документа.
- terms: значимые термины и их смысл только по тексту документа. Если термин есть, но его значение прямо не раскрыто, укажи "unclear".
- important_fragments: короткие дословные цитаты из документа, которые несут ключевую норму, запрет, условие, число, срок, критерий или исключение.

Формат ответа:
{
  "brief_points": ["..."],
  "operations": ["..."],
  "skills": ["..."],
  "violations": ["..."],
  "visual_points": ["..."],
  "constraints": ["..."],
  "terms": ["..."],
  "important_fragments": ["..."]
}
"""


def guess_source_type(filename: str, mime: str) -> str:
    name = (filename or "").lower()
    if "sop" in name or "соп" in name:
        return SourceType.SOP.value
    if "check" in name or "чек" in name:
        return SourceType.CHECKLIST.value
    if "pdd" in name or "пдд" in name or "регламент" in name:
        return SourceType.REGULATION.value
    if "note" in name or "замет" in name or "интерв" in name:
        return SourceType.INTERVIEW_NOTE.value
    if "instruct" in name or "инструк" in name:
        return SourceType.INSTRUCTION.value
    if mime.startswith("image/"):
        return SourceType.NOTE.value
    return SourceType.OTHER.value


def parse_file_bytes(filename: str, mime: str, data: bytes) -> tuple[str, str]:
    """Return (text, parse_status)."""
    name = (filename or "").lower()
    mime = (mime or "").lower()
    try:
        if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
            return "", ParseStatus.UNSUPPORTED.value
        if mime == "application/pdf" or name.endswith(".pdf"):
            return _parse_pdf(data), ParseStatus.READY.value
        if (
            mime
            in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/msword",
            )
            or name.endswith(".docx")
        ):
            return _parse_docx(data), ParseStatus.READY.value
        if mime.startswith("text/") or name.endswith((".txt", ".md", ".csv")):
            return data.decode("utf-8", errors="replace"), ParseStatus.READY.value
        # Try utf-8 as last resort for unknown text-ish types.
        sample = data[:200]
        if b"\x00" not in sample:
            try:
                return data.decode("utf-8"), ParseStatus.READY.value
            except UnicodeDecodeError:
                pass
        return "", ParseStatus.UNSUPPORTED.value
    except Exception as exc:  # noqa: BLE001
        logger.warning("Parse failed for %s: %s", filename, exc)
        return "", ParseStatus.FAILED.value


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[page {i + 1}]\n{text.strip()}")
    return "\n\n".join(parts)


def _parse_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def chunk_text(text: str) -> list[tuple[int, str, str]]:
    """Return list of (index, text, page_ref)."""
    if not text.strip():
        return []
    pages = text.split("[page ")
    chunks: list[tuple[int, str, str]] = []
    idx = 0
    if len(pages) > 1:
        for part in pages:
            if not part.strip():
                continue
            if "]" in part[:8]:
                page_no, rest = part.split("]", 1)
                page_ref = page_no.strip()
                body = rest.strip()
            else:
                page_ref = ""
                body = part.strip()
            for piece in _window(body):
                chunks.append((idx, piece, page_ref))
                idx += 1
        return chunks
    for piece in _window(text):
        chunks.append((idx, piece, ""))
        idx += 1
    return chunks


def _window(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    out = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            cut = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if cut > start:
                end = cut
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [c for c in out if c]


async def create_source_from_upload(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    filename: str,
    mime: str,
    data: bytes,
    source_type: Optional[str] = None,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> ProjectSource:
    object_name = (
        f"projects/{project_id}/sources/{uuid.uuid4().hex}_{_safe_filename(filename)}"
    )
    url = upload_bytes(object_name, data, mime or "application/octet-stream")
    source = ProjectSource(
        project_id=project_id,
        title=filename,
        source_type=source_type or guess_source_type(filename, mime),
        file_path=url,
        mime_type=mime or "",
        parse_status=ParseStatus.PENDING.value,
        created_by=user_id,
    )
    db.add(source)
    await db.flush()
    await process_source(
        db,
        source,
        user_id=user_id,
        raw=data,
        filename=filename,
        mime=mime,
        primary_model_id=primary_model_id,
        fallback_model_id=fallback_model_id,
    )
    return source


async def process_source(
    db: AsyncSession,
    source: ProjectSource,
    *,
    user_id: UUID,
    raw: bytes | None = None,
    filename: str | None = None,
    mime: str | None = None,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> ProjectSource:
    source.parse_status = ParseStatus.PARSING.value
    source.parse_error = ""
    await db.flush()

    text, status = parse_file_bytes(
        filename or source.title, mime or source.mime_type, raw or b""
    )
    if raw is None:
        # reprocess uses already stored parsed_text if we cannot re-download
        text = source.parsed_text
        status = ParseStatus.READY.value if text else source.parse_status

    if status == ParseStatus.UNSUPPORTED.value:
        source.parse_status = ParseStatus.UNSUPPORTED.value
        source.parse_error = "Формат не поддерживается для извлечения текста (OCR не включён)."
        await db.flush()
        return source
    if status == ParseStatus.FAILED.value and not text:
        source.parse_status = ParseStatus.FAILED.value
        source.parse_error = "Не удалось извлечь текст из файла."
        await db.flush()
        return source

    source.parsed_text = text
    chunk_objs = await _replace_chunks(db, source, chunk_text(text))

    source.parse_status = ParseStatus.SUMMARIZING.value
    await db.flush()
    try:
        await summarize_source(
            db, source, user_id, primary_model_id, fallback_model_id
        )
        source.parse_status = ParseStatus.READY.value
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary failed for source %s: %s", source.id, exc)
        source.summary_short_json = _fallback_short_summary(text)
        source.summary_structured_json = {"note": "Выжимка без модели", "excerpt": text[:1500]}
        source.important_chunks_json = [
            {"text": c.text[:400], "page_ref": c.page_ref}
            for c in chunk_objs[:5]
        ]
        source.parse_status = ParseStatus.READY.value
        source.parse_error = f"Выжимка по заглушке: {exc}"
    await db.flush()
    await db.refresh(source)
    return source


async def reprocess_source(
    db: AsyncSession,
    source: ProjectSource,
    user_id: UUID,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> ProjectSource:
    return await process_source(
        db,
        source,
        user_id=user_id,
        raw=None,
        primary_model_id=primary_model_id,
        fallback_model_id=fallback_model_id,
    )


async def summarize_source(
    db: AsyncSession,
    source: ProjectSource,
    user_id: UUID,
    primary_model_id: Optional[UUID] = None,
    fallback_model_id: Optional[UUID] = None,
) -> None:
    from app.services.generation import _call_model, _parse_json_content, _resolve_models
    from app.services.prompt_assembler import get_active_system_template

    template = await get_active_system_template(db, "source_summary")
    system = template.content if template else SOURCE_SUMMARY_PROMPT
    excerpt = source.parsed_text[:12000]
    assembled = {
        "system_prompt": system,
        "user_message": (
            f"Файл: {source.title}\n"
            f"Тип: {source.source_type}\n\n"
            "Проанализируй только текст между маркерами.\n"
            "Если текст выглядит обрезанным, неполным или начинается/заканчивается на середине мысли, "
            "отрази это в constraints.\n"
            "Сохраняй критические детали: числа, единицы измерения, сроки, роли, последовательности действий, "
            "условия, исключения, запреты, критерии проверки и основания для нарушений.\n"
            "Не объединяй разные нормы в один общий пункт.\n"
            "Верни ТОЛЬКО JSON.\n\n"
            f"=== DOCUMENT TEXT ===\n{excerpt}\n=== END ==="
        ),
    }
    primary, fallback = await _resolve_models(
        db, user_id, source.project_id, "source_summary", primary_model_id, fallback_model_id
    )
    result = None
    last_error = ""
    for model in (primary, fallback):
        if model is None:
            continue
        try:
            result = await _call_model(db, model, assembled)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
    if result is None:
        raise RuntimeError(last_error or "no model")
    payload = _parse_json_content(result.content)
    if not isinstance(payload, dict):
        payload = {"brief_points": [str(payload)]}
    source.summary_short_json = payload.get("brief_points") or payload.get("short") or []
    source.summary_structured_json = {
        "operations": payload.get("operations") or [],
        "skills": payload.get("skills") or [],
        "violations": payload.get("violations") or [],
        "visual_points": payload.get("visual_points") or [],
        "constraints": payload.get("constraints") or [],
        "terms": payload.get("terms") or [],
    }
    source.important_chunks_json = payload.get("important_fragments") or []


async def search_chunks(
    db: AsyncSession, project_id: UUID, query: str, limit: int = 8
) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    q = (
        select(ProjectSourceChunk, ProjectSource)
        .join(ProjectSource, ProjectSourceChunk.source_id == ProjectSource.id)
        .where(ProjectSource.project_id == project_id)
        .where(ProjectSourceChunk.text.ilike(f"%{query.strip()[:200]}%"))
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    if rows:
        return [
            {
                "source_id": str(src.id),
                "source_title": src.title,
                "chunk_index": chunk.chunk_index,
                "page_ref": chunk.page_ref,
                "text": chunk.text[:800],
            }
            for chunk, src in rows
        ]
    # Fallback: return first chunks from each source if no lexical hit.
    sources = (
        await db.execute(
            select(ProjectSource)
            .where(ProjectSource.project_id == project_id)
            .options(selectinload(ProjectSource.chunks))
        )
    ).scalars().all()
    out = []
    for src in sources:
        for chunk in sorted(src.chunks, key=lambda c: c.chunk_index)[:2]:
            out.append(
                {
                    "source_id": str(src.id),
                    "source_title": src.title,
                    "chunk_index": chunk.chunk_index,
                    "page_ref": chunk.page_ref,
                    "text": chunk.text[:800],
                }
            )
            if len(out) >= limit:
                return out
    return out


async def list_sources(db: AsyncSession, project_id: UUID) -> list[ProjectSource]:
    result = await db.execute(
        select(ProjectSource)
        .where(ProjectSource.project_id == project_id)
        .order_by(ProjectSource.created_at.desc())
    )
    return list(result.scalars().all())


def source_to_out(source: ProjectSource, *, detail: bool = False) -> dict[str, Any]:
    payload = {
        "id": source.id,
        "project_id": source.project_id,
        "title": source.title,
        "source_type": source.source_type,
        "file_path": source.file_path,
        "mime_type": source.mime_type,
        "parse_status": source.parse_status,
        "parse_error": source.parse_error,
        "summary_short_json": source.summary_short_json,
        "summary_structured_json": source.summary_structured_json,
        "important_chunks_json": source.important_chunks_json,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "has_parsed_text": bool(source.parsed_text),
    }
    if detail:
        payload["parsed_text"] = (source.parsed_text or "")[:20000]
        payload["chunks"] = [
            {"id": str(c.id), "chunk_index": c.chunk_index, "page_ref": c.page_ref, "text": c.text[:1200]}
            for c in sorted(source.chunks, key=lambda x: x.chunk_index)
        ]
    return payload


async def _replace_chunks(
    db: AsyncSession, source: ProjectSource, chunks: list[tuple[int, str, str]]
) -> list[ProjectSourceChunk]:
    await db.execute(delete(ProjectSourceChunk).where(ProjectSourceChunk.source_id == source.id))
    objects = [
        ProjectSourceChunk(
            source_id=source.id, chunk_index=idx, text=text, page_ref=page_ref
        )
        for idx, text, page_ref in chunks
    ]
    db.add_all(objects)
    await db.flush()
    return objects


def _fallback_short_summary(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[:8] or ["Текст извлечён, но выжимка не построена."]


def _safe_filename(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (name or "file"))
    return keep[:180] or "file"
