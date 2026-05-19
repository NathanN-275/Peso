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


def analysis_is_current(analysis: dict[str, Any] | None) -> bool:
  return analysis_model_version(analysis) == get_settings().model_version


def annotate_analysis_freshness(result_json: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
  annotated = dict(result_json or {})
  expected_model_version = get_settings().model_version
  stored_model_version = analysis_model_version(analysis, annotated)
  annotated["expected_model_version"] = expected_model_version
  annotated["analysis_model_version"] = stored_model_version
  annotated["analysis_stale"] = stored_model_version != expected_model_version
  diagnostics = dict(annotated.get("diagnostics") or {})
  diagnostics["expected_model_version"] = expected_model_version
  diagnostics["analysis_model_version"] = stored_model_version
  diagnostics["analysis_stale"] = annotated["analysis_stale"]
  annotated["diagnostics"] = diagnostics
  return annotated
