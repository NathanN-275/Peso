from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable


VISIBLE_JOINTS = ("shoulder", "hip", "knee", "ankle")
SEGMENTS = (("shoulder", "hip"), ("hip", "knee"), ("knee", "ankle"))


def _number(value: object) -> float | None:
  if isinstance(value, (int, float)) and math.isfinite(float(value)):
    return float(value)
  return None


def _mean(values: Iterable[float]) -> float | None:
  resolved = list(values)
  return statistics.fmean(resolved) if resolved else None


def _median(values: Iterable[float]) -> float | None:
  resolved = list(values)
  return float(statistics.median(resolved)) if resolved else None


def _percentile(values: list[float], percentile: float) -> float | None:
  if not values:
    return None
  ordered = sorted(values)
  index = min(
    max(int(math.ceil(percentile / 100.0 * len(ordered))) - 1, 0),
    len(ordered) - 1,
  )
  return ordered[index]


def _point(landmarks: dict[str, Any], name: str) -> dict[str, Any] | None:
  value = landmarks.get(name)
  return value if isinstance(value, dict) else None


def _visibility(point: dict[str, Any] | None) -> float:
  return max(0.0, min(1.0, _number((point or {}).get("visibility")) or 0.0))


def _distance(first: dict[str, Any] | None, second: dict[str, Any] | None) -> float | None:
  if not first or not second:
    return None
  first_x = _number(first.get("x"))
  first_y = _number(first.get("y"))
  second_x = _number(second.get("x"))
  second_y = _number(second.get("y"))
  if None in (first_x, first_y, second_x, second_y):
    return None
  return math.hypot(first_x - second_x, first_y - second_y)


def _side_score(landmarks: dict[str, Any], side: str) -> float:
  return statistics.fmean(
    _visibility(_point(landmarks, f"{side}_{joint}"))
    for joint in VISIBLE_JOINTS
  )


def _selected_side(frame: dict[str, Any]) -> str | None:
  landmarks = frame.get("landmarks")
  if not isinstance(landmarks, dict):
    return None
  left_score = _side_score(landmarks, "left")
  right_score = _side_score(landmarks, "right")
  if max(left_score, right_score) <= 0.0:
    return None
  return "left" if left_score >= right_score else "right"


def _subject_height(frame: dict[str, Any], side: str) -> float | None:
  landmarks = frame.get("landmarks") or {}
  return _distance(
    _point(landmarks, f"{side}_shoulder"),
    _point(landmarks, f"{side}_ankle"),
  )


def _frame_confidence(frame: dict[str, Any], confidence_threshold: float) -> dict[str, Any]:
  side = _selected_side(frame)
  landmarks = frame.get("landmarks") or {}
  confidences = (
    [_visibility(_point(landmarks, f"{side}_{joint}")) for joint in VISIBLE_JOINTS]
    if side
    else []
  )
  return {
    "sourceFrameIndex": int(frame.get("source_frame_index") or 0),
    "timestampMs": int(frame.get("timestamp_ms") or 0),
    "selectedSide": side,
    "meanVisibleChainConfidence": round(statistics.fmean(confidences), 4) if confidences else 0.0,
    "minimumVisibleChainConfidence": round(min(confidences), 4) if confidences else 0.0,
    "visibleChainCovered": bool(confidences and all(value >= confidence_threshold for value in confidences)),
  }


def _identity_metrics(frames: list[dict[str, Any]]) -> dict[str, Any]:
  sides = [side for frame in frames if (side := _selected_side(frame))]
  switches = sum(current != previous for previous, current in zip(sides, sides[1:]))
  transitions = max(len(sides) - 1, 0)
  return {
    "observedFrameCount": len(sides),
    "sideSwitchCount": switches,
    "stabilityScore": round(1.0 - switches / transitions, 4) if transitions else (1.0 if sides else 0.0),
    "note": "Proxy metric based on relative landmark visibility; it is not physical-side ground truth.",
  }


def _bone_consistency(frames: list[dict[str, Any]]) -> dict[str, Any]:
  segment_lengths: dict[str, list[float]] = defaultdict(list)
  for frame in frames:
    side = _selected_side(frame)
    if not side:
      continue
    landmarks = frame.get("landmarks") or {}
    for start, end in SEGMENTS:
      length = _distance(
        _point(landmarks, f"{side}_{start}"),
        _point(landmarks, f"{side}_{end}"),
      )
      if length is not None and length > 0:
        segment_lengths[f"{start}To{end.title()}"].append(length)

  coefficients: dict[str, float | None] = {}
  for name, values in segment_lengths.items():
    mean_length = _mean(values)
    coefficients[name] = (
      round(statistics.pstdev(values) / mean_length, 4)
      if mean_length and len(values) >= 2
      else 0.0 if values else None
    )
  valid_coefficients = [value for value in coefficients.values() if value is not None]
  return {
    "segmentCoefficientOfVariation": coefficients,
    "consistencyScore": (
      round(max(0.0, 1.0 - statistics.fmean(valid_coefficients)), 4)
      if valid_coefficients
      else 0.0
    ),
  }


def _trajectory_metrics(
  frames: list[dict[str, Any]],
  *,
  sudden_displacement_heights_per_second: float,
) -> dict[str, Any]:
  residuals: list[float] = []
  displacement_events = 0
  displacement_opportunities = 0
  by_joint: dict[str, list[tuple[int, dict[str, Any], float]]] = defaultdict(list)

  for frame in frames:
    side = _selected_side(frame)
    if not side:
      continue
    height = _subject_height(frame, side)
    if not height or height <= 0:
      continue
    timestamp_ms = int(frame.get("timestamp_ms") or 0)
    landmarks = frame.get("landmarks") or {}
    for joint in VISIBLE_JOINTS:
      point = _point(landmarks, f"{side}_{joint}")
      if point:
        by_joint[joint].append((timestamp_ms, point, height))

  for samples in by_joint.values():
    for previous, current in zip(samples, samples[1:]):
      elapsed_seconds = (current[0] - previous[0]) / 1000.0
      distance = _distance(previous[1], current[1])
      if elapsed_seconds <= 0 or distance is None:
        continue
      displacement_opportunities += 1
      normalized_speed = distance / max(current[2], 0.001) / elapsed_seconds
      if normalized_speed > sudden_displacement_heights_per_second:
        displacement_events += 1

    for first, second, third in zip(samples, samples[1:], samples[2:]):
      first_dt = (second[0] - first[0]) / 1000.0
      second_dt = (third[0] - second[0]) / 1000.0
      if first_dt <= 0 or second_dt <= 0:
        continue
      first_x = _number(first[1].get("x"))
      first_y = _number(first[1].get("y"))
      second_x = _number(second[1].get("x"))
      second_y = _number(second[1].get("y"))
      third_x = _number(third[1].get("x"))
      third_y = _number(third[1].get("y"))
      if None in (first_x, first_y, second_x, second_y, third_x, third_y):
        continue
      velocity_x = (second_x - first_x) / first_dt
      velocity_y = (second_y - first_y) / first_dt
      predicted_x = second_x + velocity_x * second_dt
      predicted_y = second_y + velocity_y * second_dt
      residuals.append(
        math.hypot(third_x - predicted_x, third_y - predicted_y) / max(third[2], 0.001)
      )

  return {
    "temporalJitter": {
      "medianNormalizedConstantVelocityResidual": round(_median(residuals) or 0.0, 5),
      "p95NormalizedConstantVelocityResidual": round(_percentile(residuals, 95) or 0.0, 5),
      "sampleCount": len(residuals),
      "note": "Proxy residual includes true acceleration and is not keypoint error.",
    },
    "suddenDisplacement": {
      "eventCount": displacement_events,
      "opportunityCount": displacement_opportunities,
      "frequency": round(displacement_events / displacement_opportunities, 4) if displacement_opportunities else 0.0,
      "thresholdHeightsPerSecond": sudden_displacement_heights_per_second,
    },
  }


def _annotation_frames(annotations: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
  if not isinstance(annotations, dict):
    return {}
  return {
    int(frame["source_frame_index"]): frame
    for frame in annotations.get("frames") or []
    if isinstance(frame, dict) and isinstance(frame.get("source_frame_index"), int)
  }


def _ground_truth_metrics(
  frames: list[dict[str, Any]],
  annotations: dict[str, Any] | None,
) -> dict[str, Any]:
  labels_by_frame = _annotation_frames(annotations)
  density = str((annotations or {}).get("annotation_density") or "none")
  synthetic = density == "synthetic"
  errors: list[float] = []
  identity_matches: list[bool] = []
  source_labeled_points = 0
  evaluable_labeled_points = 0
  matched_points = 0
  unsupported_labels: set[str] = set()
  predicted_by_frame = {
    int(frame.get("source_frame_index") or 0): frame
    for frame in frames
  }
  source_frame_count = int(((annotations or {}).get("source") or {}).get("frameCount") or 0)
  dense_frame_coverage = len(labels_by_frame) / max(source_frame_count, 1)

  for frame_index, label_frame in labels_by_frame.items():
    predicted = predicted_by_frame.get(frame_index)
    landmarks = label_frame.get("landmarks") or {}
    labeled_side = label_frame.get("visible_anatomical_side")
    if predicted and labeled_side in {"left", "right"}:
      identity_matches.append(_selected_side(predicted) == labeled_side)
    for visible_name, expected in landmarks.items():
      if not isinstance(expected, dict):
        continue
      source_labeled_points += 1
      joint = str(visible_name).removeprefix("visible_")
      if joint not in VISIBLE_JOINTS:
        unsupported_labels.add(str(visible_name))
        continue
      if not predicted:
        continue
      evaluable_labeled_points += 1
      side = labeled_side if labeled_side in {"left", "right"} else _selected_side(predicted)
      if not side:
        continue
      actual = _point(predicted.get("landmarks") or {}, f"{side}_{joint}")
      error = _distance(actual, expected)
      if error is None:
        continue
      height = _subject_height(predicted, side)
      errors.append(error / max(height or 1.0, 0.001))
      matched_points += 1

  accuracy_claim_eligible = (
    density == "dense"
    and not synthetic
    and bool(labels_by_frame)
    and source_frame_count > 0
    and dense_frame_coverage >= 0.8
    and evaluable_labeled_points > 0
    and matched_points / evaluable_labeled_points >= 0.8
  )
  return {
    "annotationDensity": density,
    "labeledFrameCount": len(labels_by_frame),
    "sourceFrameCount": source_frame_count,
    "denseFrameCoverage": round(dense_frame_coverage, 4),
    "sourceLabeledPointCount": source_labeled_points,
    "evaluableLabeledPointCount": evaluable_labeled_points,
    "matchedPointCount": matched_points,
    "matchedPointCoverage": round(matched_points / max(evaluable_labeled_points, 1), 4),
    "medianNormalizedLabeledPointError": round(_median(errors), 5) if errors else None,
    "p95NormalizedLabeledPointError": round(_percentile(errors, 95), 5) if errors else None,
    "visibleSideIdentityAccuracy": (
      round(sum(identity_matches) / len(identity_matches), 4)
      if identity_matches
      else None
    ),
    "unsupportedLabels": sorted(unsupported_labels),
    "accuracyClaimEligible": accuracy_claim_eligible,
    "limitation": (
      None
      if accuracy_claim_eligible
      else "Sparse, synthetic, missing, or incomplete labels cannot support an absolute accuracy claim."
    ),
  }


def _bottom_stability(
  frames: list[dict[str, Any]],
  annotations: dict[str, Any] | None,
  *,
  max_frame_distance: int,
) -> dict[str, Any]:
  bottom_indices = {
    int(frame["source_frame_index"])
    for frame in (annotations or {}).get("frames") or []
    if isinstance(frame, dict)
    and frame.get("phase") == "bottom_transition"
    and isinstance(frame.get("source_frame_index"), int)
  }
  hip_y_values: list[float] = []
  matched_bottom_indices: set[int] = set()
  for bottom_index in bottom_indices:
    frame = min(
      frames,
      key=lambda value: abs(int(value.get("source_frame_index") or 0) - bottom_index),
      default=None,
    )
    if frame is None:
      continue
    source_frame_index = int(frame.get("source_frame_index") or 0)
    if abs(bottom_index - source_frame_index) > max_frame_distance:
      continue
    side = _selected_side(frame)
    if not side:
      continue
    hip_y = _number((_point(frame.get("landmarks") or {}, f"{side}_hip") or {}).get("y"))
    if hip_y is not None:
      hip_y_values.append(hip_y)
      matched_bottom_indices.add(bottom_index)
  return {
    "labeledBottomCount": len(bottom_indices),
    "matchedBottomCount": len(matched_bottom_indices),
    "predictedHipYStandardDeviation": (
      round(statistics.pstdev(hip_y_values), 5)
      if len(hip_y_values) >= 2
      else None
    ),
    "limitation": None if len(bottom_indices) >= 2 else "Bottom stability needs at least two labeled rep bottoms.",
  }


def evaluate_pose_result(
  estimation: dict[str, Any],
  *,
  annotations: dict[str, Any] | None = None,
  confidence_threshold: float = 0.35,
  sudden_displacement_heights_per_second: float = 4.0,
) -> dict[str, Any]:
  frames = [frame for frame in estimation.get("frames") or [] if isinstance(frame, dict)]
  sampled_frame_count = int(estimation.get("sampled_frame_count") or 0)
  frame_confidence = [_frame_confidence(frame, confidence_threshold) for frame in frames]
  covered_frames = sum(frame["visibleChainCovered"] for frame in frame_confidence)
  trajectory = _trajectory_metrics(
    frames,
    sudden_displacement_heights_per_second=sudden_displacement_heights_per_second,
  )
  return {
    "proxyMetrics": {
      "landmarkAvailability": {
        "poseFrameCount": len(frames),
        "sampledFrameCount": sampled_frame_count,
        "coverage": round(len(frames) / max(sampled_frame_count, 1), 4),
      },
      "confidenceCoverage": {
        "threshold": confidence_threshold,
        "coveredFrameCount": covered_frames,
        "poseFrameCount": len(frames),
        "coverage": round(covered_frames / max(len(frames), 1), 4),
      },
      "visibleSideIdentityStability": _identity_metrics(frames),
      "boneLengthConsistency": _bone_consistency(frames),
      **trajectory,
      "bottomPositionStability": _bottom_stability(
        frames,
        annotations,
        max_frame_distance=max(1, int(estimation.get("frame_step") or 1) // 2),
      ),
    },
    "groundTruthMetrics": _ground_truth_metrics(frames, annotations),
    "frameConfidence": frame_confidence,
  }
