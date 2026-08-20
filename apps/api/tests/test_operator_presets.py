"""Factory operator-prompt catalog."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.operator_preset_defaults import OPERATOR_PRESETS, factory_operator_preset


class OperatorPresetDefaultsTests(unittest.TestCase):
    def test_factory_known_steps(self):
        for step in ("profession_map", "scenario_plan", "draft_tz"):
            preset = factory_operator_preset(step)
            self.assertIsNotNone(preset)
            self.assertTrue(preset["is_default"])
            self.assertTrue(str(preset["content"]).strip())

    def test_factory_unknown_step(self):
        self.assertIsNone(factory_operator_preset("not_a_step"))

    def test_unique_step_types(self):
        ids = [p["step_type"] for p in OPERATOR_PRESETS]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
