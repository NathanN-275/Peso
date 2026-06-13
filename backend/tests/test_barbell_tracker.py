from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.analysis.barbell_tracking import tracker as tracker_module
from app.analysis.barbell_tracker import (
  BarbellTracker,
  Candidate,
  _remove_motion_outliers,
  _validate_collar_geometry,
)
from app.analysis.barbell_tracking.detection import (
  _crop_bounds_from_landmarks,
  _detect_sleeve_end_candidates,
  _filter_wrist_candidates,
)
from app.analysis.barbell_tracking.geometry import (
  _detect_hub_point,
  _estimate_collar_from_plate,
  _refine_collar_point,
)
from app.analysis.barbell_tracking.selection import _best_initial_plate
from app.analysis.barbell_tracking.sleeve_tracker import track_unloaded_sleeve_end

TEST_COLLAR_OFFSET_RATIO = 0.28


def landmark(x: float, y: float, visibility: float = 0.95) -> dict[str, float]:
  return {
    "x": x,
    "y": y,
    "z": 0.0,
    "visibility": visibility,
  }


def pose_frame(source_frame_index: int, *, x: float, y: float) -> dict[str, object]:
  return {
    "source_frame_index": source_frame_index,
    "timestamp_ms": int(source_frame_index / 18 * 1000),
    "landmarks": {
      "left_shoulder": landmark(x - 0.03, y),
      "right_shoulder": landmark(x + 0.03, y),
      "left_hip": landmark(x - 0.02, y + 0.28),
      "right_hip": landmark(x + 0.02, y + 0.28),
      "left_wrist": landmark(x - 0.09, y + 0.22),
      "right_wrist": landmark(x + 0.09, y + 0.22),
    },
  }


def write_video(
  path: Path,
  centers: list[tuple[int, int] | None],
  *,
  size: tuple[int, int] = (320, 240),
  fps: float = 6.0,
  distractors: list[list[tuple[int, int, int]]] | None = None,
) -> None:
  writer = cv2.VideoWriter(
    str(path),
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps,
    size,
  )
  if not writer.isOpened():
    raise RuntimeError("Unable to open test video writer.")

  for index, center in enumerate(centers):
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    if center is not None:
      cv2.circle(frame, center, 28, (235, 235, 235), 3, cv2.LINE_AA)
      cv2.circle(frame, center, 5, (255, 255, 255), -1, cv2.LINE_AA)
    for x, y, radius in (distractors[index] if distractors else []):
      cv2.circle(frame, (x, y), radius, (235, 235, 235), 3, cv2.LINE_AA)
      cv2.circle(frame, (x, y), 4, (255, 255, 255), -1, cv2.LINE_AA)
    writer.write(frame)

  writer.release()


def collar_from_plate(center: tuple[int, int], radius: int = 42) -> tuple[int, int]:
  return (int(round(center[0] + radius * TEST_COLLAR_OFFSET_RATIO)), center[1])


def write_plate_video(
  path: Path,
  plate_centers: list[tuple[int, int] | None],
  *,
  size: tuple[int, int] = (320, 240),
  fps: float = 6.0,
  plate_radius: int = 42,
  distractors: list[list[tuple[int, int, int]]] | None = None,
) -> None:
  writer = cv2.VideoWriter(
    str(path),
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps,
    size,
  )
  if not writer.isOpened():
    raise RuntimeError("Unable to open test video writer.")

  for index, center in enumerate(plate_centers):
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    if center is not None:
      cv2.circle(frame, center, plate_radius, (72, 118, 108), -1, cv2.LINE_AA)
      cv2.circle(frame, center, plate_radius, (235, 235, 235), 3, cv2.LINE_AA)
      collar = collar_from_plate(center, plate_radius)
      cv2.circle(frame, collar, 7, (245, 245, 245), 2, cv2.LINE_AA)
      cv2.circle(frame, collar, 3, (30, 30, 30), -1, cv2.LINE_AA)
    for x, y, radius in (distractors[index] if distractors else []):
      cv2.circle(frame, (x, y), radius, (235, 235, 235), 3, cv2.LINE_AA)
      cv2.circle(frame, (x, y), 4, (255, 255, 255), -1, cv2.LINE_AA)
    writer.write(frame)

  writer.release()


def write_unloaded_sleeve_video(
  path: Path,
  cap_centers: list[tuple[int, int]],
  *,
  size: tuple[int, int] = (320, 240),
  fps: float = 18.0,
) -> None:
  writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
  if not writer.isOpened():
    raise RuntimeError("Unable to open unloaded sleeve test video writer.")

  for cap_x, cap_y in cap_centers:
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    inner = (190, cap_y + 88)
    direction = np.array([inner[0] - cap_x, inner[1] - cap_y], dtype=np.float64)
    direction /= max(np.linalg.norm(direction), 1.0)
    normal = np.array([-direction[1], direction[0]]) * 8
    for sign in (-1, 1):
      start = (int(round(cap_x + normal[0] * sign)), int(round(cap_y + normal[1] * sign)))
      end = (int(round(inner[0] + normal[0] * sign)), int(round(inner[1] + normal[1] * sign)))
      cv2.line(frame, start, end, (225, 225, 225), 3, cv2.LINE_AA)
    cv2.ellipse(frame, (cap_x, cap_y), (10, 7), 0, 0, 360, (245, 245, 245), 3, cv2.LINE_AA)
    cv2.line(frame, (40, 15), (40, 225), (160, 160, 160), 4, cv2.LINE_AA)
    writer.write(frame)
  writer.release()


class BarbellTrackerTest(unittest.TestCase):
  def test_multiclip_regression_manifest_covers_release_angles(self) -> None:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "barbell_multiclip_manifest.json"
    fixture = json.loads(fixture_path.read_text())
    clips = fixture["clips"]

    self.assertEqual(len(clips), 7)
    self.assertEqual(len({clip["video"] for clip in clips}), 7)
    self.assertEqual(fixture["tolerance_px"], 12)
    self.assertEqual(fixture["maximum_visible_gap_seconds"], 0.5)
    self.assertEqual(
      {clip["target"] for clip in clips},
      {"near_plate_collar_center", "near_sleeve_end_center"},
    )
    self.assertEqual(
      [clip["video"] for clip in clips if clip["target"] == "near_sleeve_end_center"],
      ["IMG_2723.mov"],
    )

  def test_unloaded_sleeve_detector_requires_paired_shaft_edges(self) -> None:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cap = (92, 48)
    cv2.line(frame, (88, 48), (184, 148), (235, 235, 235), 3, cv2.LINE_AA)
    cv2.line(frame, (100, 40), (196, 140), (235, 235, 235), 3, cv2.LINE_AA)
    cv2.ellipse(frame, cap, (11, 8), 0, 0, 360, (250, 250, 250), 3, cv2.LINE_AA)
    cv2.line(frame, (40, 10), (40, 230), (210, 210, 210), 4, cv2.LINE_AA)

    candidates = _detect_sleeve_end_candidates(
      cv2,
      frame,
      shoulder=(220.0, 190.0),
      wrist_points=[(184.0, 150.0)],
    )

    self.assertTrue(candidates)
    self.assertLess(math.hypot(candidates[0].x - cap[0], candidates[0].y - cap[1]), 40.0)
    self.assertGreater(candidates[0].x, 70.0)
    self.assertGreater(candidates[0].confidence, 0.62)

  def test_tracks_unloaded_sleeve_without_accepting_rack_upright(self) -> None:
    cap_centers = [(92, 42 + index * 3) for index in range(18)]
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "unloaded-sleeve.mp4"
      write_unloaded_sleeve_video(path, cap_centers)
      pose_frames = []
      for index, cap in enumerate(cap_centers):
        shoulder_y = cap[1] + 100
        pose_frames.append(
          {
            "source_frame_index": index,
            "timestamp_ms": int(index / 18 * 1000),
            "landmarks": {
              "left_shoulder": landmark(220 / 320, shoulder_y / 240),
              "left_wrist": landmark(184 / 320, (cap[1] + 75) / 240),
              "left_hip": landmark(220 / 320, min((shoulder_y + 40) / 240, 0.98)),
              "left_knee": landmark(220 / 320, 0.9),
              "left_ankle": landmark(220 / 320, 0.97),
            },
          }
        )

      detection_index = 0

      def confirmed_sleeve_candidates(*args, **kwargs):
        nonlocal detection_index
        target = cap_centers[min(detection_index, len(cap_centers) - 1)]
        detection_index += 1
        return [Candidate(x=target[0], y=target[1], radius=28.0, confidence=0.92)]

      with patch(
        "app.analysis.barbell_tracking.sleeve_tracker._detect_sleeve_end_candidates",
        side_effect=confirmed_sleeve_candidates,
      ):
        result = track_unloaded_sleeve_end(
          str(path),
          pose_frames=pose_frames,
          frame_step=1,
          processed_width=320,
          processed_height=240,
          selected_side="left",
          rep_windows=[{"rep_index": 1, "start": 0.0, "bottom": 0.5, "end": 1.0}],
        )

    self.assertIsNotNone(result)
    assert result is not None
    self.assertEqual(result["barbellPath"]["target"], "near_sleeve_end_center")
    self.assertGreaterEqual(len(result["barbellPath"]["points"]), 10)
    for point in result["barbellPath"]["points"]:
      frame_index = min(round(point["time"] * 18), len(cap_centers) - 1)
      target = cap_centers[frame_index]
      distance = math.hypot((point["x"] * 320) - target[0], (point["y"] * 240) - target[1])
      self.assertLessEqual(distance, 12.0)

  def test_unloaded_sleeve_does_not_switch_sides_mid_rep(self) -> None:
    cap_centers = [(92, 42 + index * 3) for index in range(18)]
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "unloaded-sleeve-side-lock.mp4"
      write_unloaded_sleeve_video(path, cap_centers)
      pose_frames = [
        {
          "source_frame_index": index,
          "timestamp_ms": int(index / 18 * 1000),
          "landmarks": {
            "left_shoulder": landmark(220 / 320, (cap[1] + 100) / 240),
            "left_wrist": landmark(184 / 320, (cap[1] + 75) / 240),
            "left_hip": landmark(220 / 320, min((cap[1] + 140) / 240, 0.98)),
          },
        }
        for index, cap in enumerate(cap_centers)
      ]
      detection_index = 0

      def switch_to_rack_side(*args, **kwargs):
        nonlocal detection_index
        target = cap_centers[min(detection_index, len(cap_centers) - 1)]
        detection_index += 1
        if detection_index > 6:
          return [Candidate(x=285.0, y=target[1], radius=28.0, confidence=0.99)]
        return [Candidate(x=target[0], y=target[1], radius=28.0, confidence=0.92)]

      with patch(
        "app.analysis.barbell_tracking.sleeve_tracker._detect_sleeve_end_candidates",
        side_effect=switch_to_rack_side,
      ):
        result = track_unloaded_sleeve_end(
          str(path),
          pose_frames=pose_frames,
          frame_step=1,
          processed_width=320,
          processed_height=240,
          selected_side="left",
          rep_windows=[{"rep_index": 1, "start": 0.0, "bottom": 0.5, "end": 1.0}],
        )

    self.assertIsNotNone(result)
    assert result is not None
    self.assertTrue(result["barbellPath"]["points"])
    self.assertTrue(all(float(point["x"]) * 320 < 220 for point in result["barbellPath"]["points"]))

  def test_low_coverage_sleeve_prepass_does_not_override_loaded_bar(self) -> None:
    plate_centers = [(178, 92 + index * 3) for index in range(18)]
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "loaded-long-sleeve.mp4"
      write_plate_video(path, plate_centers, fps=18.0)
      pose_frames = [
        pose_frame(index, x=(center[0] - 42) / 320, y=center[1] / 240)
        for index, center in enumerate(plate_centers)
      ]
      weak_sleeve_result = {
        "barbellPath": {
          "available": True,
          "target": "near_sleeve_end_center",
          "coverage": 0.1,
          "points": [],
        },
        "diagnostics": {"failure_reason": None},
      }
      with patch.object(tracker_module, "track_unloaded_sleeve_end", return_value=weak_sleeve_result):
        result = BarbellTracker().track(
          str(path),
          pose_frames=pose_frames,
          frame_step=1,
          processed_width=320,
          processed_height=240,
          selected_side="left",
          rep_windows=[{"rep_index": 1, "start": 0.2, "bottom": 0.55, "end": 0.95}],
        )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["barbellPath"]["target"], "near_plate_collar_center")

  def test_reuses_nearest_pose_frames_during_short_pose_dropouts(self) -> None:
    plate_centers = [(178, 92 + index * 2) for index in range(24)]
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "pose-dropouts.mp4"
      write_plate_video(path, plate_centers, fps=18.0)
      pose_frames = [
        pose_frame(index, x=(plate_centers[index][0] - 42) / 320, y=plate_centers[index][1] / 240)
        for index in range(0, len(plate_centers), 3)
      ]
      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
        rep_windows=[{"rep_index": 1, "start": 0.2, "bottom": 0.7, "end": 1.25}],
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertGreater(result["diagnostics"]["reused_nearest_pose_frame_count"], 0)
    self.assertLessEqual(result["diagnostics"]["max_point_gap_seconds"], 0.5)

  def test_collar_direction_points_away_from_selected_side_shoulder(self) -> None:
    left_plate = Candidate(x=150.0, y=90.0, radius=42.0, confidence=0.9)
    right_plate = Candidate(x=250.0, y=90.0, radius=42.0, confidence=0.9)

    left_collar, left_direction = _estimate_collar_from_plate(
      left_plate,
      shoulder=(220.0, 110.0),
      width=320,
      height=240,
    )
    right_collar, right_direction = _estimate_collar_from_plate(
      right_plate,
      shoulder=(180.0, 110.0),
      width=320,
      height=240,
    )

    self.assertLess(left_direction[0], 0.0)
    self.assertLess(left_collar[0], left_plate.x)
    self.assertGreater(right_direction[0], 0.0)
    self.assertGreater(right_collar[0], right_plate.x)
    self.assertIsNone(
      _validate_collar_geometry(
        left_collar,
        plate=left_plate,
        sleeve_direction=left_direction,
      )
    )

  def _track(self, centers: list[tuple[int, int] | None], *, fps: float = 6.0, frame_step: int = 1) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell.mp4"
      write_video(path, centers, fps=fps)
      pose_frames = [
        pose_frame(index, x=(center[0] / 320 if center else 0.5), y=(center[1] / 240 if center else 0.4))
        for index, center in enumerate(centers)
        if index % frame_step == 0
      ]
      return BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=frame_step,
        processed_width=320,
        processed_height=240,
      )

  def assert_points_follow_target_path(
    self,
    points: list[dict[str, float]],
    plate_centers: list[tuple[int, int]],
    *,
    fps: float = 6.0,
    max_distance_px: float = 12.0,
  ) -> None:
    self.assertTrue(points)
    for point in points:
      frame_index = min(max(int(round(float(point["time"]) * fps)), 0), len(plate_centers) - 1)
      expected = collar_from_plate(plate_centers[frame_index])
      actual = (float(point["x"]) * 320, float(point["y"]) * 240)
      distance = math.hypot(actual[0] - expected[0], actual[1] - expected[1])
      self.assertLessEqual(distance, max_distance_px)

  def test_prefers_large_plate_center_over_body_distractors(self) -> None:
    centers = [(226, 72 + index * 2) for index in range(10)]
    distractors = [[(148, 118 + index, 8), (178, 140, 6)] for index in range(10)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-distractors.mp4"
      write_video(path, centers, distractors=distractors)
      pose_frames = [
        pose_frame(index, x=0.48, y=0.43)
        for index in range(len(centers))
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    first_point = result["barbellPath"]["points"][0]
    self.assertAlmostEqual(first_point["x"], 226 / 320, delta=0.06)
    self.assertAlmostEqual(first_point["y"], 72 / 240, delta=0.08)

  def test_bootstrap_prefers_shoulder_aligned_collar_candidate_over_shifted_plate_arc(self) -> None:
    shifted_plate_arc = Candidate(x=662.16, y=802.80, radius=188.66, confidence=0.62)
    shoulder_aligned_collar = Candidate(x=514.96, y=736.56, radius=196.76, confidence=0.62)

    selected = _best_initial_plate(
      [shifted_plate_arc, shoulder_aligned_collar],
      pending_plate=None,
      shoulder=(480.0, 905.0),
      width=1080,
      height=1920,
    )

    self.assertEqual(selected, shoulder_aligned_collar)

  def test_bootstrap_starts_on_plate_center_before_motion(self) -> None:
    centers = [(226, 72), (226, 72), (226, 72), (226, 78), (226, 84), (226, 90)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-start.mp4"
      write_video(path, centers)
      pose_frames = [pose_frame(index, x=0.48, y=0.43) for index in range(len(centers))]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    first_point = result["barbellPath"]["points"][0]
    self.assertAlmostEqual(first_point["x"], 226 / 320, delta=0.06)
    self.assertAlmostEqual(first_point["y"], 72 / 240, delta=0.08)

  def test_bootstrap_rejects_high_rack_hardware(self) -> None:
    centers = [(226, 72), (226, 72), (226, 78), (226, 84), (226, 90), (226, 96)]
    distractors = [[(226, 32, 10), (178, 128, 8)] for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-rack-distractor.mp4"
      write_video(path, centers, distractors=distractors)
      pose_frames = [pose_frame(index, x=0.48, y=0.43) for index in range(len(centers))]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    first_point = result["barbellPath"]["points"][0]
    self.assertAlmostEqual(first_point["x"], 226 / 320, delta=0.06)
    self.assertAlmostEqual(first_point["y"], 72 / 240, delta=0.08)

  def test_rejects_high_rack_loop_when_collar_is_missing(self) -> None:
    centers = [None for _ in range(10)]
    distractors = [[(226, 32, 18), (210, 38, 14)] for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-rack-loop.mp4"
      write_video(path, centers, distractors=distractors)
      pose_frames = [pose_frame(index, x=0.48, y=0.43) for index in range(len(centers))]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertFalse(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["failure_reason"], "low_barbell_tracking_coverage")

  def test_prefers_candidate_moving_with_shoulder_over_stationary_rack(self) -> None:
    centers = [(210 + index * 4, 104) for index in range(12)]
    stationary_rack = [(250, 104, 28)]
    distractors = [stationary_rack for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-relative-motion.mp4"
      write_plate_video(path, centers, distractors=distractors, plate_radius=28)
      pose_frames = [
        pose_frame(index, x=(center[0] - 60) / 320, y=0.43)
        for index, center in enumerate(centers)
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assert_points_follow_target_path(result["barbellPath"]["points"], centers, max_distance_px=14.0)

  def test_reliable_manual_collar_priors_drive_the_reported_path(self) -> None:
    frame_count = 8
    stationary_rack = [(252, 102) for _ in range(frame_count)]
    manual_centers = [(184 + (index * 3), 92 + (index * 2)) for index in range(frame_count)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "manual-collar-priors.mp4"
      write_video(path, stationary_rack, fps=6.0)
      pose_frames = [
        pose_frame(index, x=0.55, y=0.40)
        for index in range(frame_count)
      ]
      manual_priors = {
        index: {
          "x": center[0] / 320,
          "y": center[1] / 240,
          "confidence": 0.95,
        }
        for index, center in enumerate(manual_centers)
      }

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
        manual_barbell_priors=manual_priors,
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["manual_point_count"], frame_count)
    self.assertEqual(result["diagnostics"]["automatic_point_count"], 0)
    self.assertEqual(len(result["barbellPath"]["points"]), frame_count)
    for point, expected in zip(result["barbellPath"]["points"], manual_centers):
      self.assertAlmostEqual(float(point["x"]) * 320, expected[0], delta=1.0)
      self.assertAlmostEqual(float(point["y"]) * 240, expected[1], delta=1.0)

  def test_manual_collar_reentry_requires_two_consecutive_valid_frames(self) -> None:
    frame_count = 6
    centers = [(184 + (index * 3), 92 + index) for index in range(frame_count)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "manual-collar-reentry.mp4"
      write_video(path, centers, fps=6.0)
      pose_frames = [pose_frame(index, x=0.55, y=0.40) for index in range(frame_count)]
      manual_priors = {
        index: {
          "x": centers[index][0] / 320,
          "y": centers[index][1] / 240,
          "confidence": 0.95,
        }
        for index in (0, 1, 3, 4, 5)
      }

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
        manual_barbell_priors=manual_priors,
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["manual_point_count"], 4)
    manual_times = [
      round(float(point["time"]), 3)
      for point in result["barbellPath"]["points"]
      if point.get("manual_assisted")
    ]
    self.assertNotIn(round(3 / 6, 3), manual_times)
    self.assertIn(round(4 / 6, 3), manual_times)

  def test_plate_first_tracker_outputs_collar_target(self) -> None:
    plate_centers = [(178 + index * 3, 104) for index in range(8)]
    distractors = [[(238, 104, 34)] for _ in plate_centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-moving-plate.mp4"
      write_plate_video(path, plate_centers, distractors=distractors)
      pose_frames = [
        pose_frame(index, x=(plate_center[0] - 42) / 320, y=0.43)
        for index, plate_center in enumerate(plate_centers)
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["selected_candidate_type"], "plate")
    points = result["barbellPath"]["points"]
    self.assert_points_follow_target_path(points, plate_centers, max_distance_px=12.0)
    self.assertTrue(result["diagnostics"]["initialization_confirmed"])
    self.assertEqual(result["diagnostics"]["initialization_frame_count"], 3)
    self.assertLessEqual(result["diagnostics"]["hough_detection_count"], 4)
    self.assertIn(
      result["diagnostics"]["local_tracker_type"],
      ("klt_optical_flow", "template_matching", "fresh_hough_validation"),
    )

  def test_tracks_near_linear_collar_path_with_rack_and_wrist_distractors(self) -> None:
    plate_centers = [(176 + index * 2, 100 + index * 4) for index in range(14)]
    distractors = [
      [
        (center[0] + 58, center[1] + (18 if index >= 7 else -10), 34),
        (center[0] - 42, center[1] + 22, 14),
      ]
      for index, center in enumerate(plate_centers)
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-linear-collar-distractors.mp4"
      write_plate_video(path, plate_centers, distractors=distractors)
      pose_frames = [
        pose_frame(
          index,
          x=(plate_center[0] - 42) / 320,
          y=(plate_center[1] + 4) / 240,
        )
        for index, plate_center in enumerate(plate_centers)
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assert_points_follow_target_path(result["barbellPath"]["points"], plate_centers, max_distance_px=12.0)
    self.assertEqual(result["barbellPath"]["target"], "near_plate_collar_center")

  def test_real_img0013_fixture_tracks_only_labeled_collar_targets(self) -> None:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "barbell_img0013_collar_labels.json"
    fixture = json.loads(fixture_path.read_text())
    video_path = Path(__file__).resolve().parents[1] / "test_videos" / fixture["video"]
    if not video_path.exists():
      self.skipTest(f"local regression video is unavailable: {video_path}")
    width = int(fixture["coordinate_space"]["width"])
    height = int(fixture["coordinate_space"]["height"])
    frame_step = int(fixture["frame_step"])
    fps = float(fixture["fps"])

    result = BarbellTracker().track(
      str(video_path),
      pose_frames=fixture["pose_frames"],
      frame_step=frame_step,
      processed_width=width,
      processed_height=height,
      selected_side=fixture["selected_side"],
      rep_windows=fixture["rep_windows"],
    )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["barbellPath"]["target"], "near_plate_collar_center")
    points = result["barbellPath"]["points"]
    tolerance = float(fixture["tolerance_px"])
    visible_hits = 0
    required_hits_by_rep: dict[int, int] = {}
    for label in fixture["labels"]:
      label_time = label["source_frame_index"] / fps
      nearby = [
        point
        for point in points
        if abs(float(point["time"]) - label_time) <= 0.07
      ]
      if label["allowed_missing"]:
        continue

      self.assertTrue(nearby, f"missing barbell point near frame {label['source_frame_index']}")
      target_x, target_y = label["target"]
      closest = min(nearby, key=lambda point: abs(float(point["time"]) - label_time))
      distance = math.hypot(
        (float(closest["x"]) * width) - target_x,
        (float(closest["y"]) * height) - target_y,
      )
      self.assertLessEqual(
        distance,
        tolerance,
        f"barbell point exceeded tolerance near frame {label['source_frame_index']}",
      )
      visible_hits += 1
      rep_index = int(label["rep_index"])
      required_hits_by_rep[rep_index] = required_hits_by_rep.get(rep_index, 0) + 1

    self.assertEqual(visible_hits, 9)
    self.assertEqual(required_hits_by_rep, {1: 3, 2: 3, 3: 3})
    self.assertLessEqual(result["diagnostics"]["max_point_gap_seconds"], 0.9)

  def test_path_prior_marks_drifting_local_updates_missing(self) -> None:
    accepted_points = [
      (179.0, 96.0),
      (180.0, 104.0),
      (181.0, 112.0),
      (182.0, 120.0),
      (183.0, 128.0),
    ]

    reason, residual, _ = BarbellTracker()._path_prior_rejection_reason(
      (207.0, 136.0),
      accepted_points,
      timestamp=0.5,
      last_accepted_timestamp=0.4,
      max_dimension=320,
    )

    self.assertEqual(reason, "path_residual_drift")
    self.assertIsNotNone(residual)
    self.assertGreater(residual, tracker_module.PATH_PRIOR_MAX_RESIDUAL_PX)

  def test_hub_detection_accepts_compact_visible_hub(self) -> None:
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    plate = Candidate(x=120, y=90, radius=42, confidence=0.9)
    cv2.circle(frame, (120, 90), 42, (72, 118, 108), -1, cv2.LINE_AA)
    cv2.circle(frame, (120, 90), 42, (235, 235, 235), 3, cv2.LINE_AA)
    cv2.circle(frame, (130, 90), 7, (245, 245, 245), 2, cv2.LINE_AA)
    cv2.circle(frame, (130, 90), 3, (30, 30, 30), -1, cv2.LINE_AA)

    result = _detect_hub_point(cv2, frame, plate=plate)

    self.assertEqual(result["source"], "hough_hub")
    self.assertIsNone(result["reason"])
    self.assertIsNotNone(result["point"])
    self.assertGreaterEqual(result["confidence"], 0.8)

  def test_hub_detection_does_not_emit_plate_center_fallback(self) -> None:
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    plate = Candidate(x=120, y=90, radius=42, confidence=0.9)
    cv2.circle(frame, (120, 90), 42, (72, 118, 108), -1, cv2.LINE_AA)
    cv2.circle(frame, (120, 90), 42, (235, 235, 235), 3, cv2.LINE_AA)

    result = _detect_hub_point(cv2, frame, plate=plate)

    self.assertIsNone(result["point"])
    self.assertEqual(result["source"], "no_hub")
    self.assertIn(result["reason"], ("moments_fallback_uncertain", "no_hub_candidates"))

  def test_detection_crop_is_anchored_to_shoulder(self) -> None:
    shoulder = (136.0, 103.2)
    wrist = (260.0, 200.0)
    landmarks = {
      "left_shoulder": landmark((shoulder[0] - 9.6) / 320, shoulder[1] / 240),
      "right_shoulder": landmark((shoulder[0] + 9.6) / 320, shoulder[1] / 240),
      "left_wrist": landmark(wrist[0] / 320, wrist[1] / 240),
    }

    diagnostics = _crop_bounds_from_landmarks(
      landmarks,
      width=320,
      height=240,
      fallback_bounds=(0.0, 0.0, 320.0, 240.0),
    )

    crop_x0, crop_y0, crop_x1, crop_y1 = diagnostics["crop_bounds"]
    crop_center_x = (crop_x0 + crop_x1) / 2
    self.assertEqual(diagnostics["anchor_landmark"], "shoulder")
    self.assertAlmostEqual(crop_center_x, shoulder[0], delta=8.0)
    self.assertLess(abs(crop_center_x - shoulder[0]), abs(crop_center_x - wrist[0]))

  def test_oblique_plate_zone_allows_plate_far_from_shoulder(self) -> None:
    candidate = Candidate(x=110.0, y=110.0, radius=48.0, confidence=0.8)
    reason = tracker_module._plate_rejection_reason(
      candidate,
      previous=None,
      shoulder=(250.0, 105.0),
      width=320,
      height=240,
      bootstrapping=True,
    )

    self.assertIsNone(reason)

  def test_oblique_plate_zone_allows_large_near_plate(self) -> None:
    candidate = Candidate(x=74.0, y=98.0, radius=70.0, confidence=0.8)

    reason = tracker_module._plate_rejection_reason(
      candidate,
      previous=None,
      shoulder=(106.0, 137.0),
      width=270,
      height=480,
      bootstrapping=True,
    )

    self.assertIsNone(reason)

  def test_oblique_plate_zone_still_rejects_frame_spanning_circle(self) -> None:
    candidate = Candidate(x=106.0, y=137.0, radius=92.0, confidence=0.8)

    reason = tracker_module._plate_rejection_reason(
      candidate,
      previous=None,
      shoulder=(106.0, 137.0),
      width=270,
      height=480,
      bootstrapping=True,
    )

    self.assertEqual(reason, "generic_circle_too_large")

  def test_detection_rejects_wrist_region_circle(self) -> None:
    wrist = (166.0, 112.0)
    landmarks = {"left_wrist": landmark(wrist[0] / 320, wrist[1] / 240)}
    candidates = [
      Candidate(x=166.0, y=112.0, radius=22.0, confidence=0.62),
      Candidate(x=226.0, y=72.0, radius=28.0, confidence=0.62),
    ]

    filtered, wrist_rejected_count = _filter_wrist_candidates(candidates, landmarks, width=320, height=240)

    self.assertEqual(wrist_rejected_count, 1)
    self.assertEqual(filtered, [candidates[1]])

  def test_detection_keeps_plate_sized_candidate_adjacent_to_wrist(self) -> None:
    wrist = (102.0, 122.0)
    landmarks = {"left_wrist": landmark(wrist[0] / 320, wrist[1] / 240)}
    plate = Candidate(x=74.0, y=98.0, radius=55.0, confidence=0.78)

    filtered, wrist_rejected_count = _filter_wrist_candidates(
      [plate],
      landmarks,
      width=320,
      height=240,
    )

    self.assertEqual(wrist_rejected_count, 0)
    self.assertEqual(filtered, [plate])

  def test_tracker_bootstrap_diagnostics_are_inspectable_without_video(self) -> None:
    tracker = BarbellTracker()

    diagnostic = tracker._record_bootstrap_diagnostic(
      frame_index=4,
      tracking_mode="initializing",
      detection_diagnostics={
        "anchor_landmark": "shoulder",
        "crop_bounds": (27.0, 45.0, 245.0, 152.0),
        "wrist_rejected_count": 1,
      },
      shoulder=(136.0, 103.2),
      wrist_points=[(166.0, 112.0)],
      selected_plate=Candidate(x=226.0, y=72.0, radius=28.0, confidence=0.62),
    )

    self.assertIs(diagnostic, tracker.bootstrap_diagnostics["frames"][0])
    self.assertEqual(tracker.bootstrap_diagnostics["frames"][0]["crop_anchor_landmark"], "shoulder")
    self.assertEqual(tracker.bootstrap_diagnostics["frames"][0]["winning_candidate_x"], 226.0)
    self.assertEqual(tracker.bootstrap_diagnostics["frames"][0]["winning_candidate_y"], 72.0)
    self.assertEqual(tracker.bootstrap_diagnostics["frames"][0]["wrist_rejected_count"], 1)

  def test_initialization_requires_multiple_frame_consistency(self) -> None:
    plate_centers = [(178 + index * 2, 104) for index in range(2)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-short-init.mp4"
      write_plate_video(path, plate_centers)
      pose_frames = [
        pose_frame(index, x=(plate_center[0] - 42) / 320, y=0.43)
        for index, plate_center in enumerate(plate_centers)
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertFalse(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["detected_point_count"], 0)
    self.assertFalse(result["diagnostics"]["initialization_confirmed"])

  def test_collar_geometry_rejects_backward_left_drift(self) -> None:
    plate = Candidate(x=178, y=104, radius=42, confidence=0.9)

    reason = _validate_collar_geometry(
      (plate.x - 10, plate.y),
      plate=plate,
      sleeve_direction=(0.996, -0.09),
    )

    self.assertEqual(reason, "collar_behind_plate")

  def test_collar_geometry_rejects_sudden_direction_flip(self) -> None:
    plate = Candidate(x=178, y=104, radius=42, confidence=0.9)

    reason = _validate_collar_geometry(
      (plate.x + 2, plate.y - 14),
      plate=plate,
      sleeve_direction=(0.996, -0.09),
      previous={"collar_dx": 12, "collar_dy": -1},
    )

    self.assertEqual(reason, "collar_direction_flip")

  def test_collar_geometry_rejects_far_point_from_plate(self) -> None:
    plate = Candidate(x=178, y=104, radius=42, confidence=0.9)

    reason = _validate_collar_geometry(
      (plate.x + 30, plate.y),
      plate=plate,
      sleeve_direction=(0.996, -0.09),
    )

    self.assertEqual(reason, "collar_too_far_from_plate")

  def test_final_collar_stays_within_plate_scaled_distance(self) -> None:
    plate_centers = [(178 + index * 2, 104) for index in range(8)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-collar-distance.mp4"
      write_plate_video(path, plate_centers)
      pose_frames = [
        pose_frame(index, x=(plate_center[0] - 42) / 320, y=0.43)
        for index, plate_center in enumerate(plate_centers)
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    diagnostics = result["diagnostics"]
    distance = ((diagnostics["final_collar_x"] - diagnostics["plate_center_x"]) ** 2 + (diagnostics["final_collar_y"] - diagnostics["plate_center_y"]) ** 2) ** 0.5
    self.assertLessEqual(distance, diagnostics["plate_radius"] * 0.35)
    self.assertGreaterEqual(distance, diagnostics["plate_radius"] * 0.1)

  def test_collar_refinement_rejects_edge_outside_sleeve_axis_window(self) -> None:
    frame = np.zeros((220, 260, 3), dtype=np.uint8)
    plate = Candidate(x=100, y=100, radius=160, confidence=0.9)
    predicted = (145.0, 100.0)
    cv2.circle(frame, (126, 120), 4, (255, 255, 255), 1, cv2.LINE_AA)

    refined, penalty, reason = _refine_collar_point(
      cv2,
      frame,
      predicted=predicted,
      plate=plate,
      sleeve_direction=(1.0, 0.0),
    )

    self.assertEqual(refined, predicted)
    self.assertGreater(penalty, 0)
    self.assertEqual(reason, "collar_refinement_outside_sleeve_axis")

  def test_collar_refinement_rejects_edge_beyond_geometric_distance_cap(self) -> None:
    frame = np.zeros((160, 200, 3), dtype=np.uint8)
    plate = Candidate(x=100, y=80, radius=8, confidence=0.9)
    predicted = (103.0, 80.0)
    cv2.line(frame, (108, 80), (109, 80), (255, 255, 255), 1, cv2.LINE_AA)

    refined, penalty, reason = _refine_collar_point(
      cv2,
      frame,
      predicted=predicted,
      plate=plate,
      sleeve_direction=(1.0, 0.0),
    )

    self.assertEqual(refined, predicted)
    self.assertGreater(penalty, 0)
    self.assertEqual(reason, "collar_refinement_too_far_from_geometric_estimate")

  def test_sudden_backward_drift_removed_as_outlier(self) -> None:
    points = [
      {"time": 0.0, "x": 0.62, "y": 0.43, "confidence": 1.0},
      {"time": 0.1, "x": 0.63, "y": 0.42, "confidence": 1.0},
      {"time": 0.2, "x": 0.34, "y": 0.44, "confidence": 1.0},
      {"time": 0.3, "x": 0.64, "y": 0.41, "confidence": 1.0},
    ]

    filtered, removed_count = _remove_motion_outliers(points)

    self.assertEqual(removed_count, 1)
    self.assertNotIn(points[2], filtered)

  def test_shoulder_motion_with_stationary_plate_marks_frames_missing(self) -> None:
    plate_centers = [(178, 104) for _ in range(8)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-stationary-plate-moving-shoulder.mp4"
      write_plate_video(path, plate_centers)
      pose_frames = [
        pose_frame(index, x=(136 + index * 7) / 320, y=0.43)
        for index in range(len(plate_centers))
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertLess(result["diagnostics"]["detected_point_count"], result["diagnostics"]["sampled_frame_count"])
    self.assertGreater(result["diagnostics"]["rejection_reason_counts"].get("stationary_hardware_like", 0), 0)

  def test_bootstrap_rejects_stationary_candidate_when_shoulder_moves(self) -> None:
    centers = [None for _ in range(8)]
    distractors = [[(178, 104, 42)] for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-stationary-bootstrap-hardware.mp4"
      write_video(path, centers, distractors=distractors)
      pose_frames = [
        pose_frame(index, x=(136 + index * 7) / 320, y=0.43)
        for index in range(len(centers))
      ]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertFalse(result["barbellPath"]["available"])
    self.assertFalse(result["diagnostics"]["initialization_confirmed"])
    self.assertGreater(sum(result["diagnostics"]["bad_candidate_rejection_counts"].values()), 0)

  def test_rejects_high_large_j_cup_candidate(self) -> None:
    centers = [(210, 104), (210, 104), (210, 108), (210, 112), (210, 116), (210, 120)]
    distractors = [[(210, 56, 36)] for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-large-jcup.mp4"
      write_video(path, centers, distractors=distractors)
      pose_frames = [pose_frame(index, x=0.47, y=0.43) for index in range(len(centers))]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    first_point = result["barbellPath"]["points"][0]
    self.assertAlmostEqual(first_point["x"], 210 / 320, delta=0.07)
    self.assertAlmostEqual(first_point["y"], 104 / 240, delta=0.08)

  def test_plate_first_rejects_high_jcup_over_plate(self) -> None:
    plate_centers = [(178, 104), (178, 104), (178, 108), (178, 112), (178, 116), (178, 120)]
    distractors = [[(178, 56, 44)] for _ in plate_centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-high-jcup-plate.mp4"
      write_plate_video(path, plate_centers, distractors=distractors)
      pose_frames = [pose_frame(index, x=0.43, y=0.43) for index in range(len(plate_centers))]

      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
      )

    self.assertTrue(result["barbellPath"]["available"])
    tracking_frames = result["diagnostics"]["bootstrap_diagnostics"]["tracking_frames"]
    emitted = [frame for frame in tracking_frames if frame["emitted_pixel_y"] is not None]
    self.assertTrue(emitted)
    for frame in emitted:
      self.assertGreater(frame["emitted_pixel_y"], 95)
    self.assertGreater(result["diagnostics"]["rejection_reason_counts"].get("too_high_above_shoulder", 0), 0)

  def test_tracks_at_pose_cadence_on_sixty_fps_video(self) -> None:
    centers = [(150, 78 + (index // 10)) for index in range(60)]

    result = self._track(centers, fps=60.0, frame_step=3)

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["tracking_frame_step"], 3)
    self.assertLessEqual(result["diagnostics"]["sampled_frame_count"], 21)
    self.assertGreaterEqual(result["diagnostics"]["sampled_frame_count"], 18)
    self.assertGreaterEqual(result["diagnostics"]["effective_tracking_fps"], 15.0)

  def test_local_tracking_continues_when_fresh_plate_detection_drops_out(self) -> None:
    plate_centers = [(178 + index * 3, 104 + index) for index in range(12)]
    original_detect = tracker_module._detect_crop_candidates
    detection_call_count = 0

    def detect_then_drop(*args, **kwargs):
      nonlocal detection_call_count
      detection_call_count += 1
      if detection_call_count > 3:
        frame = args[1]
        height, width = frame.shape[:2]
        return [], 0, 0, {
          "anchor_landmark": "test_drop_out",
          "crop_bounds": (0.0, 0.0, float(width), float(height)),
          "wrist_rejected_count": 0,
        }
      return original_detect(*args, **kwargs)

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-fresh-detection-dropout.mp4"
      write_plate_video(path, plate_centers)
      pose_frames = [
        pose_frame(index, x=(plate_center[0] - 42) / 320, y=0.43)
        for index, plate_center in enumerate(plate_centers)
      ]

      with patch.object(tracker_module, "_detect_crop_candidates", side_effect=detect_then_drop):
        result = BarbellTracker().track(
          str(path),
          pose_frames=pose_frames,
          frame_step=1,
          processed_width=320,
          processed_height=240,
        )

    self.assertTrue(result["barbellPath"]["available"])
    diagnostics = result["diagnostics"]
    self.assertGreaterEqual(diagnostics["accepted_local_tracking_count"], 5)
    self.assertEqual(diagnostics["local_tracking_failure_count"], 0)
    self.assertLessEqual(diagnostics["max_point_gap_seconds"], 0.18)
    points = result["barbellPath"]["points"]
    expected_final_collar = collar_from_plate(plate_centers[-1])
    self.assertAlmostEqual(points[-1]["x"], expected_final_collar[0] / 320, delta=0.06)
    self.assertAlmostEqual(points[-1]["y"], expected_final_collar[1] / 240, delta=0.06)

  def test_returns_unavailable_without_pose_frames(self) -> None:
    centers = [(150, 78) for _ in range(20)]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-no-pose.mp4"
      write_video(path, centers, fps=60.0)
      result = BarbellTracker().track(
        str(path),
        pose_frames=[],
        frame_step=3,
        processed_width=320,
        processed_height=240,
      )

    self.assertFalse(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["failure_reason"], "no_pose_frames")
    self.assertEqual(result["diagnostics"]["sampled_frame_count"], 0)

  def test_tracks_synthetic_moving_plate_center(self) -> None:
    centers = [(150, 78 + index * 5) for index in range(10)]

    result = self._track(centers)

    self.assertTrue(result["barbellPath"]["available"])
    points = result["barbellPath"]["points"]
    self.assertGreaterEqual(len(points), 8)
    self.assertAlmostEqual(points[0]["x"], 150 / 320, delta=0.05)
    self.assertLess(points[0]["y"], points[-1]["y"])
    self.assertEqual(result["barbellPath"]["target"], "near_plate_collar_center")

  def test_does_not_interpolate_across_target_switch(self) -> None:
    centers: list[tuple[int, int] | None] = [
      (150, 82),
      (150, 88),
      (150, 94),
      (150, 100),
      None,
      None,
      (150, 106),
      (150, 112),
      (150, 118),
      (150, 124),
    ]

    result = self._track(centers)

    self.assertGreaterEqual(result["diagnostics"]["detected_point_count"], 4)
    self.assertGreater(result["diagnostics"]["local_tracking_failure_count"], 0)
    self.assertEqual(result["diagnostics"]["interpolated_point_count"], 0)

  def test_reacquires_new_rep_after_missing_gap_without_stale_path_lockout(self) -> None:
    centers: list[tuple[int, int] | None] = [
      (150, 82),
      (150, 88),
      (150, 94),
      (150, 100),
      (150, 106),
      (150, 112),
      None,
      None,
      None,
      None,
      None,
      None,
      (225, 82),
      (225, 88),
      (225, 94),
      (225, 100),
      (225, 106),
      (225, 112),
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-rep-gap.mp4"
      write_plate_video(path, centers, fps=6.0)
      pose_frames = [
        pose_frame(
          index,
          x=((center[0] - 20) / 320 if center else 0.5),
          y=((center[1] + 20) / 240 if center else 0.45),
        )
        for index, center in enumerate(centers)
      ]
      result = BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
        processed_width=320,
        processed_height=240,
        selected_side="left",
        rep_windows=[
          {"rep_index": 1, "start": 0.0, "bottom": 0.5, "end": 0.9},
          {"rep_index": 2, "start": 2.0, "bottom": 2.5, "end": 2.9},
        ],
      )

    self.assertTrue(result["barbellPath"]["available"])
    points = result["barbellPath"]["points"]
    self.assertTrue(any(float(point["time"]) < 1.0 for point in points))
    self.assertTrue(any(float(point["time"]) >= 2.0 for point in points))
    self.assertGreaterEqual(result["diagnostics"]["path_reset_count"], 1)
    self.assertGreaterEqual(result["diagnostics"]["reacquisition_success_count"], 1)

  def test_returns_unavailable_when_no_stable_circle_exists(self) -> None:
    result = self._track([None for _ in range(10)])

    self.assertFalse(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["failure_reason"], "low_barbell_tracking_coverage")


if __name__ == "__main__":
  unittest.main()
