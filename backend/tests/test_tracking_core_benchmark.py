from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_tracking_core_benchmark.py"
SPEC = importlib.util.spec_from_file_location("tracking_benchmark", SCRIPT)
assert SPEC and SPEC.loader
BENCHMARK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCHMARK)


class TrackingCoreBenchmarkTest(unittest.TestCase):
  def test_nearest_point_allows_small_timestamp_rounding_difference(self) -> None:
    point = BENCHMARK._nearest_point(
      [{"time": 1.033, "x": 10, "y": 20}],
      time_seconds=1.0,
      tolerance_seconds=0.04,
    )
    self.assertIsNotNone(point)
    self.assertIsNone(BENCHMARK._nearest_point(
      [{"time": 1.05, "x": 10, "y": 20}],
      time_seconds=1.0,
      tolerance_seconds=0.04,
    ))

  def test_mode_specific_acceptance_thresholds(self) -> None:
    thresholds = {
      "minimum_active_rep_coverage": 0.90,
      "pin_assisted_collar_p95_px": 10,
      "pin_assisted_collar_max_px": 18,
      "automatic_collar_p95_px": 16,
      "automatic_collar_max_px": 26,
      "hardware_identity_switches": 0,
    }
    passing = BENCHMARK.evaluate_thresholds({
      "mode": "pin_assisted",
      "coverage": 0.95,
      "p95_px": 9,
      "max_px": 17,
      "hardware_identity_switches": 0,
    }, thresholds)
    failing = BENCHMARK.evaluate_thresholds({
      "mode": "automatic",
      "coverage": 0.89,
      "p95_px": 17,
      "max_px": 27,
      "hardware_identity_switches": 1,
    }, thresholds)

    self.assertTrue(passing["passed"])
    self.assertFalse(failing["passed"])
    self.assertEqual(len(failing["failures"]), 4)


if __name__ == "__main__":
  unittest.main()
