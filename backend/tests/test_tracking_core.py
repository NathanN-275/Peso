from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.analysis.tracking_core import (
  BarbellIdentityTracker,
  Detection,
  DetectionFrame,
  NormalizedPoint,
  SquatExerciseResolver,
  TrackingCoreConfig,
  TrackingPrior,
  YoloOnnxObjectDetector,
  detect_tracking_objects,
  run_apache_v1_tracking,
  tracking_core_config_from_env,
)


def frame(index: int, *, time: float, detections: list[Detection]) -> DetectionFrame:
  return DetectionFrame(
    source_frame_index=index,
    time=time,
    detections=tuple(detections),
  )


def collar(x: float, y: float, confidence: float = 0.82) -> Detection:
  return Detection(kind="barbell_collar", confidence=confidence, center=NormalizedPoint(x, y))


class TrackingCoreTest(unittest.TestCase):
  def test_config_defaults_to_legacy(self) -> None:
    with patch.dict(os.environ, {}, clear=True):
      config = tracking_core_config_from_env()

    self.assertEqual(config.core, "legacy")
    self.assertFalse(config.enabled)
    self.assertTrue(config.fallback_to_legacy)
    self.assertEqual(config.yolo_mode, "off")

  def test_config_accepts_apache_v1_fixture_path(self) -> None:
    with patch.dict(
      os.environ,
      {
        "TRACKING_CORE": "apache_v1",
        "TRACKING_CORE_FALLBACK_TO_LEGACY": "false",
        "APACHE_V1_DETECTIONS_PATH": "/tmp/detections.json",
      },
      clear=True,
    ):
      config = tracking_core_config_from_env()

    self.assertEqual(config.core, "apache_v1")
    self.assertTrue(config.enabled)
    self.assertFalse(config.fallback_to_legacy)
    self.assertEqual(str(config.detection_fixture_path), "/tmp/detections.json")

  def test_config_accepts_yolo_shadow_settings(self) -> None:
    with patch.dict(
      os.environ,
      {
        "YOLO_TRACKING_MODE": "shadow",
        "YOLO_TRACKING_MODEL_PATH": "/models/collar-v1.onnx",
        "YOLO_TRACKING_CLASS_NAMES": "barbell_collar,rack_upright,safety_arm",
      },
      clear=True,
    ):
      config = tracking_core_config_from_env()

    self.assertTrue(config.yolo_enabled)
    self.assertEqual(config.yolo_mode, "shadow")
    self.assertEqual(str(config.yolo_model_path), "/models/collar-v1.onnx")
    self.assertEqual(config.yolo_class_names[2], "safety_arm")

  def test_config_accepts_model_version(self) -> None:
    with patch.dict(os.environ, {"YOLO_TRACKING_MODEL_VERSION": "collar-v1.2.0"}, clear=True):
      config = tracking_core_config_from_env()

    self.assertEqual(config.yolo_model_version, "collar-v1.2.0")

  def test_detection_from_pixel_box_maps_to_normalized_center(self) -> None:
    detection = Detection.from_pixel_box(
      kind="barbell_collar",
      confidence=0.9,
      bbox=(90, 40, 110, 60),
      width=200,
      height=100,
    )

    self.assertAlmostEqual(detection.center.x, 0.5)
    self.assertAlmostEqual(detection.center.y, 0.5)
    self.assertEqual(detection.bbox, (0.45, 0.4, 0.55, 0.6))

  def test_barbell_tracker_rejects_hardware_as_barbell(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1"))
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[
        Detection(kind="j_hook", confidence=0.95, center=NormalizedPoint(0.5, 0.5)),
      ]),
      frame(1, time=0.1, detections=[
        Detection(kind="rack_upright", confidence=0.94, center=NormalizedPoint(0.5, 0.52)),
      ]),
    ])

    self.assertEqual(points, [])
    self.assertEqual(diagnostics["hardware_rejection_count"], 2)
    self.assertEqual(diagnostics["source_counts"]["gap"], 2)

  def test_barbell_identity_loss_coasts_then_gaps(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=3, max_coast_frames=2))
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[collar(0.50, 0.40)]),
      frame(1, time=0.1, detections=[collar(0.50, 0.42)]),
      frame(2, time=0.2, detections=[collar(0.50, 0.44)]),
      frame(3, time=0.3, detections=[]),
      frame(4, time=0.4, detections=[]),
      frame(5, time=0.5, detections=[]),
      frame(6, time=0.6, detections=[]),
    ])

    self.assertEqual([point.source for point in points], ["detector_tracklet", "coast", "coast"])
    self.assertEqual(points[-1].identity_state, "coasting")
    self.assertEqual(diagnostics["coasting_count"], 2)
    self.assertGreaterEqual(diagnostics["identity_gap_count"], 1)
    self.assertEqual(diagnostics["source_counts"]["gap"], 2)

  def test_hardware_far_from_collar_does_not_reject_the_collar(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[
        Detection(kind="safety_arm", confidence=0.99, center=NormalizedPoint(0.10, 0.20)),
        collar(0.80, 0.50, confidence=0.70),
      ]),
    ])

    self.assertEqual(len(points), 1)
    self.assertEqual(points[0].object_class, "barbell_collar")
    self.assertEqual(diagnostics["hardware_rejection_count"], 0)

  def test_candidate_association_prefers_predicted_lane_over_high_confidence_distractor(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[collar(0.50, 0.40, confidence=0.8)]),
      frame(1, time=0.1, detections=[
        collar(0.84, 0.78, confidence=0.99),
        collar(0.505, 0.41, confidence=0.64),
      ]),
    ])

    self.assertAlmostEqual(points[-1].point.x, 0.505)
    self.assertEqual(diagnostics["ambiguous_candidate_frame_count"], 1)
    self.assertEqual(diagnostics["rejected_candidate_count"], 1)

  def test_candidate_association_rejects_overlapping_hardware_but_keeps_safe_collar(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[
        Detection(
          kind="barbell_collar",
          confidence=0.96,
          center=NormalizedPoint(0.30, 0.50),
          bbox=(0.27, 0.47, 0.33, 0.53),
        ),
        Detection(
          kind="j_hook",
          confidence=0.99,
          center=NormalizedPoint(0.30, 0.50),
          bbox=(0.28, 0.45, 0.34, 0.55),
        ),
        Detection(
          kind="barbell_collar",
          confidence=0.70,
          center=NormalizedPoint(0.75, 0.50),
          bbox=(0.72, 0.47, 0.78, 0.53),
        ),
      ]),
    ])

    self.assertAlmostEqual(points[0].point.x, 0.75)
    self.assertEqual(diagnostics["hardware_rejection_count"], 1)

  def test_reference_pin_is_emitted_exactly_when_detector_is_nearby(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    points, _ = tracker.track(
      [frame(12, time=0.4, detections=[collar(0.51, 0.41, confidence=0.70)])],
      priors_by_frame={
        12: TrackingPrior(
          name="barbell",
          center=NormalizedPoint(0.50, 0.40),
          confidence=1.0,
          source="reference",
        )
      },
    )

    self.assertEqual(points[0].point, NormalizedPoint(0.50, 0.40))
    self.assertEqual(points[0].tracking_state, "reference")
    self.assertEqual(points[0].source, "reference_pin")

  def test_reference_pin_is_emitted_exactly_without_detector_output(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=3))
    points, _ = tracker.track(
      [frame(12, time=0.4, detections=[])],
      priors_by_frame={
        12: TrackingPrior(
          name="barbell",
          center=NormalizedPoint(0.50, 0.40),
          confidence=1.0,
          source="reference_pin",
        )
      },
    )

    self.assertEqual(len(points), 1)
    self.assertEqual(points[0].point, NormalizedPoint(0.50, 0.40))
    self.assertEqual(points[0].tracking_state, "reference")

  def test_reacquire_requires_three_trusted_collar_frames(self) -> None:
    tracker = BarbellIdentityTracker(
      TrackingCoreConfig(
        core="apache_v1",
        initial_lock_frames=1,
        reacquire_frames=3,
        max_coast_frames=1,
        max_coast_seconds=0.05,
      )
    )
    points, diagnostics = tracker.track([
      frame(0, time=0.0, detections=[collar(0.50, 0.40)]),
      frame(1, time=0.1, detections=[]),
      frame(2, time=0.2, detections=[]),
      frame(3, time=0.3, detections=[collar(0.50, 0.41)]),
      frame(4, time=0.4, detections=[collar(0.50, 0.42)]),
      frame(5, time=0.5, detections=[collar(0.50, 0.43)]),
    ])

    self.assertEqual([point.time for point in points], [0.0, 0.1, 0.5])
    self.assertEqual(points[-1].identity_state, "locked")
    self.assertEqual(diagnostics["reacquire_count"], 1)
    self.assertEqual(diagnostics["source_counts"]["pending_lock"], 2)

  def test_pin_prior_boosts_detector_but_stale_prior_cannot_create_track(self) -> None:
    tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    points, _ = tracker.track(
      [frame(0, time=0.0, detections=[collar(0.50, 0.40, confidence=0.46)])],
      priors_by_frame={
        0: TrackingPrior(
          name="barbell",
          center=NormalizedPoint(0.505, 0.405),
          confidence=0.88,
        )
      },
    )

    self.assertEqual(points[0].source, "detector_pin_prior")
    self.assertAlmostEqual(points[0].confidence, 0.88)

    stale_tracker = BarbellIdentityTracker(TrackingCoreConfig(core="apache_v1", initial_lock_frames=1))
    stale_points, stale_diagnostics = stale_tracker.track(
      [frame(0, time=0.0, detections=[])],
      priors_by_frame={
        0: TrackingPrior(
          name="barbell",
          center=NormalizedPoint(0.50, 0.40),
          confidence=0.9,
          stale=True,
        )
      },
    )

    self.assertEqual(stale_points, [])
    self.assertEqual(stale_diagnostics["source_counts"]["gap"], 1)

  def test_squat_resolver_marks_low_confidence_pin_as_visual_only(self) -> None:
    resolver = SquatExerciseResolver(min_visibility=0.25)
    points = resolver.resolve_frame(
      {
        "left_shoulder": {"x": 0.40, "y": 0.20, "visibility": 0.1},
        "left_hip": {"x": 0.42, "y": 0.50, "visibility": 0.9},
        "left_knee": {"x": 0.45, "y": 0.70, "visibility": 0.9},
        "left_ankle": {"x": 0.46, "y": 0.90, "visibility": 0.9},
      },
      selected_side="left",
      priors={
        "upper_back": TrackingPrior(
          name="upper_back",
          center=NormalizedPoint(0.39, 0.22),
          confidence=0.8,
          stale=True,
        )
      },
    )

    upper_back = next(point for point in points if point.name == "upper_back")
    self.assertTrue(upper_back.visual_only)
    self.assertFalse(upper_back.chain_valid)
    self.assertEqual(upper_back.accepted_source, "gap")

  def test_fixture_detector_runs_apache_result_shape(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      fixture_path = Path(temp_dir) / "detections.json"
      fixture_path.write_text(
        json.dumps({
          "frames": [
            {"source_frame_index": 0, "time": 0.0, "detections": [{"kind": "barbell_collar", "confidence": 0.9, "center": {"x": 0.5, "y": 0.4}}]},
            {"source_frame_index": 1, "time": 0.1, "detections": [{"kind": "barbell_collar", "confidence": 0.9, "center": {"x": 0.5, "y": 0.42}}]},
            {"source_frame_index": 2, "time": 0.2, "detections": [{"kind": "barbell_collar", "confidence": 0.9, "center": {"x": 0.5, "y": 0.44}}]},
          ]
        }),
        encoding="utf-8",
      )
      result = run_apache_v1_tracking(
        video_path="/tmp/source.mov",
        pose_frames=[],
        processed_width=200,
        processed_height=100,
        manual_barbell_priors=None,
        config=TrackingCoreConfig(core="apache_v1", detection_fixture_path=fixture_path),
      )

    self.assertTrue(result["barbellPath"]["available"])
    self.assertEqual(result["diagnostics"]["tracking_core"], "apache_v1")
    self.assertEqual(result["diagnostics"]["object_detector"], "fixture_detector")
    self.assertEqual(len(result["barbellPath"]["points"]), 1)

  def test_fixture_prepass_uses_only_pose_sampled_source_frames(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      fixture_path = Path(temp_dir) / "detections.json"
      fixture_path.write_text(json.dumps({
        "frames": [
          {"source_frame_index": 2, "time": 0.1, "detections": []},
          {"source_frame_index": 4, "time": 0.2, "detections": []},
        ]
      }), encoding="utf-8")
      frames, diagnostics = detect_tracking_objects(
        video_path="/tmp/source.mov",
        pose_frames=[{"source_frame_index": 4, "timestamp_ms": 220}],
        processed_width=200,
        processed_height=100,
        config=TrackingCoreConfig(
          yolo_mode="shadow",
          detection_fixture_path=fixture_path,
        ),
      )

    self.assertEqual([frame.source_frame_index for frame in frames], [4])
    self.assertEqual(frames[0].time, 0.22)
    self.assertEqual(diagnostics["detection_frame_count"], 1)

  def test_missing_yolo_artifact_fails_open_with_diagnostics(self) -> None:
    frames, diagnostics = detect_tracking_objects(
      video_path="/tmp/source.mov",
      pose_frames=[{"source_frame_index": 0, "timestamp_ms": 0}],
      processed_width=200,
      processed_height=100,
      config=TrackingCoreConfig(
        yolo_mode="shadow",
        yolo_model_path=Path("/missing/collar-v1.onnx"),
        yolo_class_names=("barbell_collar",),
      ),
    )

    self.assertEqual(frames, [])
    self.assertEqual(diagnostics["failure_reason"], "detector_error")

  def test_yolo_decoder_maps_custom_class_scores_to_boxes(self) -> None:
    detector = YoloOnnxObjectDetector.__new__(YoloOnnxObjectDetector)
    detector.class_names = ("barbell_collar", "rack_upright", "safety_arm")
    detector.confidence_threshold = 0.45
    boxes, scores, class_ids = detector._decode_output(np.array([
      [320.0, 320.0, 40.0, 20.0, 0.92, 0.04, 0.02],
    ], dtype=np.float32))

    self.assertEqual(boxes, [[300, 310, 40, 20]])
    self.assertEqual(class_ids, [0])
    self.assertAlmostEqual(scores[0], 0.92)

  def test_benchmark_manifest_declares_required_classes_and_thresholds(self) -> None:
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "tracking_core"
    schema = json.loads((fixture_dir / "label_schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((fixture_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))

    self.assertEqual(schema["license_policy"], "apache_mit_compatible")
    self.assertIn("barbell_collar", schema["object_classes"])
    self.assertIn("rack_upright", schema["object_classes"])
    self.assertIn("j_hook", schema["object_classes"])
    self.assertIn("safety_arm", schema["object_classes"])
    self.assertIn("upper_back", schema["keypoints"])
    self.assertEqual(manifest["tracking_core"], "apache_v1")
    self.assertEqual(manifest["local_regression_manifest_template"], "source_video_regression_manifest.example.json")
    self.assertEqual(manifest["thresholds"]["hardware_identity_switches"], 0)
    self.assertIn("direct_side_pinned", manifest["required_clip_categories"])
    self.assertEqual(manifest["promotion_requirements"]["minimum_independent_source_videos"], 10)


if __name__ == "__main__":
  unittest.main()
