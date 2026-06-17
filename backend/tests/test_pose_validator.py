from __future__ import annotations

import unittest

from app.analysis.pose_validator import validate_squat_pose_frames


def landmark(x: float, y: float, visibility: float = 0.95) -> dict[str, float]:
  return {
    "x": x,
    "y": y,
    "z": 0.0,
    "visibility": visibility,
  }


def frame(
  timestamp_ms: int,
  *,
  left_shoulder: dict[str, float] | None = None,
  left_hip: dict[str, float] | None = None,
) -> dict[str, object]:
  return {
    "timestamp_ms": timestamp_ms,
    "landmarks": {
      "left_shoulder": left_shoulder or landmark(0.42, 0.25),
      "left_hip": left_hip or landmark(0.46, 0.56),
      "left_knee": landmark(0.56, 0.72),
      "left_ankle": landmark(0.54, 0.93),
      "right_shoulder": landmark(0.50, 0.25, 0.4),
      "right_hip": landmark(0.54, 0.56, 0.4),
      "right_knee": landmark(0.64, 0.72, 0.4),
      "right_ankle": landmark(0.62, 0.93, 0.4),
    },
  }


class PoseValidatorTest(unittest.TestCase):
  def test_temporal_outlier_is_interpolated_and_reported(self) -> None:
    frames = [
      frame(0),
      frame(100),
      frame(200, left_hip=landmark(0.18, 0.18)),
      frame(300),
      frame(400),
    ]

    validated, report = validate_squat_pose_frames(frames)
    corrected_hip = validated[2]["landmarks"]["left_hip"]

    self.assertEqual(report["corrected_landmark_count"], 1)
    self.assertEqual(report["interpolated_landmark_count"], 1)
    self.assertEqual(report["rejected_landmark_count"], 0)
    self.assertAlmostEqual(corrected_hip["x"], 0.46)
    self.assertAlmostEqual(corrected_hip["y"], 0.56)
    self.assertEqual(corrected_hip["visibility"], 0.48)
    self.assertEqual(report["unreliable_landmarks"][0]["joint"], "hip")

  def test_low_visibility_without_neighbors_is_rejected(self) -> None:
    frames = [
      frame(0, left_hip=landmark(0.46, 0.56, 0.1)),
    ]

    validated, report = validate_squat_pose_frames(frames)

    self.assertEqual(report["corrected_landmark_count"], 0)
    self.assertEqual(report["rejected_landmark_count"], 1)
    self.assertEqual(validated[0]["landmarks"]["left_hip"]["visibility"], 0.1)
    self.assertEqual(report["unreliable_landmarks"][0]["status"], "rejected")

  def test_noisy_hip_is_smoothed_with_confidence_cap(self) -> None:
    frames = [
      frame(0, left_hip=landmark(0.46, 0.56)),
      frame(100, left_hip=landmark(0.49, 0.59)),
      frame(200, left_hip=landmark(0.46, 0.56)),
    ]

    validated, report = validate_squat_pose_frames(frames)
    smoothed_hip = validated[1]["landmarks"]["left_hip"]

    self.assertGreaterEqual(report["smoothed_landmark_count"], 1)
    self.assertLess(smoothed_hip["x"], 0.49)
    self.assertLessEqual(smoothed_hip["visibility"], 0.72)

  def test_hip_jump_with_stable_knee_ankle_is_corrected(self) -> None:
    frames = [
      frame(0, left_hip=landmark(0.46, 0.56)),
      frame(100, left_hip=landmark(0.64, 0.36)),
      frame(200, left_hip=landmark(0.47, 0.57)),
      frame(300, left_hip=landmark(0.46, 0.56)),
    ]

    validated, report = validate_squat_pose_frames(frames)
    corrected_hip = validated[1]["landmarks"]["left_hip"]

    self.assertGreaterEqual(
      report["corrected_landmark_count"] + report["smoothed_landmark_count"],
      1,
    )
    self.assertLess(corrected_hip["x"], 0.56)
    self.assertGreater(corrected_hip["y"], 0.48)
    self.assertLessEqual(corrected_hip["visibility"], 0.48)

  def test_selected_side_is_locked_for_validation_report(self) -> None:
    frames = [
      frame(0),
      frame(100),
      frame(200),
    ]

    _validated, report = validate_squat_pose_frames(frames)

    self.assertEqual(report["selected_side"], "left")
    self.assertIn("tracking_side_confidence", report)

  def test_pin_selected_side_overrides_automatic_side_selection(self) -> None:
    frames = [frame(0), frame(100), frame(200)]

    _validated, report = validate_squat_pose_frames(
      frames,
      selected_side_override="right",
    )

    self.assertEqual(report["selected_side"], "right")
    self.assertTrue(report["selected_side_overridden"])

  def test_automatic_upper_back_jump_is_interpolated(self) -> None:
    frames = [
      frame(0),
      frame(100, left_shoulder=landmark(0.67, 0.48)),
      frame(200),
    ]

    validated, report = validate_squat_pose_frames(frames)
    corrected = validated[1]["landmarks"]["left_shoulder"]

    self.assertEqual(corrected["tracking_state"], "estimated")
    self.assertLess(corrected["x"], 0.50)
    self.assertLess(corrected["y"], 0.34)
    self.assertIn("upper_back_relative_jump", report["unreliable_landmarks"][0]["reasons"])
    self.assertEqual(report["upper_back_proxy_semantics"], "displayed_as_upper_back")


if __name__ == "__main__":
  unittest.main()
