from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.analysis.manual_tracking import (
  BODY_ANCHORS,
  fuse_manual_body_tracks,
  select_manual_tracking_side,
  track_manual_anchors,
  validate_tracking_setup,
)
from app.analysis.pipeline import _apply_tracking_assistance, _attach_barbell_tracking
from app.analysis.barbell_tracking.tracker import BarbellTracker
from app.services.video_repository import VIDEO_STORAGE_COLUMNS


def tracking_setup() -> dict:
  return {
    "version": 1,
    "reference_time_ms": 100,
    "barbell_target": "near_side_collar",
    "anchors": {
      "shoulder": {"x": 0.35, "y": 0.25},
      "hip": {"x": 0.36, "y": 0.45},
      "knee": {"x": 0.38, "y": 0.64},
      "ankle": {"x": 0.40, "y": 0.84},
      "barbell": {"x": 0.50, "y": 0.27},
    },
  }


def pose_frame(source_index: int = 1) -> dict:
  landmarks = {}
  for side, offset in (("left", 0.0), ("right", 0.30)):
    for joint, point in tracking_setup()["anchors"].items():
      if joint == "barbell":
        continue
      landmarks[f"{side}_{joint}"] = {
        "x": point["x"] + offset,
        "y": point["y"],
        "z": 0.0,
        "visibility": 0.8,
      }
  return {
    "source_frame_index": source_index,
    "timestamp_ms": source_index * 100,
    "landmarks": landmarks,
  }


class ManualTrackingTest(unittest.TestCase):
  def test_img0012_regression_fixture_has_complete_ordered_labels(self) -> None:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "manual_tracking_img0012_reference.json"
    fixture = json.loads(fixture_path.read_text())

    self.assertEqual(fixture["video"], "IMG_0012.MOV")
    self.assertEqual(len(fixture["labels"]), 4)
    self.assertEqual(fixture["reference_time_ms"], fixture["labels"][0]["time_ms"])
    width = fixture["coordinate_space"]["width"]
    height = fixture["coordinate_space"]["height"]
    for label in fixture["labels"]:
      anchors = label["anchors"]
      self.assertEqual(set(anchors), {*BODY_ANCHORS, "barbell"})
      self.assertLess(anchors["shoulder"][1], anchors["hip"][1])
      self.assertLess(anchors["hip"][1], anchors["knee"][1])
      self.assertLess(anchors["knee"][1], anchors["ankle"][1])
      for x, y in anchors.values():
        self.assertGreaterEqual(x, 0)
        self.assertLessEqual(x, width)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y, height)

  def test_validate_tracking_setup_accepts_complete_payload(self) -> None:
    validated, error = validate_tracking_setup(tracking_setup(), duration_ms=1000)

    self.assertIsNone(error)
    self.assertEqual(validated["anchors"]["barbell"]["x"], 0.5)

  def test_validate_tracking_setup_rejects_missing_and_misordered_points(self) -> None:
    missing = tracking_setup()
    del missing["anchors"]["knee"]
    self.assertEqual(validate_tracking_setup(missing)[1], "missing_knee_anchor")

    misordered = tracking_setup()
    misordered["anchors"]["hip"]["y"] = 0.1
    self.assertEqual(validate_tracking_setup(misordered)[1], "invalid_body_anchor_order")

  def test_select_side_uses_chain_closest_to_manual_anchors(self) -> None:
    self.assertEqual(
      select_manual_tracking_side(pose_frame(), tracking_setup()["anchors"]),
      "left",
    )

  def test_fusion_blends_reliable_tracks_into_selected_side_only(self) -> None:
    frame = pose_frame()
    original_right_hip = frame["landmarks"]["right_hip"]["x"]
    tracks = {
      joint: {
        1: {
          "x": tracking_setup()["anchors"][joint]["x"] + 0.02,
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
        }
      }
      for joint in BODY_ANCHORS
    }

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    self.assertTrue(diagnostics["used"])
    self.assertEqual(diagnostics["selected_side"], "left")
    self.assertEqual(diagnostics["fused_landmark_count"], 4)
    self.assertTrue(fused[0]["landmarks"]["left_hip"]["manual_assisted"])
    self.assertEqual(
      fused[0]["landmarks"]["left_hip"]["x"],
      tracks["hip"][1]["x"],
    )
    self.assertEqual(diagnostics["directly_anchored_landmark_count"], 4)
    self.assertEqual(fused[0]["landmarks"]["right_hip"]["x"], original_right_hip)

  def test_fusion_requires_two_valid_frames_before_manual_reentry(self) -> None:
    frames = [pose_frame(index) for index in (1, 2, 3, 4)]
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + (index * 0.01),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
        }
        for index in (1, 3, 4)
      }
      for joint in BODY_ANCHORS
    }
    automatic_frame_three_hip = frames[2]["landmarks"]["left_hip"]["x"]

    fused, _ = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    self.assertTrue(fused[0]["landmarks"]["left_hip"]["manual_assisted"])
    self.assertNotIn("manual_assisted", fused[1]["landmarks"]["left_hip"])
    self.assertEqual(fused[2]["landmarks"]["left_hip"]["x"], automatic_frame_three_hip)
    self.assertNotIn("manual_assisted", fused[2]["landmarks"]["left_hip"])
    self.assertTrue(fused[3]["landmarks"]["left_hip"]["manual_assisted"])

  def test_tracks_anchors_forward_and_backward_from_reference_frame(self) -> None:
    width, height, fps = 160, 120, 10.0
    with tempfile.TemporaryDirectory() as directory:
      video_path = Path(directory) / "manual-tracking.avi"
      writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
      )
      self.assertTrue(writer.isOpened())
      base_points = {
        "shoulder": (56, 30),
        "hip": (58, 54),
        "knee": (61, 77),
        "ankle": (64, 101),
        "barbell": (80, 32),
      }
      for frame_index in range(3):
        image = np.zeros((height, width, 3), dtype=np.uint8)
        for point in base_points.values():
          center = (point[0] + (frame_index * 3), point[1] + frame_index)
          cv2.rectangle(image, (center[0] - 4, center[1] - 4), (center[0] + 4, center[1] + 4), (255, 255, 255), 1)
          cv2.line(image, (center[0] - 5, center[1]), (center[0] + 5, center[1]), (255, 255, 255), 1)
          cv2.line(image, (center[0], center[1] - 5), (center[0], center[1] + 5), (255, 255, 255), 1)
        writer.write(image)
      writer.release()

      setup = tracking_setup()
      setup["anchors"] = {
        name: {"x": (point[0] + 3) / width, "y": (point[1] + 1) / height}
        for name, point in base_points.items()
      }
      result = track_manual_anchors(
        str(video_path),
        setup=setup,
        pose_frames=[pose_frame(0), pose_frame(1), pose_frame(2)],
        fps=fps,
        width=width,
        height=height,
      )

    self.assertEqual(result["reference_source_index"], 1)
    for name in setup["anchors"]:
      self.assertEqual(set(result["tracks"][name]), {0, 1, 2})
      self.assertGreaterEqual(result["coverage"][name], 0.99)

  def test_pipeline_fails_open_when_tracking_setup_is_invalid(self) -> None:
    invalid_setup = tracking_setup()
    invalid_setup["version"] = 99
    estimation = {
      "duration_ms": 1000,
      "frames": [pose_frame()],
      "fps": 10.0,
      "processed_frame_width": 160,
      "processed_frame_height": 120,
    }

    assisted = _apply_tracking_assistance(
      file_path="unused.mov",
      video={"id": "video-1", "tracking_setup": invalid_setup},
      estimation=estimation,
    )

    self.assertEqual(assisted["tracking_assistance"]["actualMode"], "automatic_fallback")
    self.assertEqual(assisted["tracking_assistance"]["fallbackReason"], "unsupported_tracking_setup_version")
    self.assertEqual(assisted["frames"], estimation["frames"])

  def test_pipeline_marks_valid_fusion_as_pin_assisted(self) -> None:
    estimation = {
      "duration_ms": 1000,
      "frames": [pose_frame()],
      "fps": 10.0,
      "processed_frame_width": 160,
      "processed_frame_height": 120,
    }
    tracked = {
      "tracks": {
        joint: {1: {**tracking_setup()["anchors"][joint], "confidence": 0.9}}
        for joint in (*BODY_ANCHORS, "barbell")
      },
      "reference_source_index": 1,
      "coverage": {joint: 1.0 for joint in (*BODY_ANCHORS, "barbell")},
    }

    with patch("app.analysis.pipeline.track_manual_anchors", return_value=tracked):
      assisted = _apply_tracking_assistance(
        file_path="unused.mov",
        video={"id": "video-1", "tracking_setup": tracking_setup()},
        estimation=estimation,
      )

    self.assertEqual(assisted["tracking_assistance"]["actualMode"], "pin_assisted")
    self.assertTrue(assisted["tracking_assistance"]["used"])

  def test_pipeline_marks_manual_collar_points_as_pin_assisted(self) -> None:
    tracker = BarbellTracker()
    tracker.manual_seed_count = 3
    tracker.manual_point_count = 3
    tracker.automatic_point_count = 2
    tracker.track = lambda *args, **kwargs: {
      "barbellPath": {"available": True, "coverage": 1.0, "points": []},
      "diagnostics": {"manual_point_count": 3, "automatic_point_count": 2},
    }
    result = {
      "reps": [],
      "trackingAssistance": {
        "requestedMode": "pins",
        "actualMode": "automatic_fallback",
        "used": False,
        "fallbackReason": "manual_tracks_unavailable",
      },
    }

    with patch("app.analysis.pipeline.BarbellTracker", return_value=tracker):
      _attach_barbell_tracking(
        result=result,
        video={"id": "video-1", "exercise_type": "squat", "view_type": "side"},
        file_path="unused.mov",
        estimation={"frames": [], "frame_step": 1, "manual_tracking": {"tracks": {}}},
      )

    assistance = result["trackingAssistance"]
    self.assertEqual(assistance["actualMode"], "pin_assisted")
    self.assertTrue(assistance["used"])
    self.assertEqual(assistance["manualBarbellPointCount"], 3)
    self.assertEqual(assistance["automaticBarbellPointCount"], 2)
    self.assertIsNone(assistance["fallbackReason"])

  def test_barbell_prior_must_be_confident_and_inside_pose_region(self) -> None:
    self.assertTrue(BarbellTracker._manual_prior_is_plausible(
      {"x": 0.5, "y": 0.25, "confidence": 0.9},
      bounds=(20, 10, 140, 70),
      shoulder=(60, 32),
      width=160,
      height=120,
    ))
    self.assertFalse(BarbellTracker._manual_prior_is_plausible(
      {"x": 0.95, "y": 0.95, "confidence": 0.9},
      bounds=(20, 10, 140, 70),
      shoulder=(60, 32),
      width=160,
      height=120,
    ))

  def test_repository_reads_tracking_setup(self) -> None:
    self.assertIn("tracking_setup", VIDEO_STORAGE_COLUMNS)


if __name__ == "__main__":
  unittest.main()
