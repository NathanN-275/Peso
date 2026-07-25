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
    self.assertNotIn("tracking_state", repaired[4]["landmarks"]["right_ankle"])


if __name__ == "__main__":
  unittest.main()
