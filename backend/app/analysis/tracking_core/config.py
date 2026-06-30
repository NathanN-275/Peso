from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_TRACKING_CORES = {"legacy", "apache_v1"}


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


@dataclass(frozen=True)
class TrackingCoreConfig:
  core: str = "legacy"
  fallback_to_legacy: bool = True
  detection_fixture_path: Path | None = None
  min_collar_confidence: float = 0.45
  initial_lock_frames: int = 3
  reacquire_frames: int = 3
  max_coast_frames: int = 2
  max_lane_distance: float = 0.065

  @property
  def enabled(self) -> bool:
    return self.core == "apache_v1"


def tracking_core_config_from_env() -> TrackingCoreConfig:
  raw_core = (os.getenv("TRACKING_CORE", "legacy").strip().lower() or "legacy")
  core = raw_core if raw_core in SUPPORTED_TRACKING_CORES else "legacy"
  fixture_raw = os.getenv("APACHE_V1_DETECTIONS_PATH", "").strip()
  return TrackingCoreConfig(
    core=core,
    fallback_to_legacy=_bool_from_env("TRACKING_CORE_FALLBACK_TO_LEGACY", True),
    detection_fixture_path=Path(fixture_raw) if fixture_raw else None,
  )
