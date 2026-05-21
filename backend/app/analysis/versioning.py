from __future__ import annotations

from typing import Any

from ..services.config import get_settings


DEPTH_DEBUG_FIELDS = (
  "estimated_hip_crease_y",
  "estimated_knee_top_y",
  "depth_delta_px",
  "depth_tolerance_px",
  "depth_classification",
  "depth_reason",
  "selected_side",
  "selected_source",
)


def analysis_model_version(analysis: dict[str, Any] | None, result_json: dict[str, Any] | None = None) -> str | None:
  result = result_json or (analysis or {}).get("result_json") or {}
  return (
    result.get("analysis_model_version")
    or result.get("model_version")
    or (analysis or {}).get("model_version")
  )


def _first_present(*values: Any) -> Any:
  for value in values:
    if value is not None:
      return value
  return None


def _rep_depth_debug_field(rep: dict[str, Any], field: str) -> Any:
  depth_evidence = rep.get("depth_evidence") or {}
  depth_components = rep.get("depth_components") or {}

  camel_case_fields = {
    "estimated_hip_crease_y": "estimatedHipCreaseY",
    "estimated_knee_top_y": "estimatedKneeTopY",
    "depth_delta_px": "depthDeltaPx",
    "depth_tolerance_px": "depthTolerancePx",
    "depth_classification": "depthClassification",
    "depth_reason": "depthReason",
    "selected_side": "selectedSide",
    "selected_source": "selectedSource",
  }
  camel_field = camel_case_fields[field]

  return _first_present(
    rep.get(field),
    rep.get(camel_field),
    depth_evidence.get(field),
    depth_evidence.get(camel_field),
    depth_components.get(field),
    depth_components.get(camel_field),
  )


def analysis_payload_incomplete(result_json: dict[str, Any] | None) -> bool:
  result = result_json or {}
  if result.get("analysis_limited"):
    return False

  diagnostics = result.get("diagnostics") or {}
  if not (result.get("pose_backend") or diagnostics.get("pose_backend")):
    return True
  if not (result.get("landmark_model") or diagnostics.get("landmark_model")):
    return True

  for rep in result.get("reps") or []:
    depth_status = rep.get("depth_status") or rep.get("depthStatus")
    depth_evidence = rep.get("depth_evidence") or {}
    depth_components = rep.get("depth_components") or {}
    hip_knee_delta = depth_evidence.get("hip_knee_delta", depth_components.get("hip_knee_delta"))
    parallel_score = depth_evidence.get("parallel_score", depth_components.get("parallel_score"))

    if not depth_status or hip_knee_delta is None or parallel_score is None:
      return True
    if any(_rep_depth_debug_field(rep, field) is None for field in DEPTH_DEBUG_FIELDS):
      return True

  return False


def analysis_is_current(analysis: dict[str, Any] | None) -> bool:
  result_json = (analysis or {}).get("result_json") or {}
  return (
    analysis_model_version(analysis, result_json) == get_settings().model_version
    and not analysis_payload_incomplete(result_json)
  )


def annotate_analysis_freshness(result_json: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
  annotated = dict(result_json or {})
  expected_model_version = get_settings().model_version
  stored_model_version = analysis_model_version(analysis, annotated)
  analysis_incomplete = analysis_payload_incomplete(annotated)
  annotated["expected_model_version"] = expected_model_version
  annotated["analysis_model_version"] = stored_model_version
  annotated["analysis_incomplete"] = analysis_incomplete
  annotated["analysis_stale"] = stored_model_version != expected_model_version or analysis_incomplete
  diagnostics = dict(annotated.get("diagnostics") or {})
  diagnostics["expected_model_version"] = expected_model_version
  diagnostics["analysis_model_version"] = stored_model_version
  diagnostics["analysis_incomplete"] = analysis_incomplete
  diagnostics["analysis_stale"] = annotated["analysis_stale"]
  annotated["diagnostics"] = diagnostics
  return annotated
