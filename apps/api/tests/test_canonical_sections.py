"""Canonical sections for profession_map / scenario_plan."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document import ensure_ids


class CanonicalSectionsTests(unittest.TestCase):
    def test_profession_map_fills_fixed_sections(self):
        doc = ensure_ids(
            {"sections": [{"id": "work_type", "title": "Работы", "items": [{"title": "A"}]}]},
            "profession_map",
        )
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(ids[:3], ["work_storylines", "assessment_points", "expert_questions"])
        self.assertEqual(doc["sections"][0]["items"][0]["title"], "A")

    def test_profession_map_merges_old_section_ids(self):
        doc = ensure_ids(
            {
                "sections": [
                    {"id": "work_variants", "title": "Работы", "items": [{"title": "W"}]},
                    {"id": "preliminary_storylines", "title": "Сюжет", "items": [{"title": "S"}]},
                    {"id": "evaluated_skills", "title": "Навыки", "items": [{"title": "Sk"}]},
                ]
            },
            "profession_map",
        )
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(ids, ["work_storylines", "assessment_points", "expert_questions"])
        work_titles = [it["title"] for it in doc["sections"][0]["items"]]
        self.assertEqual(work_titles, ["W", "S"])
        self.assertEqual(doc["sections"][1]["items"][0]["title"], "Sk")

    def test_scenario_plan_aliases_and_keeps_legacy_tail(self):
        doc = ensure_ids(
            {
                "sections": [
                    {"id": "training_mode", "title": "Обучение", "items": [{"title": "T"}]},
                    {"id": "passport", "title": "Паспорт", "items": [{"title": "P"}]},
                    {"id": "microtexts", "title": "Тексты", "items": []},
                    {"id": "shooting_plan", "title": "Съёмка", "items": []},
                ]
            },
            "scenario_plan",
        )
        ids = [s["id"] for s in doc["sections"]]
        self.assertEqual(ids[0], "training_scenes")
        self.assertEqual(ids[1], "diagnostic_scenes")
        self.assertIn("scenario_passport", ids)
        self.assertIn("microtexts", ids)
        self.assertIn("shooting_plan", ids)
        self.assertEqual(doc["sections"][0]["items"][0]["title"], "T")

    def test_scenario_frames_keep_shot_fields(self):
        doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "training_scenes",
                        "title": "Обучение",
                        "items": [
                            {
                                "title": "Выход из подъезда",
                                "frames": [{"shot_no": 1, "action": "Закрыть дверь", "accent": "Ручка"}],
                            }
                        ],
                    }
                ]
            },
            "scenario_plan",
        )
        frame = doc["sections"][0]["items"][0]["frames"][0]
        self.assertEqual(frame["action"], "Закрыть дверь")
        self.assertIn("id", frame)


    def test_assessment_points_errors_array(self):
        doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "assessment_points",
                        "title": "Навыки и точки оценки",
                        "items": [
                            {
                                "title": "Порядок действий",
                                "description": "Проверяется последовательность",
                                "errors": [
                                    {
                                        "error": "Пропуск шага",
                                        "correct": "Шаги по регламенту",
                                        "visual_cues": ["Видно в кадре"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "profession_map",
        )
        ap_section = next(s for s in doc["sections"] if s["id"] == "assessment_points")
        item = ap_section["items"][0]
        self.assertIn("errors", item)
        self.assertIsInstance(item["errors"], list)
        self.assertEqual(len(item["errors"]), 1)
        err = item["errors"][0]
        self.assertEqual(err["error"], "Пропуск шага")
        self.assertEqual(err["correct"], "Шаги по регламенту")
        self.assertNotIn("error_observation", item)
        self.assertNotIn("correct_observation", item)

    def test_diagnostic_frame_action_violation(self):
        doc = ensure_ids(
            {
                "sections": [
                    {
                        "id": "diagnostic_scenes",
                        "title": "Диагностика",
                        "items": [
                            {
                                "title": "Выход из подъезда",
                                "frames": [
                                    {"shot_no": 1, "action": "Работник выходит", "violation": "", "accent": "Общий план", "categories": []},
                                    {"shot_no": 2, "action": "Дверь оставлена открытой", "violation": "Дверь не закрыта", "accent": "Открытый проём", "categories": ["контроль доступа"]},
                                ],
                            }
                        ],
                    }
                ]
            },
            "scenario_plan",
        )
        diag_section = next(s for s in doc["sections"] if s["id"] == "diagnostic_scenes")
        frames = diag_section["items"][0]["frames"]
        self.assertEqual(frames[0]["action"], "Работник выходит")
        self.assertEqual(frames[0]["violation"], "")
        self.assertEqual(frames[1]["violation"], "Дверь не закрыта")


if __name__ == "__main__":
    unittest.main()
