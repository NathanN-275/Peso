from __future__ import annotations

import unittest

from app.analysis.pose_repair import PoseRepairConfig, repair_selected_side_pose


def landmark(x: float, y: float, visibility: float = 0.95) -> dict[str, float]:
  return {"x": x, "y": y, "z": 0.0, "visibility": visibility}


def frame(
  timestamp_ms: int,
  *,
  hip: dict[str, float] | None = None,
  knee: dict[str, float] | None = None,
  ankle: dict[str, float] | None = None,
) -> dict[str, object]:
  return {
    "timestamp_ms": timestamp_ms,
    "source_frame_index": timestamp_ms // 50,
    "landmarks": {
      "left_shoulder": landmark(0.40, 0.25),
      "left_hip": hip or landmark(0.45, 0.55),
      "left_knee": knee or landmark(0.52, 0.72),
      "left_ankle": ankle or landmark(0.50, 0.92),
      "left_heel": landmark(0.48, 0.94),
      "left_foot_index": landmark(0.55, 0.95),
      "right_shoulder": landmark(0.45, 0.25, 0.35),
      "right_hip": landmark(0.50, 0.55, 0.35),
      "right_knee": landmark(0.57, 0.72, 0.35),
      "right_ankle": landmark(0.55, 0.92, 0.35),
    },
  }


class PoseRepairTest(unittest.TestCase):
  def setUp(self) -> None:
    self.config = PoseRepairConfig(enabled=True, max_gap_frames=3, velocity_gap_frames=2)

  def test_short_occlusion_is_interpolated_and_reported(self) -> None:
    frames = [
      frame(0),
      frame(50, knee=landmark(0.80, 0.20, 0.05)),
      frame(100),
    ]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=self.config,
    )

    knee = repaired[1]["landmarks"]["left_knee"]
    self.assertEqual(knee["accepted_source"], "pose_repair_interpolated")
    self.assertEqual(knee["tracking_state"], "estimated")
    self.assertAlmostEqual(knee["x"], 0.52)
    self.assertGreaterEqual(diagnostics["interpolated_landmark_count"], 1)
    self.assertGreaterEqual(diagnostics["repaired_frame_count"], 1)

  def test_long_occlusion_remains_a_low_confidence_gap(self) -> None:
    frames = [frame(0)] + [
      frame(index * 50, hip=landmark(0.80, 0.20, 0.05))
      for index in range(1, 5)
    ] + [frame(250)]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=self.config,
    )

    for index in range(1, 5):
      hip = repaired[index]["landmarks"]["left_hip"]
      self.assertEqual(hip["accepted_source"], "gap")
      self.assertTrue(hip["visual_only"])
      self.assertLessEqual(hip["visibility"], 0.2)
    self.assertGreaterEqual(diagnostics["gap_count"], 4)

  def test_short_ankle_gap_uses_recent_velocity_without_future_frame(self) -> None:
    frames = [
      frame(0, ankle=landmark(0.48, 0.92)),
      frame(50, ankle=landmark(0.50, 0.92)),
      frame(100, ankle=landmark(0.90, 0.20, 0.05)),
    ]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=self.config,
    )

    ankle = repaired[2]["landmarks"]["left_ankle"]
    self.assertIn("pose_repair_velocity", ankle["accepted_source"])
    self.assertLess(ankle["x"], 0.60)
    self.assertGreaterEqual(diagnostics["velocity_estimated_landmark_count"], 1)

  def test_implausible_jump_is_rejected_by_quality_and_repair(self) -> None:
    frames = [
      frame(0),
      frame(50, knee=landmark(0.85, 0.20)),
      frame(100),
    ]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=self.config,
    )

    knee = repaired[1]["landmarks"]["left_knee"]
    self.assertEqual(knee["tracking_state"], "estimated")
    self.assertLess(knee["x"], 0.60)
    self.assertIn("knee_temporal_jump", diagnostics["frame_quality"][1]["reasons"])

  def test_clean_pose_stays_observed(self) -> None:
    frames = [frame(0), frame(50), frame(100)]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=self.config,
    )

    self.assertAlmostEqual(repaired[1]["landmarks"]["left_hip"]["x"], 0.45)
    self.assertEqual(diagnostics["gap_count"], 0)
    self.assertEqual(diagnostics["velocity_estimated_landmark_count"], 0)
    self.assertGreater(diagnostics["average_quality"], 0.85)
    self.assertEqual(diagnostics["raw_repair_debug"], [])

  def test_disabled_repair_preserves_raw_frames(self) -> None:
    frames = [frame(0), frame(50, knee=landmark(0.80, 0.20, 0.05)), frame(100)]

    repaired, diagnostics = repair_selected_side_pose(
      frames,
      selected_side_override="left",
      config=PoseRepairConfig(enabled=False),
    )

    self.assertAlmostEqual(repaired[1]["landmarks"]["left_knee"]["x"], 0.80)
    self.assertFalse(diagnostics["enabled"])


if __name__ == "__main__":
  unittest.main()
