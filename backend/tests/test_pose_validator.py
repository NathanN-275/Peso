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
  source_frame_index: int | None = None,
  left_shoulder: dict[str, float] | None = None,
  left_hip: dict[str, float] | None = None,
  left_knee: dict[str, float] | None = None,
  left_ankle: dict[str, float] | None = None,
) -> dict[str, object]:
  return {
    "timestamp_ms": timestamp_ms,
    **({"source_frame_index": source_frame_index} if source_frame_index is not None else {}),
    "frame_width": 1000,
    "frame_height": 1000,
    "landmarks": {
      "left_shoulder": left_shoulder or landmark(0.42, 0.25),
      "left_hip": left_hip or landmark(0.46, 0.56),
      "left_knee": left_knee or landmark(0.56, 0.72),
      "left_ankle": left_ankle or landmark(0.54, 0.93),
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

  def test_chain_jumble_near_rack_is_estimated_instead_of_displayed(self) -> None:
    frames = [
      frame(0),
      frame(100),
      frame(
        200,
        left_shoulder=landmark(0.62, 0.34),
        left_hip=landmark(0.65, 0.58),
        left_knee=landmark(0.68, 0.71),
        left_ankle=landmark(0.54, 0.93),
      ),
      frame(300),
      frame(400),
    ]

    validated, report = validate_squat_pose_frames(frames)
    unreliable = {
      item["joint"]: item
      for item in report["unreliable_landmarks"]
      if item["frame_index"] == 2
    }

    for joint in ("shoulder", "hip", "knee"):
      self.assertIn(joint, unreliable)
      self.assertIn("chain_jumble", unreliable[joint]["reasons"])
      self.assertEqual(validated[2]["landmarks"][f"left_{joint}"]["tracking_state"], "estimated")
      self.assertLessEqual(validated[2]["landmarks"][f"left_{joint}"]["visibility"], 0.48)

  def test_multi_frame_direct_side_chain_jumble_is_rejected(self) -> None:
    frames = [
      frame(0),
      frame(100),
      frame(
        200,
        left_shoulder=landmark(0.64, 0.36),
        left_hip=landmark(0.66, 0.55),
        left_knee=landmark(0.68, 0.71),
      ),
      frame(
        300,
        left_shoulder=landmark(0.65, 0.37),
        left_hip=landmark(0.67, 0.56),
        left_knee=landmark(0.69, 0.72),
      ),
      frame(
        400,
        left_shoulder=landmark(0.64, 0.36),
        left_hip=landmark(0.66, 0.55),
        left_knee=landmark(0.68, 0.71),
      ),
      frame(500),
      frame(600),
    ]

    validated, report = validate_squat_pose_frames(frames)
    middle_unreliable = {
      item["joint"]: item
      for item in report["unreliable_landmarks"]
      if item["frame_index"] == 3
    }

    for joint in ("shoulder", "hip", "knee"):
      self.assertIn(joint, middle_unreliable)
      self.assertIn("direct_side_chain_jumble", middle_unreliable[joint]["reasons"])
      self.assertEqual(validated[3]["landmarks"][f"left_{joint}"]["tracking_state"], "estimated")
      self.assertLessEqual(validated[3]["landmarks"][f"left_{joint}"]["visibility"], 0.48)

  def test_high_confidence_plate_occluded_upper_back_and_hip_are_rejected(self) -> None:
    frames = [
      frame(0, source_frame_index=0),
      frame(
        100,
        source_frame_index=1,
        left_shoulder=landmark(0.50, 0.34, 0.99),
        left_hip=landmark(0.50, 0.43, 0.99),
      ),
      frame(200, source_frame_index=2),
    ]

    validated, report = validate_squat_pose_frames(
      frames,
      selected_side_override="left",
      barbell_occluders_by_frame={
        1: {"x": 0.50, "y": 0.38, "radius": 0.075},
      },
    )

    unreliable = {
      item["joint"]: item
      for item in report["unreliable_landmarks"]
      if item["frame_index"] == 1
    }
    self.assertIn("shoulder", unreliable)
    self.assertIn("hip", unreliable)
    self.assertIn("barbell_plate_occlusion", unreliable["shoulder"]["reasons"])
    self.assertIn("barbell_plate_occlusion", unreliable["hip"]["reasons"])
    self.assertEqual(validated[1]["landmarks"]["left_shoulder"]["tracking_state"], "estimated")
    self.assertEqual(validated[1]["landmarks"]["left_hip"]["tracking_state"], "estimated")
    self.assertLess(validated[1]["landmarks"]["left_shoulder"]["x"], 0.46)
    self.assertGreaterEqual(report["barbell_plate_occlusion_count"], 2)

  def test_automatic_plate_occlusion_without_recovery_becomes_visual_only(self) -> None:
    frames = [
      frame(
        0,
        source_frame_index=0,
        left_shoulder=landmark(0.50, 0.34, 0.99),
        left_hip=landmark(0.50, 0.43, 0.99),
      ),
    ]

    validated, report = validate_squat_pose_frames(
      frames,
      selected_side_override="left",
      barbell_occluders_by_frame={
        0: {"x": 0.50, "y": 0.38, "radius": 0.075},
      },
    )

    for joint in ("shoulder", "hip"):
      point = validated[0]["landmarks"][f"left_{joint}"]
      self.assertEqual(point["tracking_state"], "estimated")
      self.assertEqual(point["accepted_source"], "gap")
      self.assertFalse(point["chain_valid"])
      self.assertTrue(point["visual_only"])
      self.assertEqual(point["chain_failure_reason"], "barbell_plate_occlusion")

    self.assertEqual(report["visual_only_landmark_count"], 2)
    self.assertEqual(report["kinematic_estimated_landmark_count"], 0)

  def test_automatic_occluded_upper_back_recovers_from_trusted_hip(self) -> None:
    frames = [
      frame(0, source_frame_index=0),
      frame(
        100,
        source_frame_index=1,
        left_shoulder=landmark(0.50, 0.34, 0.99),
        left_hip=landmark(0.46, 0.56, 0.95),
      ),
    ]

    validated, report = validate_squat_pose_frames(
      frames,
      selected_side_override="left",
      barbell_occluders_by_frame={
        1: {"x": 0.50, "y": 0.34, "radius": 0.04},
      },
    )

    shoulder = validated[1]["landmarks"]["left_shoulder"]
    self.assertEqual(shoulder["tracking_state"], "estimated")
    self.assertEqual(shoulder["accepted_source"], "kinematic_estimate")
    self.assertTrue(shoulder["chain_valid"])
    self.assertFalse(shoulder["visual_only"])
    self.assertLess(shoulder["x"], 0.49)
    self.assertGreaterEqual(report["kinematic_estimated_landmark_count"], 1)


if __name__ == "__main__":
  unittest.main()
