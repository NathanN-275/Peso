from __future__ import annotations

import unittest

from app.analysis.metrics_calculator import squat_depth_assessment


def point(x: float, y: float, visibility: float = 0.95) -> dict[str, float]:
  return {
    "x": x,
    "y": y,
    "z": 0.0,
    "visibility": visibility,
  }


class SquatDepthAssessmentTest(unittest.TestCase):
  def test_hip_clearly_below_knee_scores_high(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.72),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )

    self.assertGreaterEqual(assessment["score"], 0.85)
    self.assertGreaterEqual(assessment["confidence"], 0.8)

  def test_clear_depth_met_uses_hip_crease_and_knee_top(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.535),
      point(0.60, 0.58),
      point(0.58, 0.90),
      frame_height_px=720,
      selected_side="left",
      selected_side_score=0.95,
      alternate_side_score=0.50,
      side_clarity=0.47,
    )

    self.assertEqual(assessment["depth_classification"], "hit_depth")
    self.assertEqual(assessment["depth_reason"], "depth_met")
    self.assertGreaterEqual(assessment["estimated_hip_crease_y"], assessment["estimated_knee_top_y"])

  def test_screenshot_like_bottom_depth_hits_with_raw_hip_near_knee(self) -> None:
    assessment = squat_depth_assessment(
      point(0.36, 0.40),
      point(0.60, 0.57),
      point(0.34, 0.58),
      point(0.48, 0.78),
      frame_height_px=720,
      selected_side="left",
      selected_side_score=0.95,
      alternate_side_score=0.40,
      side_clarity=0.58,
    )

    self.assertLess(assessment["raw_hip_knee_delta"], 0.0)
    self.assertEqual(assessment["depth_classification"], "hit_depth")
    self.assertEqual(assessment["depth_reason"], "depth_met")
    self.assertGreaterEqual(
      assessment["estimated_hip_crease_y"],
      assessment["estimated_knee_top_y"] - assessment["depth_tolerance_normalized"],
    )

  def test_clear_insufficient_depth_requires_clear_gap(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.46),
      point(0.60, 0.58),
      point(0.58, 0.90),
      frame_height_px=720,
      selected_side="left",
      selected_side_score=0.95,
      alternate_side_score=0.50,
      side_clarity=0.47,
    )

    self.assertLess(assessment["score"], 0.45)
    self.assertEqual(assessment["depth_classification"], "insufficient_depth")
    self.assertEqual(assessment["depth_reason"], "hip_crease_above_knee_top")
    self.assertLess(assessment["depth_delta_px"], -assessment["depth_tolerance_px"])

  def test_borderline_depth_is_uncertain(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.48),
      point(0.60, 0.58),
      point(0.58, 0.90),
      frame_height_px=720,
      selected_side="left",
      selected_side_score=0.95,
      alternate_side_score=0.50,
      side_clarity=0.47,
    )

    self.assertEqual(assessment["depth_classification"], "uncertain_depth")
    self.assertEqual(assessment["depth_reason"], "borderline_depth")

  def test_hip_level_with_knee_scores_as_parallel(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.58),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )

    self.assertGreaterEqual(assessment["score"], 0.6)
    self.assertEqual(assessment["parallel_score"], 1.0)
    self.assertGreater(assessment["hip_knee_delta"], 0.0)

  def test_low_visibility_reduces_score_and_confidence(self) -> None:
    high_visibility = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.72),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )
    low_visibility = squat_depth_assessment(
      point(0.40, 0.20, 0.2),
      point(0.45, 0.72, 0.2),
      point(0.60, 0.58, 0.2),
      point(0.58, 0.90, 0.2),
    )

    self.assertLess(low_visibility["score"], high_visibility["score"])
    self.assertLess(low_visibility["confidence"], high_visibility["confidence"])
    self.assertEqual(low_visibility["depth_classification"], "uncertain_depth")
    self.assertEqual(low_visibility["depth_reason"], "low_landmark_confidence")

  def test_selected_side_unclear_is_uncertain(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.72),
      point(0.60, 0.58),
      point(0.58, 0.90),
      selected_side="left",
      selected_side_score=0.95,
      alternate_side_score=0.93,
      side_clarity=0.02,
    )

    self.assertEqual(assessment["depth_classification"], "uncertain_depth")
    self.assertEqual(assessment["depth_reason"], "selected_side_unclear")

  def test_joint_flexion_improves_score_when_depth_geometry_matches(self) -> None:
    flexed = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.72),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )
    less_flexed = squat_depth_assessment(
      point(-0.50, 0.86),
      point(0.10, 0.72),
      point(0.60, 0.58),
      point(0.95, 0.90),
    )

    self.assertGreater(flexed["knee_flexion_score"], less_flexed["knee_flexion_score"])
    self.assertGreater(flexed["hip_flexion_score"], less_flexed["hip_flexion_score"])
    self.assertGreater(flexed["score"], less_flexed["score"])


if __name__ == "__main__":
  unittest.main()
