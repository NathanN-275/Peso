from __future__ import annotations

from typing import Any


def analysis_needs_vitpose_fallback(result: dict[str, Any]) -> str | None:
  diagnostics = result.get("diagnostics") or {}
  quality_flags = set(diagnostics.get("quality_flags") or [])
  pose_validation = diagnostics.get("pose_validation") or {}
  depth_counts = diagnostics.get("depth_status_counts") or {}

  if "plate_rack_occlusion_suspected" in quality_flags or diagnostics.get("plate_rack_occlusion_suspected"):
    return "plate_rack_occlusion_suspected"
  if "excessive_landmark_jitter" in quality_flags:
    return "excessive_landmark_jitter"
  if pose_validation.get("rejected_landmark_count", 0) or pose_validation.get("occluded_landmark_count", 0):
    return "pose_validation_rejections"
  if depth_counts.get("uncertain_depth_count", 0):
    return "uncertain_depth"

  for rep in result.get("reps") or []:
    depth_components = rep.get("depth_components") or {}
    if depth_components.get("bottom_depth_landmarks_unreliable"):
      return "bottom_depth_landmarks_unreliable"
    if rep.get("depth_confidence", 1.0) < 0.45:
      return "low_bottom_depth_confidence"

  return None
