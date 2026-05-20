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

  def test_hip_above_knee_scores_low(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.50),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )

    self.assertLess(assessment["score"], 0.45)
    self.assertEqual(assessment["hip_vs_knee_score"], 0.0)

  def test_hip_level_with_knee_scores_as_parallel(self) -> None:
    assessment = squat_depth_assessment(
      point(0.40, 0.20),
      point(0.45, 0.58),
      point(0.60, 0.58),
      point(0.58, 0.90),
    )

    self.assertGreaterEqual(assessment["score"], 0.6)
    self.assertEqual(assessment["parallel_score"], 1.0)
    self.assertEqual(assessment["hip_knee_delta"], 0.0)

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
