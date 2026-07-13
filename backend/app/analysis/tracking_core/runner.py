from __future__ import annotations

import time
from typing import Any

from .config import TrackingCoreConfig
from .detectors import (
  FixtureObjectDetector,
  NullObjectDetector,
  ObjectDetectorBackend,
  YoloOnnxObjectDetector,
)
from .models import DetectionFrame, NormalizedPoint, TrackingPrior
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
  if config.yolo_model_path:
    return YoloOnnxObjectDetector(
      model_path=config.yolo_model_path,
      class_names=config.yolo_class_names,
      confidence_threshold=config.yolo_confidence_threshold,
      nms_iou_threshold=config.yolo_nms_iou_threshold,
      input_size=config.yolo_input_size,
    )
  return NullObjectDetector()


def detect_tracking_objects(
  *,
  video_path: str,
  pose_frames: list[dict[str, Any]],
  processed_width: int | None,
  processed_height: int | None,
  config: TrackingCoreConfig,
  detector: ObjectDetectorBackend | None = None,
) -> tuple[list[DetectionFrame], dict[str, Any]]:
  """Detect objects only on the frames sampled by the pose estimator.

  This is shared by shadow mode and candidate mode so candidate tracking does
  not decode and infer the same video twice.
  """
  started = time.perf_counter()
  width = int(processed_width or 0)
  height = int(processed_height or 0)
  diagnostics: dict[str, Any] = {
    "mode": config.yolo_mode,
    "available": False,
    "object_detector": None,
  }
  if width <= 0 or height <= 0:
    diagnostics["failure_reason"] = "missing_processed_dimensions"
    diagnostics["processing_duration_ms"] = int((time.perf_counter() - started) * 1000)
    return [], diagnostics

  source_indices = {
    int(frame["source_frame_index"])
    for frame in pose_frames
    if isinstance(frame.get("source_frame_index"), int)
  }
  timestamps = {
    int(frame["source_frame_index"]): float(frame.get("timestamp_ms") or 0.0) / 1000.0
    for frame in pose_frames
    if isinstance(frame.get("source_frame_index"), int)
  }
  try:
    detector = detector or _detector_from_config(config)
    diagnostics["object_detector"] = detector.name
    detection_frames = detector.detect(
      video_path=video_path,
      width=width,
      height=height,
      source_frame_indices=source_indices or None,
      timestamps_by_source_index=timestamps or None,
    )
  except Exception as error:
    diagnostics["failure_reason"] = "detector_error"
    diagnostics["error"] = str(error)
    diagnostics["processing_duration_ms"] = int((time.perf_counter() - started) * 1000)
    return [], diagnostics

  diagnostics.update({
    "available": bool(detection_frames),
    "detection_frame_count": len(detection_frames),
    "detection_count": sum(len(frame.detections) for frame in detection_frames),
    "processing_duration_ms": int((time.perf_counter() - started) * 1000),
  })
  if not detection_frames:
    diagnostics["failure_reason"] = "detector_not_configured"
  return detection_frames, diagnostics


def run_apache_v1_tracking(
  *,
  video_path: str,
  pose_frames: list[dict[str, Any]],
  processed_width: int | None,
  processed_height: int | None,
  manual_barbell_priors: dict[int, dict[str, float]] | None,
  config: TrackingCoreConfig,
  detector: ObjectDetectorBackend | None = None,
  detection_frames: list[DetectionFrame] | None = None,
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

  if detection_frames is None:
    detector = detector or _detector_from_config(config)
    diagnostics["object_detector"] = detector.name
    detection_frames, detector_diagnostics = detect_tracking_objects(
      video_path=video_path,
      pose_frames=pose_frames,
      processed_width=width,
      processed_height=height,
      config=config,
      detector=detector,
    )
    if detector_diagnostics.get("failure_reason"):
      diagnostics["failure_reason"] = detector_diagnostics["failure_reason"]
      diagnostics["detector_error"] = detector_diagnostics.get("error")
      return _empty_result(diagnostics, started)
  else:
    diagnostics["object_detector"] = detector.name if detector is not None else "precomputed_detector"
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
