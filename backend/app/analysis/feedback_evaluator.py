"""Measure exported dashboard corrections against an analysis trace.

Dashboard corrections are development evidence for the current tuning pass and
become immutable regression evidence when that pass is complete.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any


BARBELL_TARGETS = {"barbell", "barbell_center"}


def _distance(first: dict[str, Any], second: dict[str, Any], width: float, height: float) -> float:
  return math.hypot((float(first["x"]) - float(second["x"])) * width,
                    (float(first["y"]) - float(second["y"])) * height)


def _percentile(values: list[float], percentile: float) -> float | None:
  if not values:
    return None
  ordered = sorted(values)
  index = min(len(ordered) - 1, max(0, math.ceil((percentile / 100) * len(ordered)) - 1))
  return ordered[index]


def _snapshot(trace: dict[str, Any], name: str) -> dict[str, Any] | None:
  for event in trace.get("events", []):
    payload = event.get("payload") or {}
    if event.get("type") == "snapshot" and payload.get("name") == name:
      return payload
  return None


def _frames_for(trace: dict[str, Any]) -> list[dict[str, Any]]:
  for name in ("pose_repair", "pin_fusion", "raw_pose"):
    payload = _snapshot(trace, name)
    if payload and isinstance(payload.get("frames"), list):
      return payload["frames"]
  return []


def _selected_side(trace: dict[str, Any]) -> str | None:
  repaired = _snapshot(trace, "pose_repair") or {}
  diagnostics = repaired.get("pose_repair") or {}
  side = diagnostics.get("selected_side")
  if side in {"left", "right"}:
    return side
  pin_fusion = _snapshot(trace, "pin_fusion") or {}
  assistance = pin_fusion.get("tracking_assistance") or {}
  for key in ("selectedSide", "selected_side"):
    side = assistance.get(key)
    if side in {"left", "right"}:
      return side
  return None


def _frame_for_correction(frames: list[dict[str, Any]], correction: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
  source_index = correction.get("source_frame_index")
  if isinstance(source_index, (int, float)):
    matches = [frame for frame in frames if frame.get("source_frame_index") == int(source_index)]
    if matches:
      return matches[0], None
    return None, "source_frame_not_in_trace"
  timestamp = correction.get("timestamp_ms")
  if not isinstance(timestamp, (int, float)) or not frames:
    return None, "missing_frame_reference"
  nearest = min(frames, key=lambda frame: abs(float(frame.get("timestamp_ms") or 0) - float(timestamp)))
  if abs(float(nearest.get("timestamp_ms") or 0) - float(timestamp)) > 100:
    return None, "timestamp_not_in_trace"
  return nearest, None


def _barbell_point(points: list[dict[str, Any]], timestamp_ms: float) -> tuple[dict[str, Any] | None, str | None]:
  if not points:
    return None, "barbell_path_unavailable"
  nearest = min(points, key=lambda point: abs((float(point.get("time") or 0) * 1000) - timestamp_ms))
  if abs((float(nearest.get("time") or 0) * 1000) - timestamp_ms) > 100:
    return None, "barbell_point_gap"
  x = nearest.get("markerX", nearest.get("x"))
  y = nearest.get("markerY", nearest.get("y"))
  if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
    return None, "barbell_point_invalid"
  return {"x": float(x), "y": float(y), **nearest}, None


def _pose_point(frame: dict[str, Any], target: str, selected_side: str | None) -> tuple[dict[str, Any] | None, str | None]:
  landmarks = frame.get("landmarks") or {}
  if target == "upper_back":
    if selected_side:
      point = landmarks.get(f"{selected_side}_upper_back") or landmarks.get(f"{selected_side}_shoulder")
      if isinstance(point, dict):
        return point, None
    candidates = [landmarks.get(f"{side}_upper_back") for side in ("left", "right")]
    point = next((candidate for candidate in candidates if isinstance(candidate, dict)), None)
    return point, None if point else "upper_back_missing"
  landmark_target = f"{selected_side}_{target}" if target in {"hip", "knee", "ankle"} and selected_side else target
  point = landmarks.get(landmark_target)
  return (point, None) if isinstance(point, dict) else (None, "landmark_missing")


def _summary(values: list[float]) -> dict[str, float | int]:
  return {
    "count": len(values),
    "median_px": round(median(values), 3),
    "p95_px": round(_percentile(values, 95) or 0.0, 3),
    "max_px": round(max(values), 3),
  }


def evaluate_feedback(trace: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
  """Return correction error, coverage, and continuity metrics for one trace."""
  frames = _frames_for(trace)
  barbell_payload = _snapshot(trace, "barbell_tracking") or {}
  barbell_path = barbell_payload.get("barbell_path") or {}
  barbell_points = barbell_path.get("points", []) if isinstance(barbell_path, dict) else []
  width = float((frames[0] if frames else {}).get("frame_width") or 1)
  height = float((frames[0] if frames else {}).get("frame_height") or 1)
  selected_side = _selected_side(trace)
  errors: dict[str, list[float]] = {}
  mode_errors: dict[str, list[float]] = {"automatic": [], "pin_assisted": []}
  unmatched: list[dict[str, Any]] = []
  correction_count = 0

  for annotation in feedback.get("annotations", []):
    for correction in annotation.get("corrections", []):
      correction_count += 1
      frame, frame_reason = _frame_for_correction(frames, correction)
      target = str(correction.get("target") or "")
      if frame is None:
        unmatched.append({"target": target, "source_frame_index": correction.get("source_frame_index"), "reason": frame_reason})
        continue
      if target in BARBELL_TARGETS:
        actual, reason = _barbell_point(barbell_points, float(frame.get("timestamp_ms") or correction.get("timestamp_ms") or 0))
      else:
        actual, reason = _pose_point(frame, target, selected_side)
      if actual is None:
        unmatched.append({"target": target, "source_frame_index": correction.get("source_frame_index"), "reason": reason})
        continue
      error = _distance(correction, actual, width, height)
      errors.setdefault(target, []).append(error)
      mode = "pin_assisted" if actual.get("manual_assisted") else "automatic"
      mode_errors[mode].append(error)

  issue_counts = {"drift": 0, "failed_recovery": 0, "identity_switch": 0, "gaps": 0}
  for annotation in feedback.get("annotations", []):
    issue_types = set(annotation.get("issue_types", []))
    for issue in ("drift", "failed_recovery"):
      issue_counts[issue] += int(issue in issue_types)
    issue_counts["identity_switch"] += int("wrong_point" in issue_types)
    issue_counts["gaps"] += int("failed_recovery" in issue_types or annotation.get("expected_behaviors") == ["recover_tracking"])

  return {
    "run_id": trace.get("run_id") or feedback.get("run_id"),
    "selected_side": selected_side,
    "correction_count": correction_count,
    "evaluated_corrections": correction_count - len(unmatched),
    "matched_correction_coverage": round((correction_count - len(unmatched)) / max(correction_count, 1), 3),
    "unmatched_corrections": unmatched,
    "metrics": {target: _summary(values) for target, values in sorted(errors.items())},
    "mode_metrics": {mode: _summary(values) for mode, values in mode_errors.items() if values},
    "mode_error_samples_px": {mode: values for mode, values in mode_errors.items() if values},
    "annotation_count": len(feedback.get("annotations", [])),
    "issue_counts": issue_counts,
  }


def aggregate_feedback_results(results: list[dict[str, Any]]) -> dict[str, Any]:
  """Combine per-run evaluator results without discarding mode separation."""
  correction_count = sum(int(result.get("correction_count") or 0) for result in results)
  evaluated = sum(int(result.get("evaluated_corrections") or 0) for result in results)
  mode_errors: dict[str, list[float]] = {"automatic": [], "pin_assisted": []}
  issue_counts = {"drift": 0, "failed_recovery": 0, "identity_switch": 0, "gaps": 0}
  for result in results:
    for key in issue_counts:
      issue_counts[key] += int((result.get("issue_counts") or {}).get(key) or 0)
    for mode, values in (result.get("mode_error_samples_px") or {}).items():
      if mode not in mode_errors:
        continue
      mode_errors[mode].extend(float(value) for value in values)
  return {
    "run_count": len(results),
    "correction_count": correction_count,
    "evaluated_corrections": evaluated,
    "matched_correction_coverage": round(evaluated / max(correction_count, 1), 3),
    "unmatched_correction_count": correction_count - evaluated,
    "mode_metrics": {mode: _summary(values) for mode, values in mode_errors.items() if values},
    "issue_counts": issue_counts,
  }
