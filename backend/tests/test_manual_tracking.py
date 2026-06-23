from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.analysis.manual_tracking import (
  BODY_ANCHORS,
  fuse_manual_body_tracks,
  select_reference_source_index,
  select_manual_tracking_side,
  track_manual_anchors,
  validate_tracking_setup,
)
from app.analysis.pipeline import (
  _apply_tracking_assistance,
  _attach_barbell_tracking,
  _barbell_pose_frames_with_upper_back_context,
)
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

  def test_reference_frame_uses_decoded_timestamps_before_nominal_fps(self) -> None:
    frames = [
      {"source_frame_index": 0, "timestamp_ms": 0},
      {"source_frame_index": 4, "timestamp_ms": 180},
      {"source_frame_index": 8, "timestamp_ms": 410},
    ]

    self.assertEqual(
      select_reference_source_index(frames, reference_time_ms=390, fps=10.0),
      8,
    )

  def test_fusion_uses_reliable_body_pins_on_selected_side_only(self) -> None:
    frame = pose_frame()
    original_right_hip = frame["landmarks"]["right_hip"]["x"]
    original_left_shoulder = dict(frame["landmarks"]["left_shoulder"])
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
    self.assertEqual(diagnostics["fused_landmark_count"], 3)
    self.assertEqual(diagnostics["upper_back_anchor_semantics"], "upper_back_anchor")
    self.assertEqual(diagnostics["upper_back_anchor_used_count"], 1)
    self.assertTrue(fused[0]["landmarks"]["left_hip"]["manual_assisted"])
    self.assertEqual(
      fused[0]["landmarks"]["left_hip"]["x"],
      tracks["hip"][1]["x"],
    )
    self.assertEqual(diagnostics["directly_anchored_landmark_count"], 3)
    self.assertEqual(fused[0]["landmarks"]["right_hip"]["x"], original_right_hip)
    self.assertEqual(fused[0]["landmarks"]["left_shoulder"]["x"], original_left_shoulder["x"])
    self.assertNotIn("manual_assisted", fused[0]["landmarks"]["left_shoulder"])

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
    self.assertEqual(fused[1]["landmarks"]["left_hip"]["tracking_state"], "estimated")
    self.assertEqual(fused[1]["landmarks"]["left_hip"]["manual_source"], "pin_estimated")
    self.assertTrue(fused[1]["landmarks"]["left_hip"]["user_pinned"])
    self.assertEqual(fused[2]["landmarks"]["left_hip"]["x"], automatic_frame_three_hip)
    self.assertNotIn("manual_assisted", fused[2]["landmarks"]["left_hip"])
    self.assertTrue(fused[3]["landmarks"]["left_hip"]["manual_assisted"])

  def test_fusion_rejects_one_joint_drift_without_disabling_valid_joints(self) -> None:
    frame = pose_frame(2)
    tracks = {
      joint: {
        2: {
          "x": tracking_setup()["anchors"][joint]["x"] + (0.28 if joint == "hip" else 0.01),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.95,
        }
      }
      for joint in BODY_ANCHORS
    }
    original_hip = dict(frame["landmarks"]["left_hip"])

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    self.assertEqual(fused[0]["landmarks"]["left_hip"]["x"], original_hip["x"])
    self.assertEqual(fused[0]["landmarks"]["left_hip"]["y"], original_hip["y"])
    self.assertEqual(fused[0]["landmarks"]["left_hip"]["tracking_state"], "automatic")
    self.assertNotIn("manual_assisted", fused[0]["landmarks"]["left_hip"])
    self.assertNotIn("manual_assisted", fused[0]["landmarks"]["left_shoulder"])
    self.assertGreaterEqual(diagnostics["rejected_track_count"], 1)
    self.assertGreaterEqual(diagnostics["fallback_landmark_count"], 1)
    self.assertGreaterEqual(diagnostics["blended_landmark_count"], 1)

  def test_upper_back_pin_does_not_overwrite_anatomical_shoulder(self) -> None:
    frame = pose_frame(1)
    original_shoulder = dict(frame["landmarks"]["left_shoulder"])
    tracks = {
      joint: {
        1: {
          "x": tracking_setup()["anchors"][joint]["x"] + (0.18 if joint == "shoulder" else 0.0),
          "y": tracking_setup()["anchors"][joint]["y"] + (0.10 if joint == "shoulder" else 0.0),
          "confidence": 0.95,
          "tracking_state": "reference",
        }
      }
      for joint in BODY_ANCHORS
    }

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {"shoulder": 1.0}},
    )

    self.assertEqual(fused[0]["landmarks"]["left_shoulder"]["x"], original_shoulder["x"])
    self.assertEqual(fused[0]["landmarks"]["left_shoulder"]["y"], original_shoulder["y"])
    self.assertNotIn("manual_assisted", fused[0]["landmarks"]["left_shoulder"])
    self.assertEqual(diagnostics["upper_back_anchor_used_count"], 1)
    self.assertEqual(diagnostics["body_pin_frames"][0]["upper_back_source"], "reference")

  def test_upper_back_pin_emits_separate_overlay_landmark(self) -> None:
    frame = pose_frame(1)
    original_shoulder = dict(frame["landmarks"]["left_shoulder"])
    tracks = {
      joint: {
        1: {
          **tracking_setup()["anchors"][joint],
          "confidence": 0.91,
          "tracking_state": "guided",
        }
      }
      for joint in BODY_ANCHORS
    }
    tracks["shoulder"][1].update({"x": 0.52, "y": 0.34})

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 0, "coverage": {"shoulder": 1.0}},
    )

    landmarks = fused[0]["landmarks"]
    self.assertEqual(landmarks["left_shoulder"]["x"], original_shoulder["x"])
    self.assertEqual(landmarks["left_shoulder"]["y"], original_shoulder["y"])
    self.assertIn("left_upper_back", landmarks)
    self.assertAlmostEqual(landmarks["left_upper_back"]["x"], 0.52)
    self.assertAlmostEqual(landmarks["left_upper_back"]["y"], 0.34)
    self.assertEqual(landmarks["left_upper_back"]["tracking_state"], "guided")
    self.assertEqual(landmarks["left_upper_back"]["manual_source"], "pin_guided")
    self.assertEqual(diagnostics["source_counts"]["upper_back"]["pin_guided"], 1)

  def test_valid_knee_pin_is_not_dragged_to_bad_automatic_pose(self) -> None:
    frame = pose_frame(2)
    frame["landmarks"]["left_knee"].update({"x": 0.63, "y": 0.53, "visibility": 0.82})
    tracks = {
      joint: {
        2: {
          **tracking_setup()["anchors"][joint],
          "confidence": 0.92,
          "tracking_state": "guided",
        }
      }
      for joint in BODY_ANCHORS
    }

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    knee = fused[0]["landmarks"]["left_knee"]
    self.assertAlmostEqual(knee["x"], tracking_setup()["anchors"]["knee"]["x"])
    self.assertAlmostEqual(knee["y"], tracking_setup()["anchors"]["knee"]["y"])
    self.assertTrue(knee["manual_assisted"])
    self.assertEqual(knee["manual_weight"], 1.0)
    self.assertEqual(diagnostics["model_divergence_accepted_count"], 1)

  def test_recent_knee_pin_dropout_estimates_instead_of_accepting_bad_model_knee(self) -> None:
    frames = [pose_frame(index) for index in (1, 2, 3)]
    frames[1]["landmarks"]["left_knee"].update({"x": 0.52, "y": 0.60, "visibility": 0.88})
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + ((index - 1) * 0.01),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
          "tracking_state": "guided",
        }
        for index in (1, 2, 3)
      }
      for joint in BODY_ANCHORS
    }
    del tracks["knee"][2]

    fused, diagnostics = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    knee = fused[1]["landmarks"]["left_knee"]
    self.assertEqual(knee["tracking_state"], "estimated")
    self.assertAlmostEqual(knee["x"], 0.39)
    self.assertAlmostEqual(knee["y"], tracking_setup()["anchors"]["knee"]["y"])
    self.assertNotAlmostEqual(knee["x"], 0.52)
    self.assertEqual(diagnostics["source_counts"]["knee"]["pin_estimated"], 1)
    self.assertEqual(diagnostics["rejection_reasons"]["pin_track_missing_recent"], 1)

  def test_velocity_capped_knee_pin_is_not_rendered_as_guided(self) -> None:
    frames = [pose_frame(index) for index in (1, 2, 3)]
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + ((index - 1) * 0.03),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
          "tracking_state": "guided",
        }
        for index in (1, 2, 3)
      }
      for joint in BODY_ANCHORS
    }
    tracks["knee"][2] = {
      **tracking_setup()["anchors"]["knee"],
      "confidence": 0.9,
      "tracking_state": "guided",
      "velocity_cap_reused_previous": 1.0,
      "stale_track": 1.0,
    }
    tracks["knee"][3].update({"x": 0.50})

    fused, diagnostics = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    knee = fused[1]["landmarks"]["left_knee"]
    self.assertEqual(knee["tracking_state"], "estimated")
    self.assertNotIn("manual_assisted", knee)
    self.assertAlmostEqual(knee["x"], tracking_setup()["anchors"]["knee"]["x"] + 0.03)
    self.assertEqual(diagnostics["source_counts"]["knee"]["stale_pin_rejected"], 1)
    self.assertEqual(diagnostics["source_counts"]["knee"]["pin_estimated"], 1)

  def test_short_knee_dropout_estimates_from_hip_ankle_motion_without_following_chain(self) -> None:
    frames = [pose_frame(index) for index in (1, 2)]
    frames[1]["landmarks"]["left_knee"].update({"x": 0.60, "y": 0.54, "visibility": 0.88})
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + (0.04 if index == 2 else 0.0),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
          "tracking_state": "guided",
        }
        for index in (1, 2)
      }
      for joint in BODY_ANCHORS
    }
    del tracks["knee"][2]

    fused, diagnostics = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    knee = fused[1]["landmarks"]["left_knee"]
    self.assertEqual(knee["tracking_state"], "estimated")
    self.assertAlmostEqual(knee["x"], tracking_setup()["anchors"]["knee"]["x"] + 0.04)
    self.assertNotAlmostEqual(knee["x"], tracking_setup()["anchors"]["knee"]["x"])
    self.assertLessEqual(knee["visibility"], 0.48)
    self.assertEqual(diagnostics["source_counts"]["knee"]["pin_estimated"], 1)

  def test_long_knee_dropout_keeps_visual_fallback_without_accepting_pin(self) -> None:
    frames = [pose_frame(index) for index in (1, 2, 3, 4)]
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + ((index - 1) * 0.03),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
          "tracking_state": "guided",
        }
        for index in (1, 2, 3, 4)
      }
      for joint in BODY_ANCHORS
    }
    for index in (2, 3, 4):
      del tracks["knee"][index]

    fused, diagnostics = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    knee = fused[3]["landmarks"]["left_knee"]
    self.assertNotEqual(knee.get("manual_source"), "pin_estimated")
    self.assertNotEqual(knee.get("accepted_source"), "pin_estimated")
    self.assertEqual(knee["visual_fallback"]["manual_source"], "pin_visual_fallback")
    self.assertTrue(knee["visual_fallback"]["user_pinned"])
    self.assertGreaterEqual(knee["visual_fallback"]["confidence"], 0.15)
    self.assertGreaterEqual(diagnostics["source_counts"]["knee"]["pin_visual_fallback"], 1)

  def test_upper_back_long_dropout_uses_automatic_proxy_instead_of_stale_pin(self) -> None:
    frames = [pose_frame(index) for index in (1, 2, 3, 4)]
    tracks = {
      joint: {
        index: {
          "x": tracking_setup()["anchors"][joint]["x"] + ((index - 1) * 0.02),
          "y": tracking_setup()["anchors"][joint]["y"],
          "confidence": 0.9,
          "tracking_state": "guided",
        }
        for index in (1, 2, 3, 4)
      }
      for joint in BODY_ANCHORS
    }
    for index in (2, 3, 4):
      del tracks["shoulder"][index]

    fused, diagnostics = fuse_manual_body_tracks(
      frames,
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    upper_back = fused[3]["landmarks"]["left_upper_back"]
    self.assertEqual(upper_back["tracking_state"], "automatic")
    self.assertEqual(upper_back["manual_source"], "automatic")
    self.assertFalse(upper_back["user_pinned"])
    self.assertEqual(upper_back["accepted_source"], "automatic")
    self.assertEqual(diagnostics["source_counts"]["upper_back"]["automatic"], 3)

  def test_barbell_context_uses_upper_back_without_mutating_public_pose_frames(self) -> None:
    frame = pose_frame(1)
    original_shoulder = dict(frame["landmarks"]["left_shoulder"])
    contextual_frames, count = _barbell_pose_frames_with_upper_back_context(
      [frame],
      manual_tracking={
        "tracks": {
          "shoulder": {
            1: {"x": 0.51, "y": 0.33, "confidence": 0.88},
          },
        },
      },
      selected_side="left",
    )

    self.assertEqual(count, 1)
    self.assertEqual(frame["landmarks"]["left_shoulder"]["x"], original_shoulder["x"])
    contextual_shoulder = contextual_frames[0]["landmarks"]["left_shoulder"]
    self.assertEqual(contextual_shoulder["x"], 0.51)
    self.assertEqual(contextual_shoulder["y"], 0.33)
    self.assertTrue(contextual_shoulder["upper_back_context"])

  def test_fusion_selects_a_valid_complete_chain_when_automatic_ankle_is_inverted(self) -> None:
    frame = pose_frame(2)
    frame["landmarks"]["left_ankle"].update({"x": 0.40, "y": 0.58, "visibility": 0.12})
    tracks = {
      joint: {
        2: {
          **tracking_setup()["anchors"][joint],
          "confidence": 0.95,
        }
      }
      for joint in BODY_ANCHORS
    }

    fused, diagnostics = fuse_manual_body_tracks(
      [frame],
      setup=tracking_setup(),
      tracking={"tracks": tracks, "reference_source_index": 1, "coverage": {}},
    )

    landmarks = fused[0]["landmarks"]
    self.assertGreater(landmarks["left_ankle"]["y"], landmarks["left_knee"]["y"])
    self.assertEqual(landmarks["left_ankle"]["tracking_state"], "guided")
    self.assertEqual(diagnostics["selected_side"], "left")

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

  def test_knee_tracking_scales_motion_cap_across_sampled_frames(self) -> None:
    width, height, fps = 180, 140, 30.0
    with tempfile.TemporaryDirectory() as directory:
      video_path = Path(directory) / "fast-knee-tracking.avi"
      writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
      )
      self.assertTrue(writer.isOpened())
      stable_points = {
        "shoulder": (55, 30),
        "hip": (58, 55),
        "ankle": (66, 112),
        "barbell": (92, 32),
      }
      knee_positions = {
        0: (60, 82),
        4: (91, 84),
        8: (137, 86),
      }
      for frame_index in range(9):
        image = np.zeros((height, width, 3), dtype=np.uint8)
        if frame_index <= 4:
          ratio = frame_index / 4
          start = knee_positions[0]
          end = knee_positions[4]
        else:
          ratio = (frame_index - 4) / 4
          start = knee_positions[4]
          end = knee_positions[8]
        knee_center = (
          int(round(start[0] + ((end[0] - start[0]) * ratio))),
          int(round(start[1] + ((end[1] - start[1]) * ratio))),
        )
        for point in stable_points.values():
          cv2.rectangle(image, (point[0] - 5, point[1] - 5), (point[0] + 5, point[1] + 5), (90, 90, 90), 1)
          cv2.line(image, (point[0] - 6, point[1]), (point[0] + 6, point[1]), (90, 90, 90), 1)
          cv2.line(image, (point[0], point[1] - 6), (point[0], point[1] + 6), (90, 90, 90), 1)
        cv2.circle(image, knee_center, 6, (255, 255, 255), -1)
        cv2.circle(image, knee_center, 2, (130, 130, 130), -1)
        writer.write(image)
      writer.release()

      setup = tracking_setup()
      setup["reference_time_ms"] = 0
      setup["anchors"] = {
        "shoulder": {"x": stable_points["shoulder"][0] / width, "y": stable_points["shoulder"][1] / height},
        "hip": {"x": stable_points["hip"][0] / width, "y": stable_points["hip"][1] / height},
        "knee": {"x": knee_positions[0][0] / width, "y": knee_positions[0][1] / height},
        "ankle": {"x": stable_points["ankle"][0] / width, "y": stable_points["ankle"][1] / height},
        "barbell": {"x": stable_points["barbell"][0] / width, "y": stable_points["barbell"][1] / height},
      }
      result = track_manual_anchors(
        str(video_path),
        setup=setup,
        pose_frames=[pose_frame(0), pose_frame(4), pose_frame(8)],
        fps=fps,
        width=width,
        height=height,
      )

    knee = result["tracks"]["knee"][8]
    self.assertNotIn("velocity_cap_reused_previous", knee)
    self.assertGreater(knee["confidence"], 0.5)
    self.assertGreater(knee["x"] * width, 120)
    self.assertEqual(result["velocity_cap_counts"]["knee"], 0)

  def test_img0012_video_tracking_stays_near_labeled_reference_points(self) -> None:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "manual_tracking_img0012_reference.json"
    fixture = json.loads(fixture_path.read_text())
    video_path = Path(__file__).resolve().parent.parent / "test_videos" / fixture["video"]
    width = fixture["coordinate_space"]["width"]
    height = fixture["coordinate_space"]["height"]
    fps = fixture["fps"]
    first_label = fixture["labels"][0]
    setup = {
      "version": 1,
      "reference_time_ms": fixture["reference_time_ms"],
      "barbell_target": "near_side_collar",
      "anchors": {
        name: {"x": point[0] / width, "y": point[1] / height}
        for name, point in first_label["anchors"].items()
      },
    }
    final_index = fixture["labels"][-1]["source_frame_index"]
    source_indices = list(range(0, final_index + 1, 4))
    frames = [
      {"source_frame_index": index, "timestamp_ms": round((index / fps) * 1000)}
      for index in source_indices
    ]

    result = track_manual_anchors(
      str(video_path),
      setup=setup,
      pose_frames=frames,
      fps=fps,
      width=width,
      height=height,
    )

    self.assertEqual(result["reference_source_index"], 0)
    self.assertGreaterEqual(result["coverage"]["hip"], 0.35)
    for name in ("shoulder", "knee", "ankle", "barbell"):
      self.assertGreaterEqual(result["coverage"][name], 0.95)
    for label in fixture["labels"]:
      source_index = min(source_indices, key=lambda index: abs(index - label["source_frame_index"]))
      for name, expected in label["anchors"].items():
        point = result["tracks"].get(name, {}).get(source_index)
        if point is None:
          continue
        error_px = math.hypot(
          (point["x"] * width) - expected[0],
          (point["y"] * height) - expected[1],
        )
        self.assertLessEqual(error_px, fixture["tolerance_px"] * 3)

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
    self.assertIn("blendedLandmarkCount", assisted["tracking_assistance"])
    self.assertIn("fallbackLandmarkCount", assisted["tracking_assistance"])
    self.assertEqual(assisted["tracking_assistance"]["upperBackAnchorSemantics"], "upper_back_anchor")
    self.assertEqual(assisted["tracking_assistance"]["pinOwnedLandmarkCount"], 3)
    self.assertEqual(
      assisted["tracking_assistance"]["reference"],
      {
        "version": 1,
        "timeMs": 100,
        "selectedSide": "left",
        "anchors": tracking_setup()["anchors"],
      },
    )

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

  def test_barbell_tracking_uses_validated_pose_context(self) -> None:
    frames = [pose_frame(index) for index in (0, 1, 2)]
    frames[1]["landmarks"]["left_shoulder"].update({"x": 0.68, "y": 0.36})
    frames[1]["landmarks"]["left_hip"].update({"x": 0.70, "y": 0.58})
    frames[1]["landmarks"]["left_knee"].update({"x": 0.73, "y": 0.70})
    tracker = BarbellTracker()
    tracking_result = {
      "barbellPath": {"available": True, "coverage": 1.0, "points": []},
      "diagnostics": {
        "manual_point_count": 0,
        "automatic_point_count": 3,
        "pose_context_validated": True,
      },
    }
    captured_pose_frames: list[dict] = []

    def capture_track(*args, **kwargs) -> dict:
      captured_pose_frames.extend(kwargs["pose_frames"])
      return tracking_result

    tracker.track = capture_track
    result = {
      "reps": [],
      "diagnostics": {
        "selected_side": "left",
        "pose_validation": {"selected_side": "left"},
      },
    }

    with patch("app.analysis.pipeline.BarbellTracker", return_value=tracker):
      _attach_barbell_tracking(
        result=result,
        video={"id": "video-1", "exercise_type": "squat", "view_type": "side"},
        file_path="unused.mov",
        estimation={"frames": frames, "frame_step": 1, "manual_tracking": {"tracks": {}}},
      )

    self.assertEqual(
      captured_pose_frames[1]["landmarks"]["left_hip"]["tracking_state"],
      "estimated",
    )
    self.assertTrue(result["diagnostics"]["barbell_tracking"]["pose_context_validated"])

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
    self.assertFalse(BarbellTracker._manual_prior_is_plausible(
      {"x": 0.78, "y": 0.25, "confidence": 0.9},
      bounds=(20, 10, 140, 70),
      shoulder=(60, 32),
      previous_point=(80, 30),
      width=160,
      height=120,
    ))
    self.assertFalse(BarbellTracker._manual_prior_is_plausible(
      {"x": 0.68, "y": 0.25, "confidence": 0.9},
      bounds=(20, 10, 140, 70),
      shoulder=(60, 32),
      reference_shoulder_offset=(20, -2),
      width=160,
      height=120,
    ))

  def test_repository_reads_tracking_setup(self) -> None:
    self.assertIn("tracking_setup", VIDEO_STORAGE_COLUMNS)


if __name__ == "__main__":
  unittest.main()
