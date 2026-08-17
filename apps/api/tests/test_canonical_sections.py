"""Canonical sections for profession_map / scenario_plan."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document import ensure_ids


class CanonicalSectionsTests(unittest.TestCase):
    def test_profession_map_fills_fixed_sections(self):
        doc = ensure_ids({"sections": [{"id": "work_type", "title": "Работы", "items": [{"title": "A"}]}]}, "profession_map")
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(
            ids[:5],
            [
                "work_variants",
                "evaluated_skills",
                "assessment_points",
                "preliminary_storylines",
                "expert_questions",
            ],
        )
        self.assertEqual(doc["sections"][0]["items"][0]["title"], "A")

    def test_scenario_plan_aliases_and_order(self):
        doc = ensure_ids(
            {
                "sections": [
                    {"id": "training_mode", "title": "Обучение", "items": [{"title": "T"}]},
                    {"id": "passport", "title": "Паспорт", "items": []},
                ]
            },
            "scenario_plan",
        )
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(ids[0], "scenario_passport")
        self.assertEqual(ids[1], "training_scenes")
        self.assertEqual(ids[2], "diagnostic_scenes")
        self.assertIn("microtexts", ids)
        self.assertIn("shooting_plan", ids)


if __name__ == "__main__":
    unittest.main()
