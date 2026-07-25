from __future__ import annotations

import unittest

from app.analysis.exercises.front_squat import (
  FrontSquatAnalyzer,
  repair_front_pose_frames,
)


def landmark(x: float, y: float, visibility: float = 0.95) -> dict[str, float]:
  return {"x": x, "y": y, "z": 0.0, "visibility": visibility}


def frame(index: int, knee_shift: float = 0.0) -> dict:
  return {
    "source_frame_index": index,
    "timestamp_ms": index * 500,
    "landmarks": {
      "left_shoulder": landmark(0.42, 0.22),
      "right_shoulder": landmark(0.58, 0.22),
      "left_hip": landmark(0.44, 0.47 + (knee_shift * 0.65)),
      "right_hip": landmark(0.56, 0.47 + (knee_shift * 0.65)),
      "left_knee": landmark(0.44 + knee_shift, 0.68),
      "right_knee": landmark(0.56 - knee_shift, 0.68),
      "left_ankle": landmark(0.40, 0.91),
      "right_ankle": landmark(0.60, 0.91),
    },
  }


class FrontSquatAnalyzerTest(unittest.TestCase):
  def test_counts_front_squat_without_emitting_side_view_metrics(self) -> None:
    shifts = [0.0, 0.0, 0.05, 0.15, 0.08, 0.02, 0.0, 0.0]
    frames = [frame(index, shift) for index, shift in enumerate(shifts)]

    result = FrontSquatAnalyzer().analyze(
      video_id="video-1",
      exercise_type="front squat",
      view_type="front",
      frames=frames,
      sampled_frame_count=len(frames),
    )

    self.assertEqual(result["analysisMode"], "front_squat_tracking_v1")
    self.assertEqual(result["rep_count"], 1)
    self.assertFalse(result["analysisCapabilities"]["depthAssessment"])
    self.assertNotIn("depth_score", result["reps"][0])
    self.assertNotIn("torso_angle_change", result["reps"][0])
    self.assertEqual(len(result["poseFrames"]), len(frames))

  def test_rep_detection_can_use_one_reliable_leg(self) -> None:
    shifts = [0.0, 0.0, 0.05, 0.15, 0.08, 0.02, 0.0, 0.0]
    frames = [frame(index, shift) for index, shift in enumerate(shifts)]
    for current in frames:
      for joint in ("hip", "knee", "ankle"):
        current["landmarks"][f"right_{joint}"]["visibility"] = 0.1

    result = FrontSquatAnalyzer().analyze(
      video_id="video-1",
      exercise_type="squat",
      view_type="front",
      frames=frames,
      sampled_frame_count=len(frames),
    )

    self.assertEqual(result["rep_count"], 1)
    self.assertIn("lower_body_occluded", result["diagnostics"]["quality_flags"])

  def test_counts_fast_shallow_rep_before_deeper_rep(self) -> None:
    shifts = [0.0] * 50
    for index, shift in enumerate(
      [0.0, 0.024, 0.072, 0.12, 0.072, 0.024, 0.0],
      start=3,
    ):
      shifts[index] = shift
    for index, shift in enumerate(
      [0.0, 0.03, 0.08, 0.15, 0.18, 0.15, 0.08, 0.03, 0.0],
      start=34,
    ):
      shifts[index] = shift
    frames = [frame(index, shift) for index, shift in enumerate(shifts)]
    for index, current in enumerate(frames):
      current["timestamp_ms"] = index * 100

    result = FrontSquatAnalyzer().analyze(
      video_id="video-1",
      exercise_type="squat",
      view_type="front",
      frames=frames,
      sampled_frame_count=len(frames),
    )

    self.assertEqual(result["rep_count"], 2)
    self.assertEqual(
      [round(rep["bottomTime"], 1) for rep in result["reps"]],
      [0.5, 3.8],
    )

  def test_repairs_only_short_interior_gaps(self) -> None:
    frames = [frame(index) for index in range(8)]
    for index in range(1, 4):
      frames[index]["landmarks"]["left_knee"]["visibility"] = 0.05
    for index in range(4, 8):
      frames[index]["landmarks"]["right_ankle"]["visibility"] = 0.05

    repaired, diagnostics = repair_front_pose_frames(frames)

    for index in range(1, 4):
      self.assertEqual(
        repaired[index]["landmarks"]["left_knee"]["tracking_state"],
        "estimated",
      )
    self.assertEqual(diagnostics["estimated_counts"]["left_knee"], 3)
    self.assertEqual(diagnostics["estimated_counts"]["right_ankle"], 0)
    self.assertEqual(
      repaired[4]["landmarks"]["right_ankle"]["tracking_state"],
      "uncertain",
    )
    self.assertEqual(
      repaired[4]["landmarks"]["right_ankle"]["accepted_source"],
      "gap",
    )

  def test_front_repair_does_not_treat_invented_hips_as_confident(self) -> None:
    frames = [frame(index) for index in range(7)]
    frames[3]["landmarks"]["left_hip"].update({
      "x": 0.50,
      "y": 0.30,
      "visibility": 0.99,
      "tracking_state": "estimated",
      "accepted_source": "kinematic_estimate",
    })

    repaired, diagnostics = repair_front_pose_frames(frames)
    repaired_hip = repaired[3]["landmarks"]["left_hip"]

    self.assertEqual(repaired_hip["accepted_source"], "front_short_gap_estimate")
    self.assertEqual(repaired_hip["tracking_state"], "estimated")
    self.assertLessEqual(repaired_hip["visibility"], 0.48)
    self.assertAlmostEqual(repaired_hip["x"], 0.44)
    self.assertAlmostEqual(repaired_hip["y"], 0.47)
    self.assertEqual(diagnostics["estimated_counts"]["left_hip"], 1)

  def test_front_repair_marks_long_uncertain_hip_runs_as_gaps(self) -> None:
    frames = [frame(index) for index in range(8)]
    for index in range(1, 6):
      frames[index]["landmarks"]["right_hip"].update({
        "visibility": 0.99,
        "tracking_state": "estimated",
        "accepted_source": "pose_repair_interpolated_constrained",
      })

    repaired, diagnostics = repair_front_pose_frames(frames)

    for index in range(1, 6):
      repaired_hip = repaired[index]["landmarks"]["right_hip"]
      self.assertEqual(repaired_hip["accepted_source"], "gap")
      self.assertEqual(repaired_hip["tracking_state"], "uncertain")
      self.assertEqual(repaired_hip["visibility"], 0.0)
      self.assertFalse(repaired_hip["chain_valid"])
    self.assertEqual(diagnostics["gap_counts"]["right_hip"], 5)

  def test_front_repair_removes_bilateral_side_swaps(self) -> None:
    frames = [frame(index) for index in range(7)]
    frames[3]["landmarks"]["left_hip"]["x"] = 0.57
    frames[3]["landmarks"]["right_hip"]["x"] = 0.43

    repaired, diagnostics = repair_front_pose_frames(frames)

    self.assertLess(
      repaired[3]["landmarks"]["left_hip"]["x"],
      repaired[3]["landmarks"]["right_hip"]["x"],
    )
    self.assertEqual(
      repaired[3]["landmarks"]["left_hip"]["tracking_state"],
      "estimated",
    )
    self.assertEqual(diagnostics["identity_switch_counts"]["hip"], 1)


if __name__ == "__main__":
  unittest.main()
