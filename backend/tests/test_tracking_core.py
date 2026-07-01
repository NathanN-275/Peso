from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.analysis.tracking_core import (
  BarbellIdentityTracker,
  Detection,
  DetectionFrame,
  NormalizedPoint,
  SquatExerciseResolver,
  TrackingCoreConfig,
  TrackingPrior,
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
    ])

    self.assertEqual([point.source for point in points], ["detector_tracklet", "coast", "coast"])
    self.assertEqual(points[-1].identity_state, "coasting")
    self.assertEqual(diagnostics["coasting_count"], 2)
    self.assertGreaterEqual(diagnostics["identity_gap_count"], 1)
    self.assertEqual(diagnostics["source_counts"]["gap"], 1)

  def test_reacquire_requires_three_trusted_collar_frames(self) -> None:
    tracker = BarbellIdentityTracker(
      TrackingCoreConfig(core="apache_v1", initial_lock_frames=1, reacquire_frames=3, max_coast_frames=1)
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

  def test_benchmark_manifest_declares_required_classes_and_thresholds(self) -> None:
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "tracking_core"
    schema = json.loads((fixture_dir / "label_schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((fixture_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))

    self.assertEqual(schema["license_policy"], "apache_mit_compatible")
    self.assertIn("barbell_collar", schema["object_classes"])
    self.assertIn("rack_upright", schema["object_classes"])
    self.assertIn("j_hook", schema["object_classes"])
    self.assertIn("upper_back", schema["keypoints"])
    self.assertEqual(manifest["tracking_core"], "apache_v1")
    self.assertEqual(manifest["thresholds"]["hardware_identity_switches"], 0)
    self.assertIn("direct_side_pinned", manifest["required_clip_categories"])


if __name__ == "__main__":
  unittest.main()
