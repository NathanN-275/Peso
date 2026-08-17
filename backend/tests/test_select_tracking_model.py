from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "select_tracking_model.py"
SPEC = importlib.util.spec_from_file_location("tracking_model_selection", SCRIPT)
assert SPEC and SPEC.loader
SELECTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SELECTION)

THRESHOLDS = {
  "maximum_latency_ratio": 1.10,
  "minimum_active_rep_coverage": 0.90,
  "pin_assisted_collar_p95_px": 10,
  "pin_assisted_collar_max_px": 18,
  "automatic_collar_p95_px": 16,
  "automatic_collar_max_px": 26,
  "hardware_identity_switches": 0,
}


def candidate(variant: str, *, latency: float, auto_p95: float = 15) -> dict[str, object]:
  return {
    "variant": variant,
    "artifact": f"{variant}.onnx",
    "baseline_latency_ms": 100,
    "latency_ms": latency,
    "tracking": {
      "pin_assisted": {"coverage": 0.95, "p95_px": 9, "max_px": 17, "hardware_identity_switches": 0},
      "automatic": {"coverage": 0.94, "p95_px": auto_p95, "max_px": 24, "hardware_identity_switches": 0},
    },
  }


class SelectTrackingModelTest(unittest.TestCase):
  def test_selects_nano_when_both_models_pass(self) -> None:
    result = SELECTION.select_tracking_model({
      "candidates": [candidate("yolo11s", latency=109), candidate("yolo11n", latency=104)]
    }, THRESHOLDS)

    self.assertEqual(result["selected_variant"], "yolo11n")
    self.assertEqual(result["status"], "promotion_ready")

  def test_selects_small_model_only_when_it_passes_latency_and_accuracy(self) -> None:
    result = SELECTION.select_tracking_model({
      "candidates": [candidate("yolo11n", latency=112), candidate("yolo11s", latency=108)]
    }, THRESHOLDS)

    self.assertEqual(result["selected_variant"], "yolo11s")
    self.assertFalse(result["candidates"][0]["acceptance"]["passed"])

  def test_rejects_all_models_when_tracking_identity_gate_fails(self) -> None:
    result = SELECTION.select_tracking_model({
      "candidates": [candidate("yolo11n", latency=100, auto_p95=17)]
    }, THRESHOLDS)

    self.assertIsNone(result["selected_variant"])
    self.assertEqual(result["status"], "no_candidate_passed")


if __name__ == "__main__":
  unittest.main()
