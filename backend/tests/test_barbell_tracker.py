from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.analysis.barbell_tracker import BarbellTracker


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
  distractors: list[list[tuple[int, int, int]]] | None = None,
) -> None:
  writer = cv2.VideoWriter(
    str(path),
    cv2.VideoWriter_fourcc(*"mp4v"),
    18.0,
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


class BarbellTrackerTest(unittest.TestCase):
  def _track(self, centers: list[tuple[int, int] | None]) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "barbell.mp4"
      write_video(path, centers)
      pose_frames = [
        pose_frame(index, x=(center[0] / 320 if center else 0.5), y=(center[1] / 240 if center else 0.4))
        for index, center in enumerate(centers)
      ]
      return BarbellTracker().track(
        str(path),
        pose_frames=pose_frames,
        frame_step=1,
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
