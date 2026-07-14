from __future__ import annotations

import unittest

from app.analysis.exercises.pressing import PressingAnalyzer


def landmark(x: float, y: float, visibility: float = 0.9) -> dict[str, float]:
  return {"x": x, "y": y, "z": 0.0, "visibility": visibility}


def frame(index: int, wrist_y: float, *, visibility: float = 0.9, asymmetry: float = 0.0) -> dict:
  return {
    "source_frame_index": index,
    "timestamp_ms": index * 100,
    "landmarks": {
      "left_shoulder": landmark(0.42, 0.34, visibility),
      "right_shoulder": landmark(0.58, 0.34, visibility),
      "left_elbow": landmark(0.40, (0.34 + wrist_y) / 2, visibility),
      "right_elbow": landmark(0.60, (0.34 + wrist_y + asymmetry) / 2, visibility),
      "left_wrist": landmark(0.44, wrist_y, visibility),
      "right_wrist": landmark(0.56, wrist_y + asymmetry, visibility),
      "left_hip": landmark(0.44, 0.68, visibility),
      "right_hip": landmark(0.56, 0.68, visibility),
    },
  }


class PressingAnalyzerTest(unittest.TestCase):
  def test_counts_press_reps_from_barbell_path(self) -> None:
    frames = [frame(index, wrist_y) for index, wrist_y in enumerate([0.34, 0.56, 0.33, 0.55, 0.32])]
    barbell_path = {
      "available": True,
      "points": [
        {"time": index * 0.1, "x": 0.5, "y": y, "confidence": 0.9}
        for index, y in enumerate([0.34, 0.58, 0.33, 0.57, 0.32])
      ],
    }

    result = PressingAnalyzer().analyze(
      video_id="video-1",
      exercise_type="bench press",
      view_type="side",
      frames=frames,
      sampled_frame_count=len(frames),
      barbell_path=barbell_path,
    )

    self.assertEqual(result["rep_count"], 2)
    self.assertTrue(result["diagnostics"]["pressing_analysis"]["barbell_path_used"])
    self.assertGreater(result["reps"][0]["bar_travel"], 0.1)

  def test_counts_press_reps_from_wrist_fallback(self) -> None:
    frames = [frame(index, wrist_y) for index, wrist_y in enumerate([0.34, 0.56, 0.33, 0.55, 0.32])]

    result = PressingAnalyzer().analyze(
      video_id="video-1",
      exercise_type="overhead press",
      view_type="front",
      frames=frames,
      sampled_frame_count=len(frames),
    )

    self.assertEqual(result["rep_count"], 2)
    self.assertFalse(result["diagnostics"]["pressing_analysis"]["barbell_path_used"])

  def test_low_confidence_suppresses_form_warnings(self) -> None:
    frames = [
      frame(index, wrist_y, visibility=0.3, asymmetry=0.08)
      for index, wrist_y in enumerate([0.34, 0.56, 0.33])
    ]

    result = PressingAnalyzer().analyze(
      video_id="video-1",
      exercise_type="bench press",
      view_type="front",
      frames=frames,
      sampled_frame_count=len(frames),
    )

    self.assertEqual(result["rep_count"], 1)
    self.assertIn("low_tracking_confidence", result["reps"][0]["flags"])
    self.assertNotIn("front_view_asymmetry", result["reps"][0]["flags"])

  def test_selected_side_uses_the_pin_guided_arm_for_elbow_metrics(self) -> None:
    frames = [frame(index, wrist_y) for index, wrist_y in enumerate([0.34, 0.56, 0.33])]
    for current in frames:
      current["landmarks"]["right_elbow"] = landmark(0.58, 0.45, 0.9)
      current["landmarks"]["right_wrist"] = landmark(0.68, 0.45, 0.9)

    result = PressingAnalyzer().analyze(
      video_id="video-1",
      exercise_type="bench press",
      view_type="side",
      frames=frames,
      sampled_frame_count=len(frames),
      selected_side="right",
    )

    self.assertEqual(result["diagnostics"]["pressing_analysis"]["selected_side"], "right")
    self.assertAlmostEqual(result["reps"][0]["top_elbow_angle"], 90.0, places=1)


if __name__ == "__main__":
  unittest.main()
