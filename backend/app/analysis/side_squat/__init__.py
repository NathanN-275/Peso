"""Side-view squat analysis stages with explicit, versioned contracts."""

from .quality_preflight import (
  QUALITY_PREFLIGHT_MODEL_VERSION,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  QualityPreflightThresholds,
  SideSquatQualityPreflight,
  evaluate_quality_observations,
)

__all__ = [
  "QUALITY_PREFLIGHT_MODEL_VERSION",
  "QUALITY_PREFLIGHT_THRESHOLD_VERSION",
  "QualityPreflightThresholds",
  "SideSquatQualityPreflight",
  "evaluate_quality_observations",
]
