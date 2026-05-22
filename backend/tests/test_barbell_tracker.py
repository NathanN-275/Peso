from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.analysis.barbell_tracker import BarbellTracker

TEST_COLLAR_OFFSET_RATIO = 0.34


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
      "left_wrist": landmark(x - 0.09, y + 0.04),
      "right_wrist": landmark(x + 0.09, y + 0.04),
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
  plate_centers: list[tuple[int, int]],
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


class BarbellTrackerTest(unittest.TestCase):
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

  def test_prefers_large_plate_center_over_body_distractors(self) -> None:
    centers = [(226, 72 + index * 2) for index in range(10)]
    distractors = [[(148, 118 + index, 16), (178, 140, 12)] for index in range(10)]

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

  def test_bootstrap_starts_on_plate_center_before_motion(self) -> None:
    centers = [(226, 72), (226, 72), (226, 72), (226, 78), (226, 84), (226, 90)]
    distractors = [[(150, 116, 18), (178, 132, 16)] for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-start.mp4"
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

  def test_bootstrap_rejects_high_rack_hardware(self) -> None:
    centers = [(226, 72), (226, 72), (226, 78), (226, 84), (226, 90), (226, 96)]
    distractors = [[(226, 32, 18), (178, 128, 16)] for _ in centers]

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
    centers = [(210 + index * 4, 104) for index in range(8)]
    stationary_rack = [(250, 104, 28)]
    distractors = [stationary_rack for _ in centers]

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell-relative-motion.mp4"
      write_video(path, centers, distractors=distractors)
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
    points = result["barbellPath"]["points"]
    self.assertAlmostEqual(points[0]["x"], centers[0][0] / 320, delta=0.07)
    self.assertAlmostEqual(points[-1]["x"], centers[-1][0] / 320, delta=0.07)

  def test_plate_first_tracker_outputs_derived_collar_point(self) -> None:
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
    first_collar = collar_from_plate(plate_centers[0])
    last_collar = collar_from_plate(plate_centers[-1])
    self.assertAlmostEqual(points[0]["x"], first_collar[0] / 320, delta=0.07)
    self.assertAlmostEqual(points[0]["y"], first_collar[1] / 240, delta=0.08)
    self.assertAlmostEqual(points[-1]["x"], last_collar[0] / 320, delta=0.07)

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
    first_collar = collar_from_plate(plate_centers[0])
    first_point = result["barbellPath"]["points"][0]
    self.assertAlmostEqual(first_point["x"], first_collar[0] / 320, delta=0.07)
    self.assertAlmostEqual(first_point["y"], first_collar[1] / 240, delta=0.08)
    self.assertGreater(result["diagnostics"]["rejection_reason_counts"].get("too_high_above_shoulder", 0), 0)

  def test_tracks_about_six_fps_on_sixty_fps_video(self) -> None:
    centers = [(150, 78 + (index // 10)) for index in range(60)]

    result = self._track(centers, fps=60.0, frame_step=3)

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["tracking_frame_step"], 9)
    self.assertLessEqual(result["diagnostics"]["sampled_frame_count"], 8)
    self.assertGreaterEqual(result["diagnostics"]["sampled_frame_count"], 6)

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

  def test_interpolates_short_occlusion_gap(self) -> None:
    centers: list[tuple[int, int] | None] = [
      (150, 82),
      (150, 88),
      (150, 94),
      None,
      None,
      (150, 112),
      (150, 118),
      (150, 124),
    ]

    result = self._track(centers)

    self.assertTrue(result["barbellPath"]["available"])
    self.assertGreaterEqual(result["diagnostics"]["interpolated_point_count"], 2)
    self.assertGreaterEqual(len(result["barbellPath"]["points"]), 7)

  def test_returns_unavailable_when_no_stable_circle_exists(self) -> None:
    result = self._track([None for _ in range(10)])

    self.assertFalse(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["failure_reason"], "low_barbell_tracking_coverage")


if __name__ == "__main__":
  unittest.main()
