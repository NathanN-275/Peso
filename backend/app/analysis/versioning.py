from __future__ import annotations

from typing import Any

from ..services.config import get_settings


def analysis_model_version(analysis: dict[str, Any] | None, result_json: dict[str, Any] | None = None) -> str | None:
  result = result_json or (analysis or {}).get("result_json") or {}
  return (
    result.get("analysis_model_version")
    or result.get("model_version")
    or (analysis or {}).get("model_version")
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
