from __future__ import annotations

import time
from typing import Any

from .config import TrackingCoreConfig
from .detectors import FixtureObjectDetector, NullObjectDetector, ObjectDetectorBackend
from .models import NormalizedPoint, TrackingPrior
from .temporal_tracker import BarbellIdentityTracker


def _manual_priors_to_tracking_priors(
  manual_barbell_priors: dict[int, dict[str, float]] | None,
) -> dict[int, TrackingPrior]:
  priors: dict[int, TrackingPrior] = {}
  for source_index, point in (manual_barbell_priors or {}).items():
    if not isinstance(point, dict):
      continue
    x = point.get("x")
    y = point.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
      continue
    priors[int(source_index)] = TrackingPrior(
      name="barbell",
      center=NormalizedPoint(float(x), float(y)).clamped(),
      confidence=float(point.get("confidence") or 0.0),
      source=str(point.get("source") or "pin"),
      stale=bool(point.get("stale") or point.get("stale_track") or point.get("velocity_cap_reused_previous")),
    )
  return priors


def _detector_from_config(config: TrackingCoreConfig) -> ObjectDetectorBackend:
  if config.detection_fixture_path:
    return FixtureObjectDetector(config.detection_fixture_path)
  return NullObjectDetector()


def run_apache_v1_tracking(
  *,
  video_path: str,
  pose_frames: list[dict[str, Any]],
  processed_width: int | None,
  processed_height: int | None,
  manual_barbell_priors: dict[int, dict[str, float]] | None,
  config: TrackingCoreConfig,
  detector: ObjectDetectorBackend | None = None,
) -> dict[str, Any]:
  started = time.perf_counter()
  width = int(processed_width or 0)
  height = int(processed_height or 0)
  diagnostics: dict[str, Any] = {
    "tracking_core": "apache_v1",
    "object_detector": None,
    "pose_backend_strategy": "mmpose_rtmpose_adapter",
    "deployment_strategy": "mmdeploy_onnxruntime",
    "available": False,
  }
  if width <= 0 or height <= 0:
    diagnostics["failure_reason"] = "missing_processed_dimensions"
    return _empty_result(diagnostics, started)

  detector = detector or _detector_from_config(config)
  diagnostics["object_detector"] = detector.name
  detection_frames = detector.detect(video_path=video_path, width=width, height=height)
  diagnostics["detection_frame_count"] = len(detection_frames)
  if not detection_frames:
    diagnostics["failure_reason"] = "detector_not_configured"
    return _empty_result(diagnostics, started)

  tracker = BarbellIdentityTracker(config)
  points, tracker_diagnostics = tracker.track(
    detection_frames,
    priors_by_frame=_manual_priors_to_tracking_priors(manual_barbell_priors),
  )
  public_points = [point.to_public() for point in points]
  coverage = len(public_points) / max(len(detection_frames), 1)
  diagnostics.update({
    "available": bool(public_points),
    "coverage": coverage,
    "barbell_identity": tracker_diagnostics,
    "source_counts": tracker_diagnostics.get("source_counts") or {},
    "hardware_rejection_count": tracker_diagnostics.get("hardware_rejection_count", 0),
    "identity_gap_count": tracker_diagnostics.get("identity_gap_count", 0),
    "coasting_count": tracker_diagnostics.get("coasting_count", 0),
    "processing_duration_ms": int((time.perf_counter() - started) * 1000),
  })
  return {
    "barbellPath": {
      "available": bool(public_points),
      "target": "near_plate_collar_center",
      "source": "apache_v1_detector_tracker",
      "coverage": coverage,
      "points": public_points,
    },
    "diagnostics": diagnostics,
  }


def _empty_result(diagnostics: dict[str, Any], started: float) -> dict[str, Any]:
  diagnostics["processing_duration_ms"] = int((time.perf_counter() - started) * 1000)
  return {
    "barbellPath": {
      "available": False,
      "target": "near_plate_collar_center",
      "source": "apache_v1_detector_tracker",
      "coverage": 0.0,
      "points": [],
    },
    "diagnostics": diagnostics,
  }
