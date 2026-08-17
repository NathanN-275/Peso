from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_TRACKING_CORES = {"legacy", "apache_v1"}
SUPPORTED_YOLO_TRACKING_MODES = {"off", "shadow", "candidate"}


def _bool_from_env(name: str, default: bool) -> bool:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  normalized = raw_value.strip().lower()
  if normalized in {"1", "true", "yes", "on"}:
    return True
  if normalized in {"0", "false", "no", "off"}:
    return False
  return default


def _float_from_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  try:
    value = float(raw_value)
  except ValueError:
    return default
  return value if minimum <= value <= maximum else default


def _int_from_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  try:
    value = int(raw_value)
  except ValueError:
    return default
  return value if minimum <= value <= maximum else default


@dataclass(frozen=True)
class TrackingCoreConfig:
  core: str = "legacy"
  fallback_to_legacy: bool = True
  detection_fixture_path: Path | None = None
  min_collar_confidence: float = 0.45
  initial_lock_frames: int = 3
  reacquire_frames: int = 3
  max_coast_frames: int = 2
  max_coast_seconds: float = 0.25
  max_lane_distance: float = 0.065
  yolo_mode: str = "off"
  yolo_model_path: Path | None = None
  yolo_model_version: str | None = None
  yolo_class_names: tuple[str, ...] = ()
  yolo_confidence_threshold: float = 0.45
  yolo_nms_iou_threshold: float = 0.45
  yolo_input_size: int = 640

  @property
  def enabled(self) -> bool:
    return self.core == "apache_v1"

  @property
  def yolo_enabled(self) -> bool:
    return self.yolo_mode in {"shadow", "candidate"}


def tracking_core_config_from_env() -> TrackingCoreConfig:
  raw_core = (os.getenv("TRACKING_CORE", "legacy").strip().lower() or "legacy")
  core = raw_core if raw_core in SUPPORTED_TRACKING_CORES else "legacy"
  fixture_raw = os.getenv("APACHE_V1_DETECTIONS_PATH", "").strip()
  raw_yolo_mode = (os.getenv("YOLO_TRACKING_MODE", "off").strip().lower() or "off")
  yolo_mode = raw_yolo_mode if raw_yolo_mode in SUPPORTED_YOLO_TRACKING_MODES else "off"
  model_raw = os.getenv("YOLO_TRACKING_MODEL_PATH", "").strip()
  model_version = os.getenv("YOLO_TRACKING_MODEL_VERSION", "").strip() or None
  class_names = tuple(
    value.strip()
    for value in os.getenv("YOLO_TRACKING_CLASS_NAMES", "").split(",")
    if value.strip()
  )
  return TrackingCoreConfig(
    core=core,
    fallback_to_legacy=_bool_from_env("TRACKING_CORE_FALLBACK_TO_LEGACY", True),
    detection_fixture_path=Path(fixture_raw) if fixture_raw else None,
    max_coast_seconds=_float_from_env(
      "YOLO_TRACKING_MAX_COAST_SECONDS", 0.25, minimum=0.05, maximum=2.0
    ),
    yolo_mode=yolo_mode,
    yolo_model_path=Path(model_raw) if model_raw else None,
    yolo_model_version=model_version,
    yolo_class_names=class_names,
    yolo_confidence_threshold=_float_from_env(
      "YOLO_TRACKING_CONFIDENCE_THRESHOLD", 0.45, minimum=0.05, maximum=0.99
    ),
    yolo_nms_iou_threshold=_float_from_env(
      "YOLO_TRACKING_NMS_IOU_THRESHOLD", 0.45, minimum=0.05, maximum=0.99
    ),
    yolo_input_size=_int_from_env("YOLO_TRACKING_INPUT_SIZE", 640, minimum=160, maximum=1536),
  )
