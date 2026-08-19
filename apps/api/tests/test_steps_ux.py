"""Unlock/outdated helpers and scenario generate context (no sources)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import later_pipeline_steps, previous_step_allows_generate
from app.services.document import extract_expert_qa


class LaterStepsTests(unittest.TestCase):
    def test_brief_outdates_map_and_scenario(self):
        self.assertEqual(
            later_pipeline_steps("brief"),
            ["profession_map", "scenario_plan", "export"],
        )

    def test_map_outdates_scenario(self):
        self.assertEqual(later_pipeline_steps("profession_map"), ["scenario_plan", "export"])

    def test_unknown_is_empty(self):
        self.assertEqual(later_pipeline_steps("nope"), [])


class PipelineGateTests(unittest.TestCase):
    def test_brief_always_allows(self):
        self.assertTrue(previous_step_allows_generate("brief", False))

    def test_map_needs_artifact_not_approval(self):
        self.assertFalse(previous_step_allows_generate("profession_map", False))
        self.assertTrue(previous_step_allows_generate("profession_map", True))


class ExpertQaTests(unittest.TestCase):
    def test_empty_answer_is_explicit(self):
        items = extract_expert_qa(
            {
                "sections": [
                    {
                        "id": "expert_questions",
                        "items": [
                            {
                                "title": "Норматив?",
                                "description": "Какой допуск",
                                "why_needed": "для диагностики",
                                "answer": "",
                            },
                            {
                                "title": "СИЗ?",
                                "description": "",
                                "why_needed": "",
                                "answer": "Каска обязательна",
                            },
                        ],
                    }
                ]
            }
        )
        self.assertEqual(items[0]["answer"], "ответа нет")
        self.assertEqual(items[1]["answer"], "Каска обязательна")


if __name__ == "__main__":
    unittest.main()
