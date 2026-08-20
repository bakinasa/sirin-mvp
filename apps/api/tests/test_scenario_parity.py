"""Scenario parity validation and context rendering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document import ensure_ids, validate_scenario_parity
from app.services.token_budget import compute_max_tokens, should_truncate_block


class ScenarioParityTests(unittest.TestCase):
    def test_validate_scenario_parity_detects_missing_work_type(self):
        map_doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "work_storylines",
                        "title": "Работы",
                        "items": [
                            {"title": "A"},
                            {"title": "B"},
                            {"title": "C"},
                            {"title": "D"},
                        ],
                    }
                ]
            },
            "profession_map",
        )
        scenario_doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "training_scenes",
                        "title": "Обучение",
                        "items": [{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    },
                    {
                        "id": "diagnostic_scenes",
                        "title": "Диагностика",
                        "items": [{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    },
                ]
            },
            "scenario_plan",
        )
        warnings = validate_scenario_parity(map_doc, scenario_doc)
        self.assertTrue(any("D" in w for w in warnings))
        self.assertTrue(any("4" in w or "видов работ" in w for w in warnings))

    def test_validate_scenario_parity_ok_when_counts_match(self):
        map_doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "work_storylines",
                        "items": [{"title": "A"}, {"title": "B"}],
                    }
                ]
            },
            "profession_map",
        )
        scenario_doc = ensure_ids(
            {
                "sections": [
                    {"id": "training_scenes", "items": [{"title": "A"}, {"title": "B"}]},
                    {"id": "diagnostic_scenes", "items": [{"title": "A"}, {"title": "B"}]},
                ]
            },
            "scenario_plan",
        )
        self.assertEqual(validate_scenario_parity(map_doc, scenario_doc), [])

    def test_profession_map_block_not_truncated_by_policy(self):
        self.assertFalse(should_truncate_block("profession_map"))
        self.assertFalse(should_truncate_block("expert_qa"))
        map_content = ensure_ids(
            {
                "sections": [
                    {
                        "id": "work_storylines",
                        "items": [{"title": "Work 3", "description": "d" * 200}],
                    }
                ]
            },
            "profession_map",
        )
        self.assertEqual(map_content["sections"][0]["items"][0]["title"], "Work 3")

    def test_compute_max_tokens_uses_remaining_context(self):
        model = type("M", (), {"provider_name": "OpenRouter", "base_url": "", "context_window": 128000})()
        tokens = compute_max_tokens(model, "system" * 100, "user" * 100)
        # Above old hard 8192, but soft-capped so providers do not hang.
        self.assertGreater(tokens, 8192)
        self.assertLessEqual(tokens, 32768)

    def test_skills_alias_normalized_to_assessment_points(self):
        doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "skills",
                        "title": "Навыки",
                        "items": [
                            {
                                "title": "Порядок",
                                "errors": [{"error": "e", "correct": "c", "visual_cues": []}],
                            }
                        ],
                    }
                ]
            },
            "profession_map",
        )
        ids = [s["id"] for s in doc["sections"]]
        self.assertIn("assessment_points", ids)
        self.assertNotIn("skills", ids)

    def test_should_not_truncate_pipeline_blocks(self):
        self.assertFalse(should_truncate_block("profession_map"))
        self.assertFalse(should_truncate_block("expert_qa"))
        self.assertTrue(should_truncate_block("source_summaries"))


if __name__ == "__main__":
    unittest.main()
