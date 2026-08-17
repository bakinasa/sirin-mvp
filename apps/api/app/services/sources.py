"""Upload, parse, chunk and summarize project source files."""

from __future__ import annotations

import io
import json
import logging
import uuid
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import ParseStatus, SourceType
from app.models import ProjectSource, ProjectSourceChunk
from app.services.storage import delete_object_by_url, upload_bytes

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
    if not (text or "").strip():
        source.parse_status = ParseStatus.FAILED.value
        source.parse_error = (
            "Из файла не удалось извлечь текст. Часто так бывает со сканами PDF без текстового слоя. "
            "Загрузите DOCX/TXT или PDF, где текст можно выделить мышью."
        )
        source.summary_short_json = []
        source.summary_structured_json = {}
        source.important_chunks_json = []
        await db.flush()
        await db.refresh(source)
        return source

    await _replace_chunks(db, source, chunk_text(text))

    source.parse_status = ParseStatus.SUMMARIZING.value
    await db.flush()
    try:
        await summarize_source(
            db, source, user_id, primary_model_id, fallback_model_id
        )
        source.parse_status = ParseStatus.READY.value
        source.parse_error = ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary failed for source %s: %s", source.id, exc)
        source.parse_status = ParseStatus.FAILED.value
        source.parse_error = f"Выжимка не удалась: {exc}"
        source.summary_short_json = []
        source.summary_structured_json = {}
        source.important_chunks_json = []
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
    from app.services.generation import _resolve_models
    from app.services.json_content import summary_has_content
    from app.services.prompt_assembler import get_active_system_template

    template = await get_active_system_template(db, "source_summary")
    system = template.content if template else SOURCE_SUMMARY_PROMPT
    primary, fallback = await _resolve_models(
        db, user_id, source.project_id, "source_summary", primary_model_id, fallback_model_id
    )
    models = [m for m in (primary, fallback) if m is not None]
    if not models:
        raise RuntimeError("Нет доступной модели для выжимки. Добавьте модель на странице «Модели».")

    parts = _split_for_summary(source.parsed_text or "")
    part_summaries: list[dict[str, Any]] = []
    last_error = ""
    for index, part in enumerate(parts):
        assembled = {
            "system_prompt": system,
            "user_message": _summary_user_message(
                source.title,
                source.source_type,
                part,
                part_index=index,
                part_count=len(parts),
            ),
        }
        summary = None
        for model in models:
            try:
                summary = await _summarize_once(db, model, assembled)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("Summary call failed (%s part %s): %s", model.model_id, index + 1, exc)
        if not summary:
            raise RuntimeError(last_error or "Модель вернула пустой ответ на выжимку")
        part_summaries.append(summary)

    merged = _merge_summaries(part_summaries)
    if not summary_has_content(merged):
        raise RuntimeError("После объединения частей выжимка всё ещё пустая")

    source.summary_short_json = merged["brief_points"]
    source.summary_structured_json = {
        "operations": merged["operations"],
        "skills": merged["skills"],
        "violations": merged["violations"],
        "visual_points": merged["visual_points"],
        "constraints": merged["constraints"],
        "terms": merged["terms"],
    }
    source.important_chunks_json = merged["important_fragments"]
    source.parse_error = ""


async def _summarize_once(db, model, assembled: dict[str, Any]) -> dict[str, Any]:
    from app.services.generation import _call_model, _parse_json_content
    from app.services.json_content import extract_source_summary, summary_has_content

    attempts = (
        {"response_json": False, "max_tokens": 16384, "timeout_seconds": 240},
        {"response_json": True, "max_tokens": 8192, "timeout_seconds": 240},
    )
    errors: list[str] = []
    for kwargs in attempts:
        try:
            result = await _call_model(db, model, assembled, "source_summary", **kwargs)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            continue
        content = (result.content or "").strip()
        if not content:
            finish = ""
            raw = result.raw or {}
            choices = raw.get("choices") or []
            if choices:
                finish = str(choices[0].get("finish_reason") or "")
            errors.append(
                f"пустой ответ модели (tokens {result.token_input}/{result.token_output}"
                f"{', finish=' + finish if finish else ''})"
            )
            continue
        summary = extract_source_summary(_parse_json_content(content))
        if not summary_has_content(summary):
            summary = extract_source_summary(content)
        if summary_has_content(summary):
            return summary
        errors.append("ответ модели не разобрался как JSON выжимки")
    raise RuntimeError("; ".join(errors) or "не удалось получить выжимку")


def _summary_user_message(
    title: str,
    source_type: str,
    text: str,
    *,
    part_index: int,
    part_count: int,
) -> str:
    part_note = ""
    if part_count > 1:
        part_note = (
            f"Это часть {part_index + 1} из {part_count} документа. "
            "Сделай выжимку этой части; не пиши, что данных нет, если в части есть факты.\n\n"
        )
    return (
        f"Файл: {title}\n"
        f"Тип: {source_type}\n\n"
        f"{part_note}"
        "Проанализируй только текст между маркерами.\n"
        "Сохраняй критические детали: числа, единицы измерения, сроки, роли, последовательности действий, "
        "условия, исключения, запреты, критерии проверки и основания для нарушений.\n"
        "Не объединяй разные нормы в один общий пункт.\n"
        "Верни ТОЛЬКО JSON.\n\n"
        f"=== DOCUMENT TEXT ===\n{text}\n=== END ==="
    )


def _split_for_summary(text: str, size: int = 24000, overlap: int = 600) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return parts


def _merge_summaries(parts: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "brief_points",
        "operations",
        "skills",
        "violations",
        "visual_points",
        "constraints",
        "terms",
        "important_fragments",
    )
    merged = {key: [] for key in keys}
    seen = {key: set() for key in keys}
    for part in parts:
        for key in keys:
            for item in part.get(key) or []:
                marker = item.strip() if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                if not marker or marker in seen[key]:
                    continue
                seen[key].add(marker)
                merged[key].append(item)
    return merged


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


async def delete_source(db: AsyncSession, source: ProjectSource) -> None:
    """Remove source, chunks and original file. Summaries live on the source row."""
    delete_object_by_url(source.file_path)
    await db.delete(source)
    await db.flush()


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


def _safe_filename(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (name or "file"))
    return keep[:180] or "file"
