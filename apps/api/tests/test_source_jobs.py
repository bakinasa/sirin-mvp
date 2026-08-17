"""Tests for source splitting and summary job helpers."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_jobs import build_summary_job, summary_progress
from app.services.sources import (
    SUMMARY_PART_SIZE,
    _merge_summaries,
    _split_for_summary,
    summarize_source,
)


class SplitForSummaryTests(unittest.TestCase):
    def test_small_text_single_part(self):
        text = "короткий документ"
        self.assertEqual(_split_for_summary(text), [text])

    def test_page_aware_split_keeps_markers(self):
        pages = [f"[page {i}]\n{'Текст страницы ' + str(i) + '. ' * 400}" for i in range(1, 25)]
        text = "\n\n".join(pages)
        parts = _split_for_summary(text)
        self.assertGreater(len(parts), 1)
        joined = "\n\n".join(parts)
        self.assertIn("[page 1]", joined)
        self.assertIn("[page 24]", joined)
        for part in parts:
            self.assertLessEqual(len(part), SUMMARY_PART_SIZE + 500)

    def test_hundred_page_estimate(self):
        pages = [f"[page {i}]\n{'СОП пункт. ' * 120}" for i in range(1, 101)]
        text = "\n\n".join(pages)
        parts = _split_for_summary(text)
        self.assertGreaterEqual(len(parts), 8)
        self.assertLessEqual(len(parts), 20)


class MergeSummaryTests(unittest.TestCase):
    def test_merge_deduplicates(self):
        merged = _merge_summaries(
            [
                {"brief_points": ["A", "B"], "operations": [], "skills": [], "violations": [], "visual_points": [], "constraints": [], "terms": [], "important_fragments": []},
                {"brief_points": ["B", "C"], "operations": ["Op1"], "skills": [], "violations": [], "visual_points": [], "constraints": [], "terms": [], "important_fragments": []},
            ]
        )
        self.assertEqual(merged["brief_points"], ["A", "B", "C"])
        self.assertEqual(merged["operations"], ["Op1"])


class SummaryJobTests(unittest.TestCase):
    def test_progress_percent(self):
        class Source:
            summary_job_json = {
                "status": "running",
                "part_done": 2,
                "part_total": 8,
                "message": "Выжимка: часть 2/8",
            }

        progress = summary_progress(Source())
        self.assertEqual(progress["percent"], 25)
        self.assertEqual(progress["part_total"], 8)


class ParallelSummarizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_parts_preserve_order(self):
        source = type(
            "Source",
            (),
            {
                "id": uuid4(),
                "project_id": uuid4(),
                "title": "Test SOP",
                "source_type": "sop",
                "parsed_text": "PartA " * 9000 + "PartB " * 9000,
                "summary_short_json": [],
                "summary_structured_json": {},
                "important_chunks_json": [],
                "summary_job_json": {},
                "parse_status": "summarizing",
                "parse_error": "",
            },
        )()
        calls: list[int] = []

        async def fake_summarize_once(db, model, assembled):
            if "PartA" in assembled["user_message"]:
                calls.append(1)
                await asyncio.sleep(0.05)
                return {
                    "brief_points": ["A"],
                    "operations": [],
                    "skills": [],
                    "violations": [],
                    "visual_points": [],
                    "constraints": [],
                    "terms": [],
                    "important_fragments": [],
                }
            calls.append(2)
            await asyncio.sleep(0.01)
            return {
                "brief_points": ["B"],
                "operations": [],
                "skills": [],
                "violations": [],
                "visual_points": [],
                "constraints": [],
                "terms": [],
                "important_fragments": [],
            }

        db = AsyncMock()
        db.flush = AsyncMock()
        parts = ["PartA " * 100, "PartB " * 100]

        with patch("app.services.generation._resolve_models", AsyncMock(return_value=(object(), None))), patch(
            "app.services.prompt_assembler.get_active_system_template",
            AsyncMock(return_value=None),
        ), patch("app.services.sources._split_for_summary", return_value=parts), patch(
            "app.services.sources._summarize_once", fake_summarize_once
        ):
            await summarize_source(db, source, uuid4())

        self.assertEqual(source.summary_short_json, ["A", "B"])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
