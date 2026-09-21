from __future__ import annotations

import unittest

from scripts.benchmark_img0013_release import (
  _pose_fixture_comparison,
  _pose_frames_for_tracker,
  _required_label_gate,
)


def pose_frame(index: int, timestamp_ms: int, right_x: float, left_x: float) -> dict:
  landmarks = {}
  for joint in ("shoulder", "wrist", "hip", "knee", "ankle"):
    landmarks[f"right_{joint}"] = {"x": right_x, "y": 0.5, "visibility": 0.9}
    landmarks[f"left_{joint}"] = {"x": left_x, "y": 0.5, "visibility": 0.9}
  return {
    "source_frame_index": index,
    "timestamp_ms": timestamp_ms,
    "landmarks": landmarks,
  }


class Img0013ReleaseBenchmarkTest(unittest.TestCase):
  def test_label_gate_uses_the_selected_fixture_label_count(self) -> None:
    tracking = {
      "barbellPath": {
        "available": True,
        "points": [{"time": 1.0, "x": 0.5, "y": 0.5}],
      },
      "diagnostics": {"max_point_gap_seconds": 0.0},
    }
    fixture = {
      "fps": 10.0,
      "coordinate_space": {"width": 100, "height": 100},
      "tolerance_px": 2.0,
      "labels": [
        {
          "source_frame_index": 10,
          "target": [50, 50],
          "allowed_missing": False,
        },
      ],
    }

    result = _required_label_gate(
      tracking,
      fixture,
      processed_width=100,
      processed_height=100,
    )

    self.assertTrue(result["passed"])
    self.assertEqual(result["required_label_count"], 1)
    self.assertEqual(result["required_label_hits"], 1)

  def test_fixture_landmarks_can_be_replayed_on_fresh_schedule(self) -> None:
    fresh = [pose_frame(0, 0, 0.2, 0.8), pose_frame(4, 67, 0.25, 0.75)]
    fixture = [pose_frame(0, 0, 0.3, 0.7), pose_frame(3, 50, 0.35, 0.65)]

    result = _pose_frames_for_tracker(fresh, fixture, "fixture_on_fresh_schedule")

    self.assertEqual([frame["source_frame_index"] for frame in result], [0, 4])
    self.assertEqual([frame["timestamp_ms"] for frame in result], [0, 67])
    self.assertEqual(result[1]["landmarks"]["right_shoulder"]["x"], 0.35)

  def test_selected_wrist_can_be_hidden_without_mutating_fresh_pose(self) -> None:
    fresh = [pose_frame(0, 0, 0.2, 0.8)]

    result = _pose_frames_for_tracker(
      fresh,
      [],
      "fresh_selected_wrist_hidden",
      selected_side="right",
    )

    self.assertEqual(result[0]["landmarks"]["right_wrist"]["visibility"], 0.0)
    self.assertEqual(fresh[0]["landmarks"]["right_wrist"]["visibility"], 0.9)

  def test_fresh_pose_sides_can_be_swapped_without_mutating_source(self) -> None:
    fresh = [pose_frame(0, 0, 0.2, 0.8)]

    result = _pose_frames_for_tracker(fresh, [], "fresh_sides_swapped")

    self.assertEqual(result[0]["landmarks"]["right_shoulder"]["x"], 0.8)
    self.assertEqual(result[0]["landmarks"]["left_shoulder"]["x"], 0.2)
    self.assertEqual(fresh[0]["landmarks"]["right_shoulder"]["x"], 0.2)

  def test_comparison_separates_schedule_coordinates_coverage_and_identity(self) -> None:
    fresh = [pose_frame(0, 0, 0.3, 0.7), pose_frame(4, 67, 0.35, 0.65)]
    fixture_frames = [pose_frame(0, 0, 0.3, 0.7), pose_frame(3, 50, 0.35, 0.65)]
    estimation = {
      "processed_frame_width": 405,
      "processed_frame_height": 720,
      "frames": fresh,
    }
    fixture = {
      "fps": 60.0,
      "selected_side": "right",
      "coordinate_space": {"width": 405, "height": 720},
      "pose_frames": fixture_frames,
    }

    result = _pose_fixture_comparison(estimation, fixture)

    self.assertTrue(result["coordinate_space_match"])
    self.assertEqual(result["common_source_index_count"], 1)
    self.assertEqual(result["max_nearest_source_index_distance"], 1)
    self.assertEqual(result["fresh_selected_joint_coverage"]["shoulder"], 1.0)
    self.assertEqual(result["swapped_side_closer_ratio"], 0.0)


if __name__ == "__main__":
  unittest.main()
