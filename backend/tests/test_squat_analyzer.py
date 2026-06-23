from __future__ import annotations

import unittest
from unittest.mock import patch

from app.analysis.exercises.squat import SquatAnalyzer, _build_pose_frames


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
  left_visibility: float = 0.95,
  right_visibility: float = 0.70,
  left_hip_y: float = 0.48,
  left_knee_y: float = 0.68,
  left_ankle_y: float = 0.92,
  right_hip_y: float = 0.48,
  right_knee_y: float = 0.68,
  right_ankle_y: float = 0.92,
  shoulder_gap: float = 0.04,
  left_shoulder_y: float = 0.20,
  left_shoulder_x: float = 0.40,
) -> dict[str, object]:
  return {
    "timestamp_ms": timestamp_ms,
    "landmarks": {
      "left_shoulder": landmark(left_shoulder_x, left_shoulder_y, left_visibility),
      "left_hip": landmark(0.45, left_hip_y, left_visibility),
      "left_knee": landmark(0.60, left_knee_y, left_visibility),
      "left_ankle": landmark(0.58, left_ankle_y, left_visibility),
      "right_shoulder": landmark(0.40 + shoulder_gap, 0.20, right_visibility),
      "right_hip": landmark(0.45 + shoulder_gap, right_hip_y, right_visibility),
      "right_knee": landmark(0.60 + shoulder_gap, right_knee_y, right_visibility),
      "right_ankle": landmark(0.58 + shoulder_gap, right_ankle_y, right_visibility),
    },
  }


class SquatAnalyzerTest(unittest.TestCase):
  def test_public_pose_frames_do_not_emit_pin_metadata_for_automatic_points(self) -> None:
    pose_frames = _build_pose_frames([frame(0)])

    left_knee = next(
      keypoint
      for keypoint in pose_frames[0]["keypoints"]
      if keypoint["name"] == "left_knee"
    )

    self.assertNotIn("manualSource", left_knee)
    self.assertNotIn("userPinned", left_knee)
    self.assertNotIn("acceptedSource", left_knee)
    self.assertNotIn("visualFallback", left_knee)

  def test_public_pose_frames_emit_visual_fallback_without_replacing_accepted_point(self) -> None:
    source_frame = frame(0)
    left_knee = source_frame["landmarks"]["left_knee"]
    left_knee["accepted_source"] = "automatic"
    left_knee["visual_fallback"] = {
      "manual_source": "pin_visual_fallback",
      "reason": "long_pin_track_loss",
      "confidence": 0.24,
      "point": {"x": 0.42, "y": 0.66},
    }

    pose_frames = _build_pose_frames([source_frame])
    public_knee = next(
      keypoint
      for keypoint in pose_frames[0]["keypoints"]
      if keypoint["name"] == "left_knee"
    )

    self.assertEqual(public_knee["x"], 0.60)
    self.assertEqual(public_knee["y"], 0.68)
    self.assertEqual(public_knee["acceptedSource"], "automatic")
    self.assertEqual(public_knee["visualFallback"]["x"], 0.42)
    self.assertEqual(public_knee["visualFallback"]["manualSource"], "pin_visual_fallback")

  def test_pin_selected_side_remains_authoritative_for_rep_depth(self) -> None:
    frames = [
      frame(0, left_visibility=0.55, right_visibility=0.99),
      frame(
        500,
        left_visibility=0.55,
        right_visibility=0.99,
        left_hip_y=0.74,
        left_knee_y=0.58,
        right_hip_y=0.46,
        right_knee_y=0.70,
      ),
      frame(1000, left_visibility=0.55, right_visibility=0.99),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [{
          "start_index": 0,
          "bottom_index": 1,
          "end_index": 2,
          "start_timestamp_ms": 0,
          "bottom_timestamp_ms": 500,
          "end_timestamp_ms": 1000,
        }],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
        selected_side_override="left",
      )

    self.assertEqual(result["diagnostics"]["selected_side"], "left")
    self.assertEqual(result["diagnostics"]["pose_validation"]["selected_side"], "left")
    self.assertEqual(result["reps"][0]["selected_side"], "left")

  def test_rep_summary_uses_selected_side_depth(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70, right_hip_y=0.46, right_knee_y=0.70),
      frame(500, left_hip_y=0.74, left_knee_y=0.58, right_hip_y=0.48, right_knee_y=0.60),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70, right_hip_y=0.46, right_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    self.assertEqual(result["diagnostics"]["selected_side"], "left")
    self.assertGreater(result["reps"][0]["depth_score"], 0.85)
    self.assertEqual(result["reps"][0]["depth_status"], "hit_depth")
    self.assertNotIn("insufficient_depth", result["reps"][0]["flags"])
    self.assertIn("depthConfidence", result["reps"][0])
    self.assertEqual(result["reps"][0]["selected_side"], "left")
    self.assertEqual(result["reps"][0]["bottom_index"], 1)
    self.assertIn("depth_evidence", result["reps"][0])
    self.assertIn("scoring_landmarks", result["reps"][0]["depth_evidence"])
    self.assertIn("estimatedHipCreaseY", result["reps"][0]["depth_evidence"])
    self.assertIn("estimatedKneeTopY", result["reps"][0]["depth_evidence"])
    self.assertIn("depthDeltaPx", result["reps"][0]["depth_evidence"])
    self.assertIn("depthTolerancePx", result["reps"][0]["depth_evidence"])
    self.assertIn("depthReason", result["reps"][0]["depth_evidence"])
    self.assertEqual(result["diagnostics"]["depth_debug"][0]["depth_status"], "hit_depth")
    self.assertIn("videoQuality", result)
    self.assertIn("poseFrames", result)

  def test_depth_uses_clearest_side_not_average(self) -> None:
    frames = [
      frame(
        0,
        left_visibility=0.30,
        right_visibility=0.95,
        left_hip_y=0.46,
        left_knee_y=0.70,
        right_hip_y=0.46,
        right_knee_y=0.70,
      ),
      frame(
        500,
        left_visibility=0.30,
        right_visibility=0.95,
        left_hip_y=0.46,
        left_knee_y=0.70,
        right_hip_y=0.72,
        right_knee_y=0.58,
      ),
      frame(
        1000,
        left_visibility=0.30,
        right_visibility=0.95,
        left_hip_y=0.46,
        left_knee_y=0.70,
        right_hip_y=0.46,
        right_knee_y=0.70,
      ),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["selected_side"], "right")
    self.assertEqual(rep["depth_status"], "hit_depth")
    self.assertNotIn("insufficient_depth", rep["flags"])

  def test_parallel_depth_does_not_flag_insufficient_depth(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(500, left_hip_y=0.58, left_knee_y=0.58),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertGreaterEqual(rep["depth_components"]["parallel_score"], 0.82)
    self.assertEqual(rep["depth_status"], "hit_depth")
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])
    self.assertEqual(result["diagnostics"]["depth_status_counts"]["hit_depth_count"], 1)

  def test_shoulder_occlusion_does_not_fail_visible_hip_knee_depth(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(500, left_hip_y=0.60, left_knee_y=0.58),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]
    frames[1]["landmarks"]["left_shoulder"]["visibility"] = 0.2

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "hit_depth")
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])

  def test_collapsed_hip_shoulder_plate_occlusion_is_uncertain_not_insufficient(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(
        500,
        left_shoulder_x=0.50,
        left_shoulder_y=0.46,
        left_hip_y=0.48,
        left_knee_y=0.68,
      ),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]
    frames[1]["landmarks"]["left_hip"]["x"] = 0.51

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "uncertain_depth")
    self.assertIn("low_depth_confidence", rep["flags"])
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])
    self.assertTrue(rep["depth_evidence"]["plate_rack_occlusion_suspected"])
    self.assertTrue(rep["depth_components"]["bottom_depth_landmarks_unreliable"])

  def test_noisy_bottom_frame_disagreement_is_uncertain_not_insufficient(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(250, left_hip_y=0.60, left_knee_y=0.61),
      frame(500, left_hip_y=0.48, left_knee_y=0.68),
      frame(750, left_hip_y=0.59, left_knee_y=0.60),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 2,
            "end_index": 4,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=5,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "uncertain_depth")
    self.assertEqual(rep["depth_reason"], "bottom_window_disagreement")
    self.assertIn("low_depth_confidence", rep["flags"])
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])
    self.assertEqual(rep["depth_frame_index"], 2)

  def test_visible_bottom_hit_is_not_overridden_by_nearby_noisy_fail(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(250, left_hip_y=0.48, left_knee_y=0.68),
      frame(500, left_hip_y=0.60, left_knee_y=0.58),
      frame(750, left_hip_y=0.48, left_knee_y=0.68),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 2,
            "end_index": 4,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=5,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "hit_depth")
    self.assertEqual(rep["depth_frame_index"], 2)
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])

  def test_hit_and_uncertain_reps_do_not_create_insufficient_summary(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(250, left_hip_y=0.60, left_knee_y=0.58),
      frame(500, left_hip_y=0.46, left_knee_y=0.70),
      frame(750, left_hip_y=0.46, left_knee_y=0.70),
      frame(1000, left_hip_y=0.58, left_knee_y=0.58, left_visibility=0.2),
      frame(1250, left_hip_y=0.46, left_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 250,
            "end_timestamp_ms": 500,
          },
          {
            "start_index": 3,
            "bottom_index": 4,
            "end_index": 5,
            "start_timestamp_ms": 750,
            "bottom_timestamp_ms": 1000,
            "end_timestamp_ms": 1250,
          },
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 2},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=6,
      )

    self.assertEqual(result["reps"][0]["depth_status"], "hit_depth")
    self.assertEqual(result["reps"][1]["depth_status"], "uncertain_depth")
    self.assertNotIn("Insufficient depth", result["summary_flags"])
    self.assertIn("Depth confidence was limited", result["summary_flags"])

  def test_above_parallel_depth_still_flags_insufficient_depth(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70),
      frame(500, left_hip_y=0.48, left_knee_y=0.68),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "insufficient_depth")
    self.assertIn("insufficient_depth", rep["flags"])
    self.assertIn("Insufficient depth", result["summary_flags"])
    self.assertEqual(result["diagnostics"]["depth_status_counts"]["insufficient_depth_count"], 1)

  def test_low_confidence_depth_is_uncertain_not_insufficient(self) -> None:
    frames = [
      frame(0, left_hip_y=0.46, left_knee_y=0.70, left_visibility=0.95),
      frame(500, left_hip_y=0.58, left_knee_y=0.58, left_visibility=0.2),
      frame(1000, left_hip_y=0.46, left_knee_y=0.70, left_visibility=0.95),
    ]

    with patch(
      "app.analysis.exercises.squat.detect_reps",
      return_value=(
        [
          {
            "start_index": 0,
            "bottom_index": 1,
            "end_index": 2,
            "start_timestamp_ms": 0,
            "bottom_timestamp_ms": 500,
            "end_timestamp_ms": 1000,
          }
        ],
        {"motion_amplitude": 0.5, "reason": None, "rep_count": 1},
      ),
    ):
      result = SquatAnalyzer().analyze(
        video_id="video-1",
        exercise_type="squat",
        view_type="side",
        frames=frames,
        sampled_frame_count=3,
      )

    rep = result["reps"][0]
    self.assertEqual(rep["depth_status"], "uncertain_depth")
    self.assertIn("low_depth_confidence", rep["flags"])
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertIn("Depth confidence was limited", result["summary_flags"])
    self.assertNotIn("Insufficient depth", result["summary_flags"])
    self.assertEqual(result["diagnostics"]["depth_status_counts"]["uncertain_depth_count"], 1)

  def test_low_visibility_produces_quality_flags(self) -> None:
    frames = [
      frame(index * 100, left_visibility=0.25, right_visibility=0.20)
      for index in range(6)
    ]

    diagnostics = SquatAnalyzer()._build_quality_report(
      frames=frames,
      sampled_frame_count=6,
    )

    self.assertIn("lower_body_occluded", diagnostics["quality_flags"])
    self.assertEqual(diagnostics["pose_frame_count"], 6)
    self.assertEqual(diagnostics["sampled_frame_count"], 6)

  def test_camera_angle_size_and_jitter_quality_flags(self) -> None:
    frames = [
      frame(0, left_hip_y=0.30, left_knee_y=0.34, left_ankle_y=0.42, shoulder_gap=0.30),
      frame(100, left_hip_y=0.45, left_knee_y=0.26, left_ankle_y=0.42, shoulder_gap=0.30),
      frame(200, left_hip_y=0.28, left_knee_y=0.38, left_ankle_y=0.42, shoulder_gap=0.30),
      frame(300, left_hip_y=0.46, left_knee_y=0.25, left_ankle_y=0.42, shoulder_gap=0.30),
      frame(400, left_hip_y=0.29, left_knee_y=0.37, left_ankle_y=0.42, shoulder_gap=0.30),
    ]

    diagnostics = SquatAnalyzer()._build_quality_report(
      frames=frames,
      sampled_frame_count=5,
    )

    self.assertIn("subject_too_small", diagnostics["quality_flags"])
    self.assertIn("camera_not_side_view", diagnostics["quality_flags"])
    self.assertIn("excessive_landmark_jitter", diagnostics["quality_flags"])


if __name__ == "__main__":
  unittest.main()
