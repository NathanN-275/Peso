from __future__ import annotations

import logging
import math
import time
from bisect import bisect_left
from pathlib import Path
from typing import Any

from .candidate import Candidate
from .constants import (
  BARBELL_TRACK_TARGET_FPS,
  INIT_CONFIRMATION_FRAMES,
  MAX_LOCAL_TRACKING_FAILURES,
  MIN_BOOTSTRAP_COLLAR_DESCRIPTOR_SCORE,
  MIN_COLLAR_DESCRIPTOR_SCORE,
  MIN_TRACK_COVERAGE,
  MIN_TRACK_POINTS,
  MAX_BAR_SPEED_FRAME_RATIO_PER_SECOND,
  PATH_PRIOR_MAX_RESIDUAL_PX,
  PATH_PRIOR_MIN_POINTS,
  PATH_PRIOR_WINDOW_POINTS,
  RECENT_POINT_MAX_JUMP_PX,
  STALE_PATH_RESET_SECONDS,
  SLEEVE_END_TRACKING_TARGET,
  TRACKING_SOURCE,
  TRACKING_TARGET,
)
from .debug import _draw_debug_frame
from .detection import _candidate_in_bounds, _detect_crop_candidates, _wrist_points_from_landmarks
from .geometry import (
  MIN_HUB_CONFIDENCE,
  _detect_hub_point,
  _estimate_collar_from_plate,
  _point_inside_plate,
  _refine_collar_point,
  _score_collar_patch,
  _validate_collar_geometry,
)
from .local_tracker import _make_tracking_lock, _track_local_patch
from .pin_tracker import build_pin_assisted_barbell_result
from .pose import _pose_bounds, _side_wrist_points
from .postprocess import _interpolate_missing, _remove_motion_outliers, _smooth_points_with_diagnostics
from .results import _empty_result
from .selection import (
  _plate_rejection_reason,
  _plate_match_is_consistent,
  _pose_relative_displacement,
  _score_plate_candidate,
  _shoulder_relative_offset,
)
from .sleeve_tracker import track_unloaded_sleeve_end

logger = logging.getLogger(__name__)

UNSAFE_HUB_REASONS = {
  "hub_fallback_plate_center",
  "hub_crop_empty",
  "hub_outside_plate_region",
  "low_confidence_hub",
  "moments_fallback_uncertain",
  "no_hub_candidates",
  "fresh_hub_not_found",
}


def _time_key(point: dict[str, Any]) -> float:
  return round(float(point.get("time") or 0.0), 4)


def _distance_px(
  first: dict[str, Any],
  second: dict[str, Any],
  *,
  width: float,
  height: float,
) -> float:
  return math.hypot(
    (float(first["x"]) - float(second["x"])) * width,
    (float(first["y"]) - float(second["y"])) * height,
  )


def _fuse_barbell_lanes(
  automatic_points: list[dict[str, Any]],
  manual_points: list[dict[str, Any]],
  *,
  width: float,
  height: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  if not manual_points:
    return automatic_points, {
      "enabled": False,
      "reason": "missing_manual_lane",
      "frames": [],
    }

  auto_by_time = {_time_key(point): point for point in automatic_points}
  manual_by_time = {_time_key(point): point for point in manual_points}
  fused: list[dict[str, Any]] = []
  frames: list[dict[str, Any]] = []
  source_counts: dict[str, int] = {}
  previous_manual: dict[str, Any] | None = None
  previous_automatic: dict[str, Any] | None = None
  previous_emitted: dict[str, Any] | None = None
  emitted_history: list[dict[str, Any]] = []
  consecutive_manual_failures = 0
  consecutive_auto_failures = 0
  automatic_recovery_streak = 0
  stationary_manual_rejection_count = 0
  agreement_limit_px = max(18.0, max(width, height) * 0.035)
  manual_jump_limit_px = max(70.0, max(width, height) * 0.14)
  stationary_motion_limit_px = max(2.5, max(width, height) * 0.004)
  active_bar_motion_px = max(8.0, max(width, height) * 0.012)

  def coast_from_history(time_key: float) -> dict[str, Any] | None:
    if not emitted_history:
      return None
    last = emitted_history[-1]
    if len(emitted_history) < 2:
      return {
        **last,
        "time": time_key,
      }
    previous = emitted_history[-2]
    previous_time = float(previous["time"])
    last_time = float(last["time"])
    if last_time <= previous_time:
      return {
        **last,
        "time": time_key,
      }
    horizon = time_key - last_time
    if horizon < 0 or horizon > (last_time - previous_time) * 2.5:
      return {
        **last,
        "time": time_key,
      }
    scale = horizon / (last_time - previous_time)
    return {
      **last,
      "time": time_key,
      "x": min(max(float(last["x"]) + ((float(last["x"]) - float(previous["x"])) * scale), 0.0), 1.0),
      "y": min(max(float(last["y"]) + ((float(last["y"]) - float(previous["y"])) * scale), 0.0), 1.0),
    }

  def lane_snapshot(point: dict[str, Any] | None) -> dict[str, Any] | None:
    if not point:
      return None
    return {
      "x": float(point["x"]),
      "y": float(point["y"]),
      "confidence": float(point.get("confidence") or 0.0),
      **(
        {"trackingState": point["trackingState"]}
        if isinstance(point.get("trackingState"), str)
        else {}
      ),
    }

  def point_near_expected_lane(
    point: dict[str, Any],
    *,
    time_key: float,
  ) -> bool:
    predicted = coast_from_history(time_key) or previous_emitted
    if predicted is None:
      return True
    distance_px = _distance_px(point, predicted, width=width, height=height)
    return distance_px <= max(agreement_limit_px * 1.35, max(width, height) * 0.045)

  for key in sorted(set(auto_by_time) | set(manual_by_time)):
    manual = manual_by_time.get(key)
    automatic = auto_by_time.get(key)
    manual_confidence = float(manual.get("confidence") or 0.0) if manual else 0.0
    automatic_confidence = float(automatic.get("confidence") or 0.0) if automatic else 0.0
    manual_valid = manual is not None and manual_confidence >= 0.20
    auto_valid = automatic is not None and automatic_confidence >= 0.15
    manual_jump_px = (
      _distance_px(manual, previous_manual, width=width, height=height)
      if manual_valid and previous_manual is not None
      else None
    )
    manual_stale = bool(manual_jump_px is not None and manual_jump_px > manual_jump_limit_px)
    automatic_motion_px = (
      _distance_px(automatic, previous_automatic, width=width, height=height)
      if auto_valid and previous_automatic is not None
      else None
    )
    agreement_px = (
      _distance_px(manual, automatic, width=width, height=height)
      if manual_valid and auto_valid
      else None
    )
    selected_source = "gap"
    rejection_reason: str | None = None
    emitted: dict[str, Any] | None = None
    rejected_stationary_hardware = False

    if (
      manual_valid
      and not manual_stale
      and manual_jump_px is not None
      and automatic_motion_px is not None
      and manual_jump_px <= stationary_motion_limit_px
      and automatic_motion_px >= active_bar_motion_px
      and agreement_px is not None
      and agreement_px > agreement_limit_px
    ):
      manual_stale = True
      rejected_stationary_hardware = True
      stationary_manual_rejection_count += 1
      rejection_reason = "manual_lane_stationary_hardware_like"

    if manual_valid and not manual_stale:
      consecutive_manual_failures = 0
      automatic_recovery_streak = 0
      if auto_valid and agreement_px is not None and agreement_px <= agreement_limit_px:
        manual_weight = 0.78
        auto_weight = 0.22
        emitted = {
          **manual,
          "x": (float(manual["x"]) * manual_weight) + (float(automatic["x"]) * auto_weight),
          "y": (float(manual["y"]) * manual_weight) + (float(automatic["y"]) * auto_weight),
          "confidence": max(manual_confidence, min(automatic_confidence, 0.85)),
          "manual_assisted": True,
          "selectedSource": "manual_pin_blend",
        }
        selected_source = "manual_pin_blend"
      else:
        emitted = {
          **manual,
          "manual_assisted": True,
          "selectedSource": "manual_pin_lane",
        }
        selected_source = "manual_pin_lane"
        if auto_valid and agreement_px is not None:
          rejection_reason = "automatic_disagrees_with_manual_lane"
    else:
      consecutive_manual_failures += 1
      if manual_stale and rejection_reason is None:
        rejection_reason = "manual_lane_temporal_jump"

    if emitted is None and auto_valid:
      automatic_needs_recovery = bool(previous_emitted is not None and (manual_stale or not manual_valid))
      automatic_recovery_allowed = True
      if automatic_needs_recovery:
        if point_near_expected_lane(automatic, time_key=key):
          automatic_recovery_streak += 1
        else:
          automatic_recovery_streak = 0
          if rejection_reason is None:
            rejection_reason = "automatic_outside_predicted_lane"
        automatic_recovery_allowed = automatic_recovery_streak >= 3

      if automatic_recovery_allowed:
        consecutive_auto_failures = 0
        emitted = {
          **automatic,
          "selectedSource": "automatic_lane",
        }
        emitted.pop("manual_assisted", None)
        selected_source = "automatic_lane"
      else:
        consecutive_auto_failures += 1
    elif emitted is None:
      consecutive_auto_failures += 1

    if emitted is None and previous_emitted is not None and consecutive_manual_failures <= 1:
      coast_base = coast_from_history(key) or previous_emitted
      emitted = {
        **coast_base,
        "time": key,
        "confidence": min(float(coast_base.get("confidence") or 0.0) * 0.75, 0.42),
        "trackingState": "estimated",
        "manual_assisted": True,
        "selectedSource": "kinematic_coast",
      }
      selected_source = "kinematic_coast"

    if emitted is not None:
      emitted = {
        **emitted,
        "selectedSource": selected_source,
        "coastingFrame": selected_source == "kinematic_coast",
        "stationaryHardwareRejected": rejected_stationary_hardware,
      }
      if rejection_reason:
        emitted["rejectionReason"] = rejection_reason
      else:
        emitted.pop("rejectionReason", None)
      path_residual_px = agreement_px if rejected_stationary_hardware else manual_jump_px
      if path_residual_px is not None:
        emitted["pathResidualPx"] = float(path_residual_px)
      else:
        emitted.pop("pathResidualPx", None)
      pin_lane = lane_snapshot(manual)
      emitted.pop("pinLane", None)
      if pin_lane is not None:
        emitted["pinLane"] = pin_lane
      automatic_lane = lane_snapshot(automatic)
      emitted.pop("automaticLane", None)
      if automatic_lane is not None:
        emitted["automaticLane"] = automatic_lane
      source_counts[selected_source] = source_counts.get(selected_source, 0) + 1
      fused.append(emitted)
      previous_emitted = emitted
      emitted_history.append(emitted)
      if len(emitted_history) > 4:
        emitted_history = emitted_history[-4:]
    else:
      source_counts["gap"] = source_counts.get("gap", 0) + 1

    if manual_valid and not manual_stale:
      previous_manual = manual
    if auto_valid:
      previous_automatic = automatic

    if len(frames) < 120:
      frames.append({
        "time": key,
        "manual_pin_x": round(float(manual["x"]) * width, 2) if manual else None,
        "manual_pin_y": round(float(manual["y"]) * height, 2) if manual else None,
        "manual_pin_confidence": round(manual_confidence, 3) if manual else 0.0,
        "automatic_x": round(float(automatic["x"]) * width, 2) if automatic else None,
        "automatic_y": round(float(automatic["y"]) * height, 2) if automatic else None,
        "automatic_confidence": round(automatic_confidence, 3) if automatic else 0.0,
        "emitted_x": round(float(emitted["x"]) * width, 2) if emitted else None,
        "emitted_y": round(float(emitted["y"]) * height, 2) if emitted else None,
        "emitted_confidence": round(float(emitted.get("confidence") or 0.0), 3) if emitted else 0.0,
        "selected_source": selected_source,
        "rejection_reason": rejection_reason,
        "rejected_stationary_hardware": rejected_stationary_hardware,
        "coasting_frame": selected_source == "kinematic_coast",
        "visual_agreement_px": round(agreement_px, 2) if agreement_px is not None else None,
        "path_residual_px": round(
          agreement_px if rejected_stationary_hardware else manual_jump_px,
          2,
        ) if (agreement_px if rejected_stationary_hardware else manual_jump_px) is not None else None,
        "automatic_motion_px": round(automatic_motion_px, 2) if automatic_motion_px is not None else None,
        "consecutive_manual_failures": consecutive_manual_failures,
        "consecutive_auto_failures": consecutive_auto_failures,
        "automatic_recovery_streak": automatic_recovery_streak,
      })

  return fused, {
    "enabled": True,
    "manual_lane_point_count": len(manual_points),
    "automatic_lane_point_count": len(automatic_points),
    "emitted_point_count": len(fused),
    "stationary_manual_rejection_count": stationary_manual_rejection_count,
    "source_counts": source_counts,
    "frames": frames,
  }


class BarbellTracker:
  def __init__(self) -> None:
    self.bootstrap_diagnostics: dict[str, Any] = {"frames": []}
    self.manual_seed_count = 0
    self.manual_point_count = 0
    self.automatic_point_count = 0
    self.manual_accepted_count = 0
    self.manual_blended_count = 0
    self.manual_rejected_count = 0
    self.manual_fallback_count = 0
    self.manual_rejection_reason_counts: dict[str, int] = {}

  @staticmethod
  def _manual_prior_is_plausible(
    prior: dict[str, float] | None,
    *,
    bounds: tuple[float, float, float, float],
    shoulder: tuple[float, float] | None,
    previous_point: tuple[float, float] | None = None,
    reference_shoulder_offset: tuple[float, float] | None = None,
    width: int,
    height: int,
  ) -> bool:
    if not prior or float(prior.get("confidence") or 0.0) < 0.42:
      return False
    x = float(prior.get("x") or 0.0) * width
    y = float(prior.get("y") or 0.0) * height
    x0, y0, x1, y1 = bounds
    margin = max(width, height) * 0.04
    if not (x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin):
      return False
    if shoulder and math.hypot(x - shoulder[0], y - shoulder[1]) > max(width, height) * 0.34:
      return False
    if shoulder and reference_shoulder_offset:
      shoulder_offset = (x - shoulder[0], y - shoulder[1])
      if math.hypot(
        shoulder_offset[0] - reference_shoulder_offset[0],
        shoulder_offset[1] - reference_shoulder_offset[1],
      ) > max(18.0, max(width, height) * 0.05):
        return False
    if previous_point and math.hypot(x - previous_point[0], y - previous_point[1]) > max(width, height) * 0.12:
      return False
    return True

  def _plate_color_signature(
    self,
    cv2: Any,
    frame: Any,
    plate: Candidate,
  ) -> tuple[float, float, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = gray.copy()
    mask[:] = 0
    center = (int(round(plate.x)), int(round(plate.y)))
    cv2.circle(mask, center, max(int(round(plate.radius * 0.72)), 2), 255, -1)
    cv2.circle(mask, center, max(int(round(plate.radius * 0.28)), 1), 0, -1)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    mean_l, mean_a, mean_b, _ = cv2.mean(lab, mask=mask)
    return mean_l / 255.0, mean_a / 255.0, mean_b / 255.0

  def _plate_color_similarity(
    self,
    current: tuple[float, float, float],
    historical: tuple[float, float, float] | None,
  ) -> float:
    if historical is None:
      return 0.0
    distance = math.sqrt(
      ((current[0] - historical[0]) * 0.3) ** 2
      + (current[1] - historical[1]) ** 2
      + (current[2] - historical[2]) ** 2
    )
    return max(0.0, 1.0 - (distance / 0.18))

  def _target_hub_point(
    self,
    result: dict[str, Any],
    *,
    plate: Candidate,
    shoulder: tuple[float, float] | None,
    height: int,
  ) -> tuple[float, float] | None:
    candidates = list(result.get("candidates") or [])
    plausible = [
      candidate
      for candidate in candidates
      if candidate.get("point") is not None
      and candidate.get("reason") is None
      and float(candidate.get("confidence") or 0.0) >= 0.74
      and _point_inside_plate(candidate["point"], plate=plate, max_radius_ratio=0.58)
    ]
    if not plausible:
      point = result.get("point")
      return (float(point[0]), float(point[1])) if point is not None else None

    selected = max(
      plausible,
      key=lambda candidate: (
        float(candidate.get("confidence") or 0.0)
        + (
          max(0.0, 1.0 - abs(float(candidate["point"][1]) - shoulder[1]) / max(height * 0.14, 1.0))
          * 0.38
          if shoulder is not None
          else 0.0
        )
      ),
    )
    return float(selected["point"][0]), float(selected["point"][1])

  def _record_bootstrap_diagnostic(
    self,
    *,
    frame_index: int,
    tracking_mode: str,
    detection_diagnostics: dict[str, Any],
    shoulder: tuple[float, float] | None,
    wrist_points: list[tuple[float, float]],
    selected_plate: Candidate | None,
  ) -> dict[str, Any] | None:
    frames = self.bootstrap_diagnostics.setdefault("frames", [])
    if len(frames) >= 10:
      return None

    crop_x0, crop_y0, crop_x1, crop_y1 = detection_diagnostics["crop_bounds"]
    diagnostic = {
      "frame_index": frame_index,
      "tracking_mode": tracking_mode,
      "crop_anchor_landmark": detection_diagnostics["anchor_landmark"],
      "crop_anchor_x": round(shoulder[0], 2) if shoulder else None,
      "crop_anchor_y": round(shoulder[1], 2) if shoulder else None,
      "crop_x0": round(crop_x0, 2),
      "crop_y0": round(crop_y0, 2),
      "crop_x1": round(crop_x1, 2),
      "crop_y1": round(crop_y1, 2),
      "wrist_points": [(round(x, 2), round(y, 2)) for x, y in wrist_points],
      "wrist_rejected_count": int(detection_diagnostics["wrist_rejected_count"]),
      "winning_candidate_x": round(selected_plate.x, 2) if selected_plate else None,
      "winning_candidate_y": round(selected_plate.y, 2) if selected_plate else None,
    }
    frames.append(diagnostic)
    return diagnostic

  def _log_bootstrap_diagnostic(self, diagnostic: dict[str, Any]) -> None:
    if diagnostic["winning_candidate_x"] is None:
      logger.info(
        "Barbell bootstrap frame %s: crop_anchor=%s anchor=(%s, %s) crop=(%s, %s, %s, %s) winning_candidate=None wrist_points=%s",
        diagnostic["frame_index"],
        diagnostic["crop_anchor_landmark"],
        diagnostic["crop_anchor_x"],
        diagnostic["crop_anchor_y"],
        diagnostic["crop_x0"],
        diagnostic["crop_y0"],
        diagnostic["crop_x1"],
        diagnostic["crop_y1"],
        diagnostic["wrist_points"],
      )
      return

    logger.info(
      "Barbell bootstrap frame %s: crop_anchor=%s anchor=(%s, %s) crop=(%s, %s, %s, %s) winning_candidate=(%s, %s) wrist_points=%s",
      diagnostic["frame_index"],
      diagnostic["crop_anchor_landmark"],
      diagnostic["crop_anchor_x"],
      diagnostic["crop_anchor_y"],
      diagnostic["crop_x0"],
      diagnostic["crop_y0"],
      diagnostic["crop_x1"],
      diagnostic["crop_y1"],
      diagnostic["winning_candidate_x"],
      diagnostic["winning_candidate_y"],
      diagnostic["wrist_points"],
    )

  def _record_tracking_frame_diagnostic(
    self,
    *,
    frame_index: int,
    timestamp: float,
    tracking_mode: str,
    selected_plate: Candidate | None,
    final_bar_point: tuple[float, float] | None,
    pose_predicted_point: tuple[float, float] | None,
    predicted_collar: tuple[float, float] | None,
    refined_collar: tuple[float, float] | None,
    point: dict[str, float] | None,
    width: int,
    height: int,
    local_tracker_type: str | None,
    optical_flow_inlier_count: int,
    template_match_score: float | None,
    collar_rejection_reason: str | None,
    point_source: str,
    final_bar_reason: str | None = None,
    final_bar_confidence: float = 0.0,
    final_bar_source: str | None = None,
    fallback_used: bool = False,
    path_residual_px: float | None = None,
    collar_descriptor_score: float | None = None,
  ) -> dict[str, Any] | None:
    frames = self.bootstrap_diagnostics.setdefault("tracking_frames", [])
    if len(frames) >= 20:
      return None

    emitted_x = point.get("x") if point else None
    emitted_y = point.get("y") if point else None
    diagnostic = {
      "frame_index": frame_index,
      "timestamp": round(timestamp, 4),
      "tracking_mode": tracking_mode,
      "selected_plate_x": round(selected_plate.x, 2) if selected_plate else None,
      "selected_plate_y": round(selected_plate.y, 2) if selected_plate else None,
      "selected_plate_radius": round(selected_plate.radius, 2) if selected_plate else None,
      "final_bar_point_x": round(final_bar_point[0], 2) if final_bar_point else None,
      "final_bar_point_y": round(final_bar_point[1], 2) if final_bar_point else None,
      "pose_predicted_bar_x": round(pose_predicted_point[0], 2) if pose_predicted_point else None,
      "pose_predicted_bar_y": round(pose_predicted_point[1], 2) if pose_predicted_point else None,
      "predicted_collar_x": round(predicted_collar[0], 2) if predicted_collar else None,
      "predicted_collar_y": round(predicted_collar[1], 2) if predicted_collar else None,
      "refined_collar_x": round(refined_collar[0], 2) if refined_collar else None,
      "refined_collar_y": round(refined_collar[1], 2) if refined_collar else None,
      "emitted_normalized_x": round(emitted_x, 4) if emitted_x is not None else None,
      "emitted_normalized_y": round(emitted_y, 4) if emitted_y is not None else None,
      "emitted_pixel_x": round(emitted_x * width, 2) if emitted_x is not None else None,
      "emitted_pixel_y": round(emitted_y * height, 2) if emitted_y is not None else None,
      "local_tracker_type": local_tracker_type,
      "optical_flow_inlier_count": optical_flow_inlier_count,
      "template_match_score": round(template_match_score, 4) if template_match_score is not None else None,
      "collar_rejection_reason": collar_rejection_reason,
      "point_source": point_source,
      "final_bar_reason": final_bar_reason,
      "final_bar_confidence": round(final_bar_confidence, 3),
      "final_bar_source": final_bar_source,
      "fallback_used": fallback_used,
      "path_residual_px": round(path_residual_px, 2) if path_residual_px is not None else None,
      "collar_descriptor_score": round(collar_descriptor_score, 3) if collar_descriptor_score is not None else None,
    }
    frames.append(diagnostic)
    logger.info(
      "[BARBELL_TRACK_DIAG] frame=%s time=%.4f mode=%s source=%s plate=(%s, %s r=%s) final=(%s, %s) final_reason=%s final_conf=%s final_source=%s fallback=%s pose_pred=(%s, %s) predicted=(%s, %s) refined=(%s, %s) emitted_norm=(%s, %s) emitted_px=(%s, %s) local=%s flow_inliers=%s template=%s collar_reason=%s path_residual=%s collar_descriptor=%s",
      diagnostic["frame_index"],
      diagnostic["timestamp"],
      diagnostic["tracking_mode"],
      diagnostic["point_source"],
      diagnostic["selected_plate_x"],
      diagnostic["selected_plate_y"],
      diagnostic["selected_plate_radius"],
      diagnostic["final_bar_point_x"],
      diagnostic["final_bar_point_y"],
      diagnostic["final_bar_reason"],
      diagnostic["final_bar_confidence"],
      diagnostic["final_bar_source"],
      diagnostic["fallback_used"],
      diagnostic["pose_predicted_bar_x"],
      diagnostic["pose_predicted_bar_y"],
      diagnostic["predicted_collar_x"],
      diagnostic["predicted_collar_y"],
      diagnostic["refined_collar_x"],
      diagnostic["refined_collar_y"],
      diagnostic["emitted_normalized_x"],
      diagnostic["emitted_normalized_y"],
      diagnostic["emitted_pixel_x"],
      diagnostic["emitted_pixel_y"],
      diagnostic["local_tracker_type"],
      diagnostic["optical_flow_inlier_count"],
      diagnostic["template_match_score"],
      diagnostic["collar_rejection_reason"],
      diagnostic["path_residual_px"],
      diagnostic["collar_descriptor_score"],
    )
    return diagnostic

  def _pose_predicted_bar_point(
    self,
    previous: dict[str, Any] | None,
    shoulder: tuple[float, float] | None,
  ) -> tuple[float, float] | None:
    if not previous or not shoulder:
      return None

    if "final_bar_dx" not in previous or "final_bar_dy" not in previous:
      return None

    return shoulder[0] + float(previous["final_bar_dx"]), shoulder[1] + float(previous["final_bar_dy"])

  def _final_bar_point_from_plate(
    self,
    cv2: Any,
    frame: Any,
    *,
    plate: Candidate,
    previous: dict[str, Any] | None,
  ) -> dict[str, Any]:
    result = _detect_hub_point(
      cv2,
      frame,
      plate=plate,
      previous=previous,
    )
    point = result.get("point")
    if point is not None and not _point_inside_plate(point, plate=plate, max_radius_ratio=0.58):
      rejected_candidates = list(result.get("rejected_candidates") or [])
      rejected_candidates.append(
        {
          "point": point,
          "radius": 0.0,
          "confidence": float(result.get("confidence") or 0.0),
          "reason": "hub_outside_plate_region",
        }
      )
      return {
        **result,
        "point": None,
        "confidence": 0.0,
        "reason": "hub_outside_plate_region",
        "source": "no_hub",
        "rejected_candidates": rejected_candidates,
      }

    return result

  def _hub_result_is_emit_safe(self, result: dict[str, Any] | None) -> bool:
    if not result:
      return False
    if result.get("point") is None:
      return False
    if result.get("source") != "hough_hub":
      return False
    if result.get("reason") in UNSAFE_HUB_REASONS:
      return False
    if result.get("reason") is not None:
      return False
    return float(result.get("confidence") or 0.0) >= MIN_HUB_CONFIDENCE

  def _collar_descriptor_from_plate(
    self,
    cv2: Any,
    frame: Any,
    *,
    plate: Candidate,
    previous: dict[str, Any] | None,
    shoulder: tuple[float, float] | None,
    width: int,
    height: int,
    bootstrapping: bool,
  ) -> dict[str, Any]:
    predicted_collar, sleeve_direction = _estimate_collar_from_plate(
      plate,
      shoulder=shoulder,
      width=width,
      height=height,
      previous=previous,
    )
    refined_collar, collar_confidence_penalty, collar_refinement_reason = _refine_collar_point(
      cv2,
      frame,
      predicted=predicted_collar,
      plate=plate,
      sleeve_direction=sleeve_direction,
      previous=previous,
    )
    geometry_reason = _validate_collar_geometry(
      refined_collar,
      plate=plate,
      sleeve_direction=sleeve_direction,
      previous=previous,
    )
    final_collar = refined_collar
    fallback_used = False
    rejection_reason = geometry_reason or collar_refinement_reason
    if rejection_reason:
      fallback_used = True
      final_collar = predicted_collar
      predicted_geometry_reason = _validate_collar_geometry(
        final_collar,
        plate=plate,
        sleeve_direction=sleeve_direction,
        previous=previous,
      )
      rejection_reason = predicted_geometry_reason or rejection_reason

    collar_descriptor_score = _score_collar_patch(
      cv2,
      frame,
      collar=final_collar,
      plate=plate,
      sleeve_direction=sleeve_direction,
    )
    hub_result = self._final_bar_point_from_plate(
      cv2,
      frame,
      plate=plate,
      previous=previous,
    )
    hub_safe = self._hub_result_is_emit_safe(hub_result)
    hub_confidence = float(hub_result.get("confidence") or 0.0)
    target_hub_point = self._target_hub_point(
      hub_result,
      plate=plate,
      shoulder=shoulder,
      height=height,
    )

    min_descriptor_score = (
      MIN_BOOTSTRAP_COLLAR_DESCRIPTOR_SCORE
      if bootstrapping
      else MIN_COLLAR_DESCRIPTOR_SCORE
    )
    if collar_descriptor_score < min_descriptor_score:
      rejection_reason = rejection_reason or "low_collar_descriptor_score"
    if bootstrapping and not hub_safe:
      rejection_reason = rejection_reason or hub_result.get("reason") or "hub_not_confirmed"

    confidence = max(
      min(
        (collar_descriptor_score * 0.55)
        + (hub_confidence * 0.25)
        + (plate.confidence * 0.2)
        - collar_confidence_penalty,
        1.0,
      ),
      0.0,
    )
    return {
      "plate": plate,
      "predicted_collar": predicted_collar,
      "refined_collar": final_collar,
      "sleeve_direction": sleeve_direction,
      "final_bar_point": final_collar,
      "final_bar_confidence": confidence,
      "final_bar_reason": rejection_reason,
      "final_bar_source": "collar_descriptor",
      "collar_descriptor_score": collar_descriptor_score,
      "hub_result": hub_result,
      "hub_safe": hub_safe,
      "fallback_used": fallback_used,
      "collar_geometry_valid": rejection_reason is None,
      "plate_color_signature": self._plate_color_signature(cv2, frame, plate),
      "target_point": target_hub_point or (plate.x, plate.y),
    }

  def _final_bar_point_is_motion_consistent(
    self,
    point: tuple[float, float],
    *,
    previous: dict[str, Any] | None,
    shoulder: tuple[float, float] | None,
    width: int,
    height: int,
  ) -> str | None:
    if not previous:
      return None

    previous_point = (
      float(previous.get("final_bar_x", previous.get("x", point[0]))),
      float(previous.get("final_bar_y", previous.get("y", point[1]))),
    )
    jump_distance = math.hypot(point[0] - previous_point[0], point[1] - previous_point[1])
    if jump_distance > max(width, height) * 0.16:
      return "final_bar_absolute_jump"

    predicted = self._pose_predicted_bar_point(previous, shoulder)
    if predicted:
      pose_relative_jump = math.hypot(point[0] - predicted[0], point[1] - predicted[1])
      if pose_relative_jump > max(width, height) * 0.1:
        return "final_bar_pose_relative_jump"

    previous_shoulder_x = previous.get("shoulder_x")
    previous_shoulder_y = previous.get("shoulder_y")
    if previous_shoulder_x is not None and previous_shoulder_y is not None and shoulder:
      shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y)
      point_motion = jump_distance
      if shoulder_motion >= 6.0 and point_motion <= 1.0:
        return "stationary_hardware_like"

    return None

  def _fit_recent_path(self, points: list[tuple[float, float]]) -> dict[str, Any] | None:
    recent_points = points[-PATH_PRIOR_WINDOW_POINTS:]
    if len(recent_points) < PATH_PRIOR_MIN_POINTS:
      return None

    mean_x = sum(point[0] for point in recent_points) / len(recent_points)
    mean_y = sum(point[1] for point in recent_points) / len(recent_points)
    centered = [(point[0] - mean_x, point[1] - mean_y) for point in recent_points]
    xx = sum(point[0] * point[0] for point in centered) / len(centered)
    yy = sum(point[1] * point[1] for point in centered) / len(centered)
    xy = sum(point[0] * point[1] for point in centered) / len(centered)
    total_variance = xx + yy
    if total_variance < 1.0:
      return None

    angle = 0.5 * math.atan2(2 * xy, xx - yy)
    direction = (math.cos(angle), math.sin(angle))
    normal = (-direction[1], direction[0])
    along_values = [(point[0] * direction[0]) + (point[1] * direction[1]) for point in centered]
    along_span = max(along_values) - min(along_values)
    if along_span < 6.0:
      return None

    residuals = [abs((point[0] * normal[0]) + (point[1] * normal[1])) for point in centered]
    return {
      "center": (mean_x, mean_y),
      "normal": normal,
      "mean_residual": sum(residuals) / len(residuals),
      "max_residual": max(residuals),
    }

  def _path_prior_residual(
    self,
    point: tuple[float, float],
    accepted_points: list[tuple[float, float]],
  ) -> tuple[float | None, dict[str, Any] | None]:
    model = self._fit_recent_path(accepted_points)
    if not model:
      return None, None

    center = model["center"]
    normal = model["normal"]
    residual = abs(((point[0] - center[0]) * normal[0]) + ((point[1] - center[1]) * normal[1]))
    return residual, model

  def _path_prior_rejection_reason(
    self,
    point: tuple[float, float],
    accepted_points: list[tuple[float, float]],
    *,
    timestamp: float,
    last_accepted_timestamp: float | None,
    max_dimension: int,
    shoulder_motion_px: float = 0.0,
  ) -> tuple[str | None, float | None, dict[str, Any] | None]:
    elapsed_seconds = (
      max(timestamp - last_accepted_timestamp, 0.0)
      if last_accepted_timestamp is not None
      else 0.0
    )
    if last_accepted_timestamp is not None and elapsed_seconds > STALE_PATH_RESET_SECONDS:
      return None, None, None

    if accepted_points:
      recent_distance = math.hypot(point[0] - accepted_points[-1][0], point[1] - accepted_points[-1][1])
      allowed_jump = max(
        RECENT_POINT_MAX_JUMP_PX,
        RECENT_POINT_MAX_JUMP_PX
        + (max_dimension * MAX_BAR_SPEED_FRAME_RATIO_PER_SECOND * elapsed_seconds)
        + (shoulder_motion_px * 1.5),
      )
      allowed_jump = min(allowed_jump, max_dimension * 0.18)
      if recent_distance > allowed_jump:
        return "target_switch_jump", recent_distance, None

    residual, model = self._path_prior_residual(point, accepted_points)
    if residual is None:
      return None, None, model

    if residual > PATH_PRIOR_MAX_RESIDUAL_PX:
      return "path_residual_drift", residual, model

    return None, residual, model

  def _fresh_plate_candidate(
    self,
    cv2: Any,
    frame: Any,
    *,
    bounds: tuple[float, float, float, float],
    previous: dict[str, Any],
    shoulder: tuple[float, float] | None,
    width: int,
    height: int,
  ) -> Candidate | None:
    predicted_bar = self._pose_predicted_bar_point(previous, shoulder)
    candidates, _, _, _ = _detect_crop_candidates(
      cv2,
      frame,
      bounds,
      shoulder=shoulder,
    )
    candidates = [candidate for candidate in candidates if _candidate_in_bounds(candidate, bounds)]
    plausible: list[Candidate] = []
    for candidate in candidates:
      if predicted_bar:
        predicted_distance = math.hypot(candidate.x - predicted_bar[0], candidate.y - predicted_bar[1])
        if predicted_distance > max(previous["plate"].radius * 0.78, max(width, height) * 0.075):
          continue
      if _plate_rejection_reason(
        candidate,
        previous=previous,
        shoulder=shoulder,
        width=width,
        height=height,
        bootstrapping=False,
      ):
        continue
      plausible.append(candidate)

    if not plausible:
      return None

    previous_plate = previous["plate"]
    max_distance = max(max(width, height) * 0.14, previous_plate.radius * 0.9)
    near_previous = [
      candidate
      for candidate in plausible
      if math.hypot(candidate.x - previous_plate.x, candidate.y - previous_plate.y) <= max_distance
    ]
    if not near_previous:
      return None

    return max(
      near_previous,
      key=lambda candidate: (
        _score_plate_candidate(
          candidate,
          previous=previous,
          shoulder=shoulder,
          width=width,
          height=height,
        )
        - (math.hypot(candidate.x - previous_plate.x, candidate.y - previous_plate.y) / max(max_distance, 1.0))
        - (
          math.hypot(candidate.x - predicted_bar[0], candidate.y - predicted_bar[1])
          / max(max_distance, 1.0)
          if predicted_bar
          else 0.0
        )
      ),
    )

  def _visible_hub_for_manual_proposal(
    self,
    cv2: Any,
    frame: Any,
    *,
    manual_point: tuple[float, float],
    bounds: tuple[float, float, float, float],
    previous: dict[str, Any] | None,
    shoulder: tuple[float, float] | None,
    width: int,
    height: int,
  ) -> dict[str, Any] | None:
    candidates, _, _, _ = _detect_crop_candidates(
      cv2,
      frame,
      bounds,
      shoulder=shoulder,
    )
    descriptors: list[dict[str, Any]] = []
    for candidate in candidates:
      if not _candidate_in_bounds(candidate, bounds):
        continue
      if _plate_rejection_reason(
        candidate,
        previous=previous,
        shoulder=shoulder,
        width=width,
        height=height,
        bootstrapping=previous is None,
      ):
        continue
      descriptor = self._collar_descriptor_from_plate(
        cv2,
        frame,
        plate=candidate,
        previous=previous,
        shoulder=shoulder,
        width=width,
        height=height,
        bootstrapping=True,
      )
      if descriptor["final_bar_reason"] is not None or not descriptor["hub_safe"]:
        continue
      sleeve_direction = descriptor["sleeve_direction"]
      sleeve_normal = (-sleeve_direction[1], sleeve_direction[0])
      refined_collar = descriptor["refined_collar"]
      guided_target_point = (
        refined_collar[0]
        - (sleeve_direction[0] * candidate.radius * 0.07)
        - (sleeve_normal[0] * candidate.radius * 0.18),
        refined_collar[1]
        - (sleeve_direction[1] * candidate.radius * 0.07)
        - (sleeve_normal[1] * candidate.radius * 0.18),
      )
      descriptor["guided_target_point"] = guided_target_point
      target_point = guided_target_point
      if previous is None:
        if math.hypot(target_point[0] - manual_point[0], target_point[1] - manual_point[1]) > max(
          40.0,
          max(width, height) * 0.16,
        ):
          continue
      else:
        previous_target = previous.get("display_target_point") or (
          previous["plate"].x,
          previous["plate"].y,
        )
        if math.hypot(target_point[0] - previous_target[0], target_point[1] - previous_target[1]) > max(
          previous["plate"].radius * 0.95,
          max(width, height) * 0.12,
        ):
          continue
      descriptors.append(descriptor)

    if not descriptors:
      return None
    return min(
      descriptors,
      key=lambda descriptor: (
        math.hypot(
          descriptor["guided_target_point"][0] - manual_point[0],
          descriptor["guided_target_point"][1] - manual_point[1],
        )
        - (float(descriptor["final_bar_confidence"]) * 8.0)
      ),
    )

  def track(
    self,
    file_path: str,
    *,
    pose_frames: list[dict[str, Any]],
    frame_step: int,
    processed_width: int | None,
    processed_height: int | None,
    selected_side: str | None = None,
    rep_windows: list[dict[str, Any]] | None = None,
    manual_barbell_priors: dict[int, dict[str, float]] | None = None,
    debug_output_path: str | None = None,
  ) -> dict[str, Any]:
    import cv2

    self.bootstrap_diagnostics = {"frames": []}
    self.manual_seed_count = 0
    self.manual_point_count = 0
    self.automatic_point_count = 0
    self.manual_accepted_count = 0
    self.manual_blended_count = 0
    self.manual_rejected_count = 0
    self.manual_fallback_count = 0
    self.manual_rejection_reason_counts = {}
    normalized_manual_priors = manual_barbell_priors or {}
    manual_priors_have_reference = any(
      prior.get("tracking_state") == "reference"
      for prior in normalized_manual_priors.values()
    )
    pin_lane_result: dict[str, Any] | None = None
    started = time.perf_counter()
    if not Path(file_path).is_file():
      return _empty_result("video_unavailable")

    capture = cv2.VideoCapture(file_path)
    if not capture.isOpened():
      return _empty_result("video_unavailable")

    if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
      capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    width = processed_width or frame_width
    height = processed_height or frame_height
    if width <= 0 or height <= 0:
      capture.release()
      return _empty_result("invalid_video_dimensions")
    coordinate_space = {
      "width": int(width),
      "height": int(height),
      "source": "processed_frame",
    }
    normalized_selected_side = selected_side if selected_side in {"left", "right"} else None
    normalized_rep_windows = sorted(
      [
        {
          "rep_index": int(window.get("rep_index", index)),
          "start": float(window["start"]),
          "bottom": float(window["bottom"]),
          "end": float(window["end"]),
        }
        for index, window in enumerate(rep_windows or [], start=1)
        if window.get("start") is not None
        and window.get("bottom") is not None
        and window.get("end") is not None
      ],
      key=lambda window: window["start"],
    )

    pose_frame_step = max(int(frame_step or 1), 1)
    target_frame_step = max(int(round(fps / BARBELL_TRACK_TARGET_FPS)), 1) if fps > 0 else pose_frame_step
    tracking_frame_step = pose_frame_step * max(int(round(target_frame_step / pose_frame_step)), 1)
    pose_by_source_index = {
      int(frame.get("source_frame_index", -1)): frame
      for frame in pose_frames
      if frame.get("source_frame_index") is not None
    }
    pose_source_indices = sorted(pose_by_source_index)
    if not pose_by_source_index:
      capture.release()
      return _empty_result(
        "no_pose_frames",
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        selected_side=normalized_selected_side,
        coordinate_space=coordinate_space,
      )

    sleeve_result = (
      track_unloaded_sleeve_end(
        file_path,
        pose_frames=pose_frames,
        frame_step=frame_step,
        processed_width=width,
        processed_height=height,
        selected_side=normalized_selected_side,
        rep_windows=normalized_rep_windows,
      )
      if not normalized_manual_priors
      and normalized_rep_windows
      and width <= 720
      and height <= 1280
      else None
    )
    if (
      sleeve_result is not None
      and float(sleeve_result.get("barbellPath", {}).get("coverage") or 0.0) >= 0.18
    ):
      capture.release()
      return sleeve_result

    if normalized_manual_priors and manual_priors_have_reference:
      pin_result, pin_diagnostics = build_pin_assisted_barbell_result(
        manual_priors=normalized_manual_priors,
        pose_source_indices=pose_source_indices,
        fps=fps,
        width=width,
        height=height,
        tracking_frame_step=tracking_frame_step,
        rep_windows=normalized_rep_windows,
        selected_side=normalized_selected_side,
        coordinate_space=coordinate_space,
        started_at=started,
      )
      pin_lane_result = pin_result
      self.bootstrap_diagnostics["pin_assisted"] = pin_diagnostics
      if pin_result is not None:
        pin_tracking_diagnostics = pin_result.get("diagnostics") or {}
        pin_diagnostics["pin_assisted_primary"] = False
        pin_diagnostics["pin_assisted_fallback_reason"] = "delegated_to_robust_tracker"
        pin_diagnostics["raw_pin_only_point_count"] = len(pin_result.get("barbellPath", {}).get("points") or [])
        pin_diagnostics["raw_pin_only_coverage"] = pin_tracking_diagnostics.get("coverage")
      pin_source_counts = pin_diagnostics.setdefault("pin_source_counts", {})
      pin_source_counts["automatic_fallback"] = int(pin_source_counts.get("automatic_fallback") or 0) + 1

    manual_prior_indices = sorted(int(index) for index in normalized_manual_priors)
    manual_prior_search_radius = max(0, int(math.floor(tracking_frame_step / 2)))
    manual_prior_index_diagnostics: dict[str, Any] = {
      "manual_prior_min_index": manual_prior_indices[0] if manual_prior_indices else None,
      "manual_prior_max_index": manual_prior_indices[-1] if manual_prior_indices else None,
      "pose_source_min_index": pose_source_indices[0] if pose_source_indices else None,
      "pose_source_max_index": pose_source_indices[-1] if pose_source_indices else None,
      "tracking_frame_step": tracking_frame_step,
      "nearest_search_radius": manual_prior_search_radius,
      "exact_match_count": 0,
      "nearest_match_count": 0,
      "nearest_miss_count": 0,
      "nearest_prior_max_distance": 0,
      "frames": [],
    }

    def manual_prior_for_frame(frame_index: int) -> dict[str, Any] | None:
      if frame_index in normalized_manual_priors:
        manual_prior_index_diagnostics["exact_match_count"] += 1
        prior = dict(normalized_manual_priors[frame_index])
        prior["_matched_prior_index"] = frame_index
        prior["_prior_frame_distance"] = 0
        return prior
      if not manual_prior_indices:
        return None

      insertion = bisect_left(manual_prior_indices, frame_index)
      candidate_indices: list[int] = []
      if insertion < len(manual_prior_indices):
        candidate_indices.append(manual_prior_indices[insertion])
      if insertion > 0:
        candidate_indices.append(manual_prior_indices[insertion - 1])
      nearest_index = min(
        candidate_indices,
        key=lambda index: abs(index - frame_index),
      ) if candidate_indices else None
      if nearest_index is None:
        manual_prior_index_diagnostics["nearest_miss_count"] += 1
        return None
      distance = abs(nearest_index - frame_index)
      if distance > manual_prior_search_radius:
        manual_prior_index_diagnostics["nearest_miss_count"] += 1
        return None

      manual_prior_index_diagnostics["nearest_match_count"] += 1
      manual_prior_index_diagnostics["nearest_prior_max_distance"] = max(
        int(manual_prior_index_diagnostics["nearest_prior_max_distance"] or 0),
        distance,
      )
      if len(manual_prior_index_diagnostics["frames"]) < 120:
        manual_prior_index_diagnostics["frames"].append({
          "frame_index": frame_index,
          "matched_prior_index": nearest_index,
          "distance": distance,
        })
      prior = dict(normalized_manual_priors[nearest_index])
      prior["_matched_prior_index"] = nearest_index
      prior["_prior_frame_distance"] = distance
      return prior

    samples: list[dict[str, Any] | None] = []
    non_interpolable_gap_indices: set[int] = set()
    tracking_lock: dict[str, Any] | None = None
    pending_plate: dict[str, float] | None = None
    pending_confirmation_count = 0
    pending_miss_count = 0
    previous_gray = None
    detected_count = 0
    rejected_candidate_count = 0
    rejection_reason_counts: dict[str, int] = {}
    skipped_no_pose_frame_count = 0
    reused_nearest_pose_frame_count = 0
    crop_widths: list[int] = []
    crop_heights: list[int] = []
    selected_plate: Candidate | None = None
    final_bar_point: tuple[float, float] | None = None
    final_bar_confidence = 0.0
    final_bar_reason: str | None = None
    final_bar_source: str | None = None
    final_bar_reason_counts: dict[str, int] = {}
    bad_candidate_rejection_counts: dict[str, int] = {}
    collar_candidate_count = 0
    collar_descriptor_score: float | None = None
    tracklet_confirmation_count = 0
    real_hub_detection_count = 0
    hub_rejected_count = 0
    pose_predicted_point: tuple[float, float] | None = None
    predicted_collar: tuple[float, float] | None = None
    refined_collar: tuple[float, float] | None = None
    sleeve_direction: tuple[float, float] | None = None
    collar_rejection_reason: str | None = None
    collar_geometry_valid = False
    fallback_used = False
    tracking_mode = "initializing"
    has_ever_locked = False
    bootstrap_pose_relative_displacements: list[float] = []
    bootstrap_rejection_reason_counts: dict[str, int] = {}
    local_tracker_type: str | None = None
    initialization_confirmed = False
    initialization_frame_count = 0
    hough_detection_count = 0
    optical_flow_point_count = 0
    optical_flow_inlier_count = 0
    template_match_score: float | None = None
    local_tracking_confidence = 0.0
    accepted_local_tracking_count = 0
    fresh_hough_correction_count = 0
    stationary_hardware_rejection_count = 0
    reacquisition_count = 0
    local_tracking_failure_count = 0
    coasted_estimated_point_count = 0
    consecutive_local_failures = 0
    consecutive_fresh_validation_failures = 0
    local_descriptor_bridge_count = 0
    accepted_points_px: list[tuple[float, float]] = []
    historical_target_point: tuple[float, float] | None = None
    historical_plate_signature: tuple[float, float, float] | None = None
    rep_anchor_x_values: list[float] = []
    last_accepted_timestamp: float | None = None
    active_rep_index: int | None = None
    path_reset_count = 0
    stale_prior_expiration_count = 0
    reacquisition_success_count = 0
    rep_sample_counts = {int(window["rep_index"]): 0 for window in normalized_rep_windows}
    rep_detected_counts = {int(window["rep_index"]): 0 for window in normalized_rep_windows}
    path_prior_rejection_count = 0
    path_prior_residuals: list[float] = []
    last_path_residual_px: float | None = None
    frame_index = 0
    debug_writer = None
    debug_frame_size = (width - (width % 2), height - (height % 2))
    sampled_shoulder_y_values: list[float] = []
    manual_mode_active = False
    manual_has_activated = False
    manual_reentry_streak = 0
    previous_manual_point: tuple[float, float] | None = None
    manual_reference_shoulder_offset: tuple[float, float] | None = None
    manual_visual_mismatch_streak = 0
    manual_visual_match_streak = 0
    manual_visual_recovery_active = False
    manual_visual_offset: tuple[float, float] | None = None
    manual_visual_offset_source: str | None = None
    manual_visual_offset_frame_index: int | None = None
    manual_visual_residuals: list[float] = []
    manual_validation_missing_count = 0
    manual_visual_recovery_emitted_count = 0
    manual_visual_recovery_gap_count = 0

    def choose_automatic_emit_point(
      *,
      final_point: tuple[float, float],
      target_point: tuple[float, float],
    ) -> tuple[float, float]:
      if not accepted_points_px:
        return target_point
      previous = accepted_points_px[-1]
      target_step = (
        target_point[0] - previous[0],
        target_point[1] - previous[1],
      )
      final_step = (
        final_point[0] - previous[0],
        final_point[1] - previous[1],
      )
      target_distance = math.hypot(target_step[0], target_step[1])
      final_distance = math.hypot(final_step[0], final_step[1])
      if final_distance + 4.0 < target_distance and target_distance > 6.0:
        return final_point
      if len(accepted_points_px) >= 2:
        previous_velocity = (
          previous[0] - accepted_points_px[-2][0],
          previous[1] - accepted_points_px[-2][1],
        )
        target_dot = (target_step[0] * previous_velocity[0]) + (target_step[1] * previous_velocity[1])
        final_dot = (final_step[0] * previous_velocity[0]) + (final_step[1] * previous_velocity[1])
        if target_dot < -1.0 and final_dot >= -1.0:
          return final_point
      return target_point

    def estimated_barbell_coast_point(
      *,
      timestamp: float,
      shoulder: tuple[float, float] | None,
      reason: str | None,
      failure_count: int,
    ) -> dict[str, Any] | None:
      if tracking_lock is None or failure_count > MAX_LOCAL_TRACKING_FAILURES:
        return None

      pose_prediction = self._pose_predicted_bar_point(tracking_lock, shoulder)
      last_visible_px: tuple[float, float] | None = None
      if samples and samples[-1] is not None:
        previous_sample = samples[-1]
        last_visible_px = (float(previous_sample["x"]) * width, float(previous_sample["y"]) * height)
      elif accepted_points_px:
        last_visible_px = accepted_points_px[-1]

      velocity_prediction: tuple[float, float] | None = None
      if len(accepted_points_px) >= 2:
        velocity_prediction = (
          accepted_points_px[-1][0] + (accepted_points_px[-1][0] - accepted_points_px[-2][0]),
          accepted_points_px[-1][1] + (accepted_points_px[-1][1] - accepted_points_px[-2][1]),
        )

      predicted_px = pose_prediction or velocity_prediction or last_visible_px
      if pose_prediction is not None and velocity_prediction is not None:
        if math.hypot(
          pose_prediction[0] - velocity_prediction[0],
          pose_prediction[1] - velocity_prediction[1],
        ) <= max(18.0, max(width, height) * 0.05):
          predicted_px = (
            (pose_prediction[0] * 0.65) + (velocity_prediction[0] * 0.35),
            (pose_prediction[1] * 0.65) + (velocity_prediction[1] * 0.35),
          )
      if predicted_px is None:
        return None
      if not (0 <= predicted_px[0] < width and 0 <= predicted_px[1] < height):
        return None

      base_confidence = float(tracking_lock.get("final_bar_confidence") or final_bar_confidence or 0.42)
      confidence = max(0.18, min(base_confidence * (0.55 ** max(failure_count, 1)), 0.38))
      return {
        "time": timestamp,
        "x": predicted_px[0] / width,
        "y": predicted_px[1] / height,
        "confidence": confidence,
        "trackingState": "estimated",
        "estimatedSource": "kinematic_coast",
        "rejectionReason": reason or "local_tracking_failed",
      }

    if debug_output_path:
      debug_writer = cv2.VideoWriter(
        debug_output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        BARBELL_TRACK_TARGET_FPS,
        debug_frame_size,
      )

    def write_debug_frame(debug_frame: Any) -> None:
      if debug_writer is None:
        return
      if (debug_frame.shape[1], debug_frame.shape[0]) != debug_frame_size:
        debug_frame = cv2.resize(debug_frame, debug_frame_size, interpolation=cv2.INTER_AREA)
      debug_writer.write(debug_frame)

    try:
      while capture.isOpened():
        success, frame = capture.read()
        if not success:
          break

        if frame_index % tracking_frame_step != 0:
          frame_index += 1
          continue

        if frame.shape[1] != width or frame.shape[0] != height:
          frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        timestamp = frame_index / fps if fps > 0 else len(samples) / 18.0
        current_rep = next(
          (
            window
            for window in normalized_rep_windows
            if window["start"] <= timestamp <= window["end"]
          ),
          None,
        )
        current_rep_index = int(current_rep["rep_index"]) if current_rep else None
        if current_rep_index is not None:
          rep_sample_counts[current_rep_index] = rep_sample_counts.get(current_rep_index, 0) + 1
        if current_rep_index != active_rep_index:
          if accepted_points_px:
            accepted_points_px = []
            path_reset_count += 1
          rep_anchor_x_values = []
          active_rep_index = current_rep_index

        if (
          last_accepted_timestamp is not None
          and timestamp - last_accepted_timestamp > STALE_PATH_RESET_SECONDS
          and accepted_points_px
        ):
          accepted_points_px = []
          path_reset_count += 1
          stale_prior_expiration_count += 1
        if normalized_rep_windows and current_rep is None:
          tracking_lock = None
          manual_mode_active = False
          manual_reentry_streak = 0
          previous_manual_point = None
          pending_plate = None
          pending_confirmation_count = 0
          pending_miss_count = 0
          previous_gray = None
          consecutive_local_failures = 0
          frame_index += 1
          continue
        pose_frame = pose_by_source_index.get(frame_index)
        if not pose_frame:
          insertion_index = bisect_left(pose_source_indices, frame_index)
          nearby_pose_indices = pose_source_indices[
            max(insertion_index - 1, 0):min(insertion_index + 1, len(pose_source_indices))
          ]
          nearest_pose_index = (
            min(nearby_pose_indices, key=lambda index: abs(index - frame_index))
            if nearby_pose_indices
            else None
          )
          max_pose_distance_frames = max(int(round(fps * 0.75)), tracking_frame_step * 2)
          if (
            nearest_pose_index is not None
            and abs(nearest_pose_index - frame_index) <= max_pose_distance_frames
          ):
            pose_frame = pose_by_source_index[nearest_pose_index]
            reused_nearest_pose_frame_count += 1
          else:
            skipped_no_pose_frame_count += 1
            frame_index += 1
            continue

        bounds = _pose_bounds(
          pose_frame,
          width=width,
          height=height,
          selected_side=normalized_selected_side,
        )
        shoulder = bounds[4]
        if shoulder:
          sampled_shoulder_y_values.append(shoulder[1])
        landmarks = pose_frame.get("landmarks") or {}
        wrist_points = (
          _side_wrist_points(
            pose_frame,
            selected_side=normalized_selected_side,
            width=width,
            height=height,
          )
          if normalized_selected_side
          else _wrist_points_from_landmarks(landmarks, width=width, height=height)
        )
        candidate_bounds = bounds[:4]

        manual_prior = manual_prior_for_frame(frame_index)
        manual_prior_is_plausible = self._manual_prior_is_plausible(
          manual_prior,
          bounds=candidate_bounds,
          shoulder=shoulder,
          previous_point=previous_manual_point,
          reference_shoulder_offset=manual_reference_shoulder_offset,
          width=width,
          height=height,
        )
        use_manual_prior = False
        if manual_prior_is_plausible:
          if not manual_has_activated or manual_mode_active:
            use_manual_prior = True
          else:
            manual_reentry_streak += 1
            use_manual_prior = manual_reentry_streak >= 2
        else:
          if manual_prior is not None and manual_has_activated:
            reason = "manual_prior_implausible"
            self.manual_rejected_count += 1
            self.manual_fallback_count += 1
            self.manual_rejection_reason_counts[reason] = (
              self.manual_rejection_reason_counts.get(reason, 0) + 1
            )
          manual_reentry_streak = 0
          manual_mode_active = False

        if use_manual_prior:
          manual_point = (
            float(manual_prior["x"]) * width,
            float(manual_prior["y"]) * height,
          )
          visible_descriptor = self._visible_hub_for_manual_proposal(
            cv2,
            frame,
            manual_point=manual_point,
            bounds=candidate_bounds,
            previous=tracking_lock,
            shoulder=shoulder,
            width=width,
            height=height,
          )
          visible_target = visible_descriptor["guided_target_point"] if visible_descriptor else None
          manual_prior_is_reference = manual_prior.get("tracking_state") == "reference"
          can_calibrate_visual_offset = (
            manual_prior_is_reference
            if manual_priors_have_reference
            else True
          )
          if (
            visible_target is not None
            and manual_visual_offset is None
            and can_calibrate_visual_offset
          ):
            manual_visual_offset = (
              manual_point[0] - visible_target[0],
              manual_point[1] - visible_target[1],
            )
            manual_visual_offset_source = (
              "reference"
              if manual_prior_is_reference
              else "legacy_first_visible_prior"
            )
            manual_visual_offset_frame_index = frame_index
          calibrated_visual_target = (
            (
              visible_target[0] + manual_visual_offset[0],
              visible_target[1] + manual_visual_offset[1],
            )
            if visible_target is not None and manual_visual_offset is not None
            else None
          )
          visible_discrepancy = (
            math.hypot(
              calibrated_visual_target[0] - manual_point[0],
              calibrated_visual_target[1] - manual_point[1],
            )
            if calibrated_visual_target
            else None
          )
          visible_tolerance = (
            max(12.0, float(visible_descriptor["plate"].radius) * 0.34)
            if visible_descriptor
            else None
          )
          if visible_discrepancy is not None:
            manual_visual_residuals.append(visible_discrepancy)
          else:
            manual_validation_missing_count += 1

          visual_mismatch = bool(
            visible_discrepancy is not None
            and visible_tolerance is not None
            and visible_discrepancy > visible_tolerance
          )
          if visual_mismatch:
            manual_visual_mismatch_streak += 1
            manual_visual_match_streak = 0
            reason = "visible_hub_mismatch"
            self.manual_rejection_reason_counts[reason] = (
              self.manual_rejection_reason_counts.get(reason, 0) + 1
            )
            bad_candidate_rejection_counts[reason] = (
              bad_candidate_rejection_counts.get(reason, 0) + 1
            )
          else:
            manual_visual_mismatch_streak = 0
            if manual_visual_recovery_active and calibrated_visual_target is not None:
              manual_visual_match_streak += 1

          if manual_visual_mismatch_streak >= 2:
            if not manual_visual_recovery_active:
              self.manual_rejected_count += 1
              self.manual_fallback_count += 1
            manual_visual_recovery_active = True
          elif manual_visual_recovery_active and manual_visual_match_streak >= 2:
            manual_visual_recovery_active = False
            manual_visual_match_streak = 0

          recovery_visual_is_safe = bool(
            visible_descriptor
            and calibrated_visual_target is not None
            and visible_descriptor.get("hub_safe")
            and visible_descriptor.get("collar_geometry_valid")
            and visible_descriptor.get("final_bar_reason") is None
            and float(visible_descriptor.get("collar_descriptor_score") or 0.0)
            >= MIN_BOOTSTRAP_COLLAR_DESCRIPTOR_SCORE
            and float(visible_descriptor.get("final_bar_confidence") or 0.0)
            >= MIN_COLLAR_DESCRIPTOR_SCORE
          )
          recovery_rejection_reason = (
            "manual_visual_recovery_low_confidence"
            if manual_visual_recovery_active and not recovery_visual_is_safe
            else None
          )
          if recovery_rejection_reason:
            manual_visual_recovery_gap_count += 1
            self.manual_rejection_reason_counts[recovery_rejection_reason] = (
              self.manual_rejection_reason_counts.get(recovery_rejection_reason, 0) + 1
            )
            bad_candidate_rejection_counts[recovery_rejection_reason] = (
              bad_candidate_rejection_counts.get(recovery_rejection_reason, 0) + 1
            )
            manual_frames = self.bootstrap_diagnostics.setdefault("manual_frames", [])
            if len(manual_frames) < 120:
              manual_frames.append({
                "frame_index": frame_index,
                "matched_prior_index": manual_prior.get("_matched_prior_index"),
                "prior_frame_distance": manual_prior.get("_prior_frame_distance"),
                "state": "reacquiring",
                "raw_pin_x": round(manual_point[0], 2),
                "raw_pin_y": round(manual_point[1], 2),
                "raw_visual_x": round(visible_target[0], 2) if visible_target else None,
                "raw_visual_y": round(visible_target[1], 2) if visible_target else None,
                "visual_x": round(visible_target[0], 2) if visible_target else None,
                "visual_y": round(visible_target[1], 2) if visible_target else None,
                "calibrated_visual_x": round(calibrated_visual_target[0], 2) if calibrated_visual_target else None,
                "calibrated_visual_y": round(calibrated_visual_target[1], 2) if calibrated_visual_target else None,
                "visual_to_pin_offset_x": round(manual_visual_offset[0], 2) if manual_visual_offset else None,
                "visual_to_pin_offset_y": round(manual_visual_offset[1], 2) if manual_visual_offset else None,
                "visual_offset_source": manual_visual_offset_source,
                "fusion_residual_px": round(visible_discrepancy, 2) if visible_discrepancy is not None else None,
                "visual_mismatch": visual_mismatch,
                "visual_mismatch_streak": manual_visual_mismatch_streak,
                "visual_match_streak": manual_visual_match_streak,
                "visual_recovery_active": True,
                "visual_recovery_emitted": False,
                "rejection_reason": recovery_rejection_reason,
              })
            if debug_writer:
              write_debug_frame(
                _draw_debug_frame(
                  cv2,
                  frame,
                  bounds=candidate_bounds,
                  candidates=[],
                  rejected=[],
                  selected_plate=visible_descriptor["plate"] if visible_descriptor else None,
                  predicted_collar=(visible_descriptor["predicted_collar"] if visible_descriptor else None),
                  refined_collar=(visible_descriptor["refined_collar"] if visible_descriptor else None),
                  final_bar_point=None,
                  emitted_point=None,
                  manual_point=manual_point,
                  visual_validation_point=calibrated_visual_target,
                  fusion_residual_px=visible_discrepancy,
                  rejection_reason=recovery_rejection_reason,
                  mode="manual_collar:reacquiring",
                )
              )
            non_interpolable_gap_indices.add(len(samples))
            samples.append(None)
            previous_gray = gray
            frame_index += 1
            continue

          manual_mode_active = True
          manual_has_activated = True
          manual_reentry_streak = 0
          previous_manual_point = manual_point
          if shoulder is not None and manual_reference_shoulder_offset is None:
            manual_reference_shoulder_offset = (
              manual_point[0] - shoulder[0],
              manual_point[1] - shoulder[1],
            )

          final_manual_point = (
            calibrated_visual_target
            if manual_visual_recovery_active and recovery_visual_is_safe
            else manual_point
          )
          final_bar_confidence = float(manual_prior["confidence"])
          if manual_visual_recovery_active:
            manual_visual_recovery_emitted_count += 1
            final_bar_confidence = min(
              final_bar_confidence * 0.82,
              float(visible_descriptor["final_bar_confidence"]) if visible_descriptor else 0.0,
            )
          elif visual_mismatch:
            final_bar_confidence *= 0.72
          if visible_descriptor:
            selected_plate = visible_descriptor["plate"]
            sleeve_direction = visible_descriptor["sleeve_direction"]
            if (visible_discrepancy or 0.0) <= 2.0:
              self.manual_accepted_count += 1
            else:
              self.manual_blended_count += 1
          else:
            manual_radius = max(height * 0.035, 12.0)
            selected_plate = Candidate(
              x=manual_point[0],
              y=manual_point[1],
              radius=manual_radius,
              confidence=float(manual_prior["confidence"]),
            )
            sleeve_direction = (1.0, 0.0)
            self.manual_accepted_count += 1

          tracking_lock = _make_tracking_lock(
            cv2,
            gray,
            plate=selected_plate,
            collar=(visible_descriptor["refined_collar"] if visible_descriptor else final_manual_point),
            sleeve_direction=sleeve_direction,
            final_bar_point=final_manual_point,
            display_target_point=final_manual_point,
            final_bar_confidence=final_bar_confidence,
            final_bar_reason=None,
            shoulder=shoulder,
            target_kind=(TRACKING_TARGET if visible_descriptor else SLEEVE_END_TRACKING_TARGET),
          )
          tracking_lock.update(
            {
              "predicted_collar": visible_descriptor["predicted_collar"] if visible_descriptor else final_manual_point,
              "refined_collar": visible_descriptor["refined_collar"] if visible_descriptor else final_manual_point,
              "collar_geometry_valid": True,
              "fallback_used": False,
              "final_bar_source": "manual_collar_prior",
              "collar_descriptor_score": (
                float(visible_descriptor["collar_descriptor_score"])
                if visible_descriptor
                else float(manual_prior["confidence"])
              ),
            }
          )
          tracking_mode = "manual_collar"
          has_ever_locked = True
          self.manual_seed_count += 1
          self.manual_point_count += 1
          final_bar_point = final_manual_point
          final_bar_reason = None
          final_bar_source = tracking_lock["final_bar_source"]
          predicted_collar = tracking_lock["predicted_collar"]
          refined_collar = tracking_lock["refined_collar"]
          collar_geometry_valid = True
          tracking_state = (
            "automatic"
            if manual_visual_recovery_active
            else (
              "reference"
              if manual_prior.get("tracking_state") == "reference"
              else "guided"
            )
          )
          point = {
            "time": timestamp,
            "x": final_manual_point[0] / width,
            "y": final_manual_point[1] / height,
            "confidence": final_bar_confidence,
            "trackingState": tracking_state,
          }
          if not manual_visual_recovery_active:
            point["manual_assisted"] = True
          samples.append(point)
          manual_frames = self.bootstrap_diagnostics.setdefault("manual_frames", [])
          if len(manual_frames) < 120:
            manual_frames.append({
              "frame_index": frame_index,
              "matched_prior_index": manual_prior.get("_matched_prior_index"),
              "prior_frame_distance": manual_prior.get("_prior_frame_distance"),
              "state": tracking_state,
              "raw_pin_x": round(manual_point[0], 2),
              "raw_pin_y": round(manual_point[1], 2),
              "raw_visual_x": round(visible_target[0], 2) if visible_target else None,
              "raw_visual_y": round(visible_target[1], 2) if visible_target else None,
              "visual_x": round(visible_target[0], 2) if visible_target else None,
              "visual_y": round(visible_target[1], 2) if visible_target else None,
              "calibrated_visual_x": round(calibrated_visual_target[0], 2) if calibrated_visual_target else None,
              "calibrated_visual_y": round(calibrated_visual_target[1], 2) if calibrated_visual_target else None,
              "visual_to_pin_offset_x": round(manual_visual_offset[0], 2) if manual_visual_offset else None,
              "visual_to_pin_offset_y": round(manual_visual_offset[1], 2) if manual_visual_offset else None,
              "visual_offset_source": manual_visual_offset_source,
              "fusion_residual_px": round(visible_discrepancy, 2) if visible_discrepancy is not None else None,
              "visual_mismatch": visual_mismatch,
              "visual_mismatch_streak": manual_visual_mismatch_streak,
              "visual_match_streak": manual_visual_match_streak,
              "visual_recovery_active": manual_visual_recovery_active,
              "visual_recovery_emitted": manual_visual_recovery_active,
              "rejection_reason": None,
            })
          accepted_points_px.append(final_manual_point)
          historical_target_point = final_manual_point
          last_accepted_timestamp = timestamp
          detected_count += 1
          if current_rep_index is not None:
            rep_detected_counts[current_rep_index] = rep_detected_counts.get(current_rep_index, 0) + 1
          if debug_writer:
            write_debug_frame(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=candidate_bounds,
                candidates=[],
                rejected=[],
                selected_plate=selected_plate,
                predicted_collar=predicted_collar,
                refined_collar=refined_collar,
                final_bar_point=final_manual_point,
                emitted_point=final_manual_point,
                manual_point=manual_point,
                visual_validation_point=calibrated_visual_target,
                fusion_residual_px=visible_discrepancy,
                rejection_reason="visible_hub_mismatch" if visual_mismatch else None,
                mode=f"manual_collar:{tracking_state}",
              )
            )
          previous_gray = gray
          frame_index += 1
          continue

        if tracking_lock and previous_gray is not None and consecutive_local_failures <= MAX_LOCAL_TRACKING_FAILURES:
          local_shoulder = shoulder
          previous_shoulder_x = tracking_lock.get("shoulder_x")
          previous_shoulder_y = tracking_lock.get("shoulder_y")
          if (
            shoulder
            and previous_shoulder_x is not None
            and previous_shoulder_y is not None
            and math.hypot(
              shoulder[0] - previous_shoulder_x,
              shoulder[1] - previous_shoulder_y,
            )
            > max(tracking_lock["plate"].radius * 0.42, max(width, height) * 0.055)
          ):
            local_shoulder = (float(previous_shoulder_x), float(previous_shoulder_y))
            bad_candidate_rejection_counts["pose_shoulder_outlier"] = (
              bad_candidate_rejection_counts.get("pose_shoulder_outlier", 0) + 1
            )
          next_lock, local_stats = _track_local_patch(
            cv2,
            previous_gray,
            gray,
            tracking_lock,
            shoulder=local_shoulder,
            width=width,
            height=height,
          )
          optical_flow_point_count = local_stats["optical_flow_point_count"]
          optical_flow_inlier_count = local_stats["optical_flow_inlier_count"]
          template_match_score = local_stats["template_match_score"]
          local_tracking_confidence = float(local_stats.get("local_tracking_confidence") or 0.0)
          local_tracker_type = local_stats["local_tracker_type"]
          fallback_used = bool(local_stats["fallback_used"])
          collar_rejection_reason = local_stats["collar_rejection_reason"]
          hub_result_for_debug: dict[str, Any] | None = None
          used_fresh_hub_validation = False

          if next_lock:
            pose_predicted_point = self._pose_predicted_bar_point(tracking_lock, local_shoulder)
            local_final_bar_point = next_lock.get("final_bar_point") or (
              next_lock["plate"].x,
              next_lock["plate"].y,
            )
            motion_rejection_reason = self._final_bar_point_is_motion_consistent(
              local_final_bar_point,
              previous=tracking_lock,
              shoulder=local_shoulder,
              width=width,
              height=height,
            )
            if motion_rejection_reason:
              next_lock = None
              local_stats["collar_rejection_reason"] = motion_rejection_reason
              collar_rejection_reason = motion_rejection_reason
            else:
              shoulder_motion_px = (
                math.hypot(
                  local_shoulder[0] - previous_shoulder_x,
                  local_shoulder[1] - previous_shoulder_y,
                )
                if local_shoulder
                and previous_shoulder_x is not None
                and previous_shoulder_y is not None
                else 0.0
              )
              local_path_point = next_lock.get(
                "display_target_point",
                (next_lock["plate"].x, next_lock["plate"].y),
              )
              path_reason, path_residual, path_model = self._path_prior_rejection_reason(
                local_path_point,
                accepted_points_px,
                timestamp=timestamp,
                last_accepted_timestamp=last_accepted_timestamp,
                max_dimension=max(width, height),
                shoulder_motion_px=shoulder_motion_px,
              )
              last_path_residual_px = path_residual
              if path_residual is not None:
                path_prior_residuals.append(path_residual)
              if path_model:
                local_stats["path_mean_residual_px"] = float(path_model["mean_residual"])
                local_stats["path_max_residual_px"] = float(path_model["max_residual"])
              if path_reason:
                path_prior_rejection_count += 1
                next_lock = None
                local_stats["collar_rejection_reason"] = path_reason
                collar_rejection_reason = path_reason

              if next_lock is not None:
                # Fresh detection corrects drift, but only if the collar target is confirmed.
                fresh_plate = self._fresh_plate_candidate(
                  cv2,
                  frame,
                  bounds=candidate_bounds,
                  previous=tracking_lock,
                  shoulder=local_shoulder,
                  width=width,
                  height=height,
                )
                if fresh_plate:
                  fresh_descriptor = self._collar_descriptor_from_plate(
                    cv2,
                    frame,
                    plate=fresh_plate,
                    previous=tracking_lock,
                    shoulder=local_shoulder,
                    width=width,
                    height=height,
                    bootstrapping=False,
                  )
                  collar_descriptor_score = float(fresh_descriptor["collar_descriptor_score"])
                  hub_result_for_debug = fresh_descriptor["hub_result"]
                  fresh_final_bar_point = fresh_descriptor.get("final_bar_point")
                  previous_display_target = tracking_lock.get("display_target_point")
                  previous_plate = tracking_lock.get("plate")
                  fresh_target_offset_reason = None
                  if previous_display_target is not None and previous_plate is not None:
                    previous_target_offset = (
                      previous_display_target[0] - previous_plate.x,
                      previous_display_target[1] - previous_plate.y,
                    )
                    fresh_target_offset = (
                      fresh_descriptor["target_point"][0] - fresh_plate.x,
                      fresh_descriptor["target_point"][1] - fresh_plate.y,
                    )
                    if math.hypot(
                      fresh_target_offset[0] - previous_target_offset[0],
                      fresh_target_offset[1] - previous_target_offset[1],
                    ) > max(12.0, previous_plate.radius * 0.2):
                      fresh_target_offset_reason = "target_offset_switch"
                  fresh_motion_reason = (
                    self._final_bar_point_is_motion_consistent(
                      fresh_final_bar_point,
                      previous=tracking_lock,
                      shoulder=local_shoulder,
                      width=width,
                      height=height,
                    )
                    if fresh_final_bar_point
                    else None
                  )
                  fresh_path_reason = None
                  fresh_path_residual = None
                  if fresh_final_bar_point:
                    fresh_path_reason, fresh_path_residual, fresh_path_model = self._path_prior_rejection_reason(
                      fresh_descriptor["target_point"],
                      accepted_points_px,
                      timestamp=timestamp,
                      last_accepted_timestamp=last_accepted_timestamp,
                      max_dimension=max(width, height),
                      shoulder_motion_px=shoulder_motion_px,
                    )
                    last_path_residual_px = fresh_path_residual
                    if fresh_path_residual is not None:
                      path_prior_residuals.append(fresh_path_residual)
                    if fresh_path_model:
                      local_stats["path_mean_residual_px"] = float(fresh_path_model["mean_residual"])
                      local_stats["path_max_residual_px"] = float(fresh_path_model["max_residual"])

                  if (
                    fresh_descriptor["final_bar_reason"] is None
                    and fresh_motion_reason is None
                    and fresh_path_reason is None
                    and fresh_target_offset_reason is None
                    and fresh_final_bar_point
                  ):
                    next_lock = _make_tracking_lock(
                      cv2,
                      gray,
                      plate=fresh_plate,
                      collar=fresh_descriptor["refined_collar"],
                      sleeve_direction=fresh_descriptor["sleeve_direction"],
                      final_bar_point=fresh_final_bar_point,
                      display_target_point=fresh_descriptor["target_point"],
                      final_bar_confidence=float(fresh_descriptor["final_bar_confidence"]),
                      final_bar_reason=fresh_descriptor["final_bar_reason"],
                      shoulder=local_shoulder,
                    )
                    next_lock["predicted_collar"] = fresh_descriptor["predicted_collar"]
                    next_lock["refined_collar"] = fresh_descriptor["refined_collar"]
                    next_lock["collar_geometry_valid"] = True
                    next_lock["fallback_used"] = bool(fresh_descriptor["fallback_used"])
                    next_lock["final_bar_source"] = fresh_descriptor["final_bar_source"]
                    next_lock["collar_descriptor_score"] = collar_descriptor_score
                    local_tracker_type = "fresh_hough_validation"
                    local_stats["local_tracker_type"] = local_tracker_type
                    local_tracking_confidence = max(
                      local_tracking_confidence,
                      float(fresh_descriptor["final_bar_confidence"]),
                    )
                    collar_rejection_reason = None
                    local_stats["collar_rejection_reason"] = collar_rejection_reason
                    used_fresh_hub_validation = True
                    consecutive_fresh_validation_failures = 0
                  else:
                    local_validation_reason = (
                      fresh_motion_reason
                      or fresh_path_reason
                      or fresh_target_offset_reason
                      or fresh_descriptor["final_bar_reason"]
                      or "low_collar_descriptor_score"
                    )
                    if fresh_path_reason:
                      path_prior_rejection_count += 1
                    bad_candidate_rejection_counts[local_validation_reason] = (
                      bad_candidate_rejection_counts.get(local_validation_reason, 0) + 1
                    )
                    local_stats["collar_rejection_reason"] = local_validation_reason
                    collar_rejection_reason = local_validation_reason
                    hub_rejected_count += 1
                    final_bar_reason_counts[local_validation_reason] = (
                      final_bar_reason_counts.get(local_validation_reason, 0) + 1
                    )
                    bridge_confident = (
                      int(local_stats.get("optical_flow_inlier_count") or 0) >= 8
                      and float(local_stats.get("local_tracking_confidence") or 0.0) >= 0.62
                      and consecutive_fresh_validation_failures < 9
                    )
                    if bridge_confident:
                      consecutive_fresh_validation_failures += 1
                      local_descriptor_bridge_count += 1
                    else:
                      next_lock = None
                else:
                  local_validation_reason = "fresh_hub_not_found"
                  local_stats["collar_rejection_reason"] = local_validation_reason
                  collar_rejection_reason = local_validation_reason
                  hub_rejected_count += 1
                  final_bar_reason_counts[local_validation_reason] = (
                    final_bar_reason_counts.get(local_validation_reason, 0) + 1
                  )

          if next_lock:

            tracking_mode = "local_tracking"
            tracking_lock = next_lock
            selected_plate = tracking_lock["plate"]
            final_bar_point = tracking_lock.get("final_bar_point") or (selected_plate.x, selected_plate.y)
            final_bar_confidence = float(tracking_lock.get("final_bar_confidence", 0.65))
            final_bar_reason = tracking_lock.get("final_bar_reason")
            final_bar_source = tracking_lock.get("final_bar_source")
            collar_descriptor_score = tracking_lock.get("collar_descriptor_score")
            predicted_collar = tracking_lock["predicted_collar"]
            refined_collar = tracking_lock["refined_collar"]
            sleeve_direction = (tracking_lock["collar_direction_x"], tracking_lock["collar_direction_y"])
            collar_geometry_valid = True
            consecutive_local_failures = 0
            emitted_bar_point = choose_automatic_emit_point(
              final_point=final_bar_point,
              target_point=tracking_lock.get("display_target_point", final_bar_point),
            )
            point = {
              "time": timestamp,
              "x": emitted_bar_point[0] / width,
              "y": emitted_bar_point[1] / height,
              "confidence": final_bar_confidence,
              "trackingState": "automatic",
            }
            accepted_points_px.append(emitted_bar_point)
            historical_target_point = emitted_bar_point
            rep_anchor_x_values.append(float(next_lock["plate"].x))
            last_accepted_timestamp = timestamp
            if current_rep_index is not None:
              rep_detected_counts[current_rep_index] = rep_detected_counts.get(current_rep_index, 0) + 1
            if used_fresh_hub_validation:
              real_hub_detection_count += 1
              fresh_hough_correction_count += 1
            else:
              accepted_local_tracking_count += 1
            logger.info(
              "Barbell point emitted frame=%s plate=(%.2f, %.2f r=%.2f) final=(%.2f, %.2f) final_reason=%s final_conf=%.3f point_source=%s fallback_used=%s predicted=(%.2f, %.2f) refined=(%.2f, %.2f) normalized=(%.4f, %.4f) pending_confirmation_count=%s",
              frame_index,
              selected_plate.x,
              selected_plate.y,
              selected_plate.radius,
              final_bar_point[0],
              final_bar_point[1],
              final_bar_reason,
              final_bar_confidence,
              "local_tracking",
              fallback_used,
              predicted_collar[0],
              predicted_collar[1],
              refined_collar[0],
              refined_collar[1],
              point["x"],
              point["y"],
              pending_confirmation_count,
            )
            self._record_tracking_frame_diagnostic(
              frame_index=frame_index,
              timestamp=timestamp,
              tracking_mode=tracking_mode,
              selected_plate=selected_plate,
              final_bar_point=final_bar_point,
              pose_predicted_point=pose_predicted_point,
              predicted_collar=predicted_collar,
              refined_collar=refined_collar,
              point=point,
              width=width,
              height=height,
              local_tracker_type=local_tracker_type,
              optical_flow_inlier_count=optical_flow_inlier_count,
              template_match_score=template_match_score,
              collar_rejection_reason=collar_rejection_reason,
              point_source="local_tracking",
              final_bar_reason=final_bar_reason,
              final_bar_confidence=final_bar_confidence,
              final_bar_source=final_bar_source,
              fallback_used=fallback_used,
              path_residual_px=last_path_residual_px,
              collar_descriptor_score=float(collar_descriptor_score) if collar_descriptor_score is not None else None,
            )
            samples.append(point)
            detected_count += 1
            previous_gray = gray
            if debug_writer:
              write_debug_frame(
                _draw_debug_frame(
                  cv2,
                  frame,
                  bounds=bounds[:4],
                  candidates=[],
                  rejected=[],
                  selected_plate=selected_plate,
                  hub_candidates=list((hub_result_for_debug or {}).get("candidates") or []),
                  rejected_hub_candidates=list((hub_result_for_debug or {}).get("rejected_candidates") or []),
                  final_bar_point=final_bar_point,
                  pose_predicted_point=pose_predicted_point,
                  predicted_collar=predicted_collar,
                  refined_collar=refined_collar,
                  emitted_point=final_bar_point,
                  mode=tracking_mode,
                )
              )
            frame_index += 1
            continue

          local_tracking_failure_count += 1
          consecutive_local_failures += 1
          consecutive_fresh_validation_failures = 0
          if collar_rejection_reason:
            hub_rejected_count += 1
            final_bar_reason_counts[collar_rejection_reason] = final_bar_reason_counts.get(collar_rejection_reason, 0) + 1
          if collar_rejection_reason == "stationary_hardware_like":
            stationary_hardware_rejection_count += 1
          if consecutive_local_failures <= MAX_LOCAL_TRACKING_FAILURES:
            tracking_mode = "local_tracking"
            coast_point = estimated_barbell_coast_point(
              timestamp=timestamp,
              shoulder=shoulder,
              reason=collar_rejection_reason,
              failure_count=consecutive_local_failures,
            )
            if coast_point is not None:
              coasted_estimated_point_count += 1
              self._record_tracking_frame_diagnostic(
                frame_index=frame_index,
                timestamp=timestamp,
                tracking_mode=tracking_mode,
                selected_plate=tracking_lock["plate"],
                final_bar_point=(
                  float(coast_point["x"]) * width,
                  float(coast_point["y"]) * height,
                ),
                pose_predicted_point=self._pose_predicted_bar_point(tracking_lock, shoulder),
                predicted_collar=tracking_lock.get("predicted_collar"),
                refined_collar=None,
                point=coast_point,
                width=width,
                height=height,
                local_tracker_type=local_tracker_type,
                optical_flow_inlier_count=optical_flow_inlier_count,
                template_match_score=template_match_score,
                collar_rejection_reason=collar_rejection_reason,
                point_source="kinematic_coast",
                final_bar_reason=collar_rejection_reason,
                final_bar_confidence=float(coast_point["confidence"]),
                final_bar_source=(hub_result_for_debug or {}).get("source"),
                fallback_used=fallback_used,
                path_residual_px=last_path_residual_px,
              )
              samples.append(coast_point)
              if debug_writer:
                coast_px = (
                  float(coast_point["x"]) * width,
                  float(coast_point["y"]) * height,
                )
                write_debug_frame(
                  _draw_debug_frame(
                    cv2,
                    frame,
                    bounds=bounds[:4],
                    candidates=[],
                    rejected=[],
                    selected_plate=tracking_lock["plate"],
                    hub_candidates=list((hub_result_for_debug or {}).get("candidates") or []),
                    rejected_hub_candidates=list((hub_result_for_debug or {}).get("rejected_candidates") or []),
                    final_bar_point=coast_px,
                    pose_predicted_point=self._pose_predicted_bar_point(tracking_lock, shoulder),
                    predicted_collar=tracking_lock.get("predicted_collar"),
                    refined_collar=None,
                    emitted_point=coast_px,
                    rejection_reason=collar_rejection_reason,
                    mode=f"{tracking_mode}:kinematic_coast",
                  )
                )
              frame_index += 1
              continue
            self._record_tracking_frame_diagnostic(
              frame_index=frame_index,
              timestamp=timestamp,
              tracking_mode=tracking_mode,
              selected_plate=tracking_lock["plate"],
              final_bar_point=tracking_lock.get("final_bar_point"),
              pose_predicted_point=self._pose_predicted_bar_point(tracking_lock, shoulder),
              predicted_collar=tracking_lock.get("predicted_collar"),
              refined_collar=None,
              point=None,
              width=width,
              height=height,
              local_tracker_type=local_tracker_type,
              optical_flow_inlier_count=optical_flow_inlier_count,
              template_match_score=template_match_score,
              collar_rejection_reason=collar_rejection_reason,
              point_source="no_emission",
              final_bar_reason=collar_rejection_reason,
              final_bar_confidence=0.0,
              final_bar_source=(hub_result_for_debug or {}).get("source"),
              fallback_used=fallback_used,
              path_residual_px=last_path_residual_px,
            )
            non_interpolable_gap_indices.add(len(samples))
            samples.append(None)
            # Keep previous_gray aligned with tracking_lock/features after a failed local update.
            if debug_writer:
              write_debug_frame(
                _draw_debug_frame(
                  cv2,
                  frame,
                  bounds=bounds[:4],
                  candidates=[],
                  rejected=[],
                  selected_plate=tracking_lock["plate"],
                  hub_candidates=list((hub_result_for_debug or {}).get("candidates") or []),
                  rejected_hub_candidates=list((hub_result_for_debug or {}).get("rejected_candidates") or []),
                  final_bar_point=tracking_lock.get("final_bar_point"),
                  pose_predicted_point=self._pose_predicted_bar_point(tracking_lock, shoulder),
                  predicted_collar=tracking_lock.get("predicted_collar"),
                  refined_collar=None,
                  rejection_reason=collar_rejection_reason,
                  mode=tracking_mode,
                )
              )
            frame_index += 1
            continue

          tracking_lock = None
          pending_plate = None
          pending_confirmation_count = 0
          pending_miss_count = 0
          bootstrap_pose_relative_displacements = []
          bootstrap_rejection_reason_counts = {}

        tracking_mode = "reacquiring" if has_ever_locked and tracking_lock is None else "initializing"
        if tracking_mode == "initializing":
          initialization_frame_count += 1
        else:
          reacquisition_count += 1

        hough_detection_count += 1
        candidates, crop_width, crop_height, detection_diagnostics = _detect_crop_candidates(
          cv2,
          frame,
          candidate_bounds,
          shoulder=shoulder,
          wrist_points=wrist_points,
        )
        debug_bounds = detection_diagnostics["crop_bounds"]
        crop_widths.append(crop_width)
        crop_heights.append(crop_height)
        wrist_rejected_count = int(detection_diagnostics["wrist_rejected_count"])
        if wrist_rejected_count:
          rejected_candidate_count += wrist_rejected_count
          rejection_reason_counts["near_wrist"] = rejection_reason_counts.get("near_wrist", 0) + wrist_rejected_count
          if tracking_mode in {"initializing", "reacquiring"}:
            bootstrap_rejection_reason_counts["near_wrist"] = (
              bootstrap_rejection_reason_counts.get("near_wrist", 0) + wrist_rejected_count
            )
        candidates = [candidate for candidate in candidates if _candidate_in_bounds(candidate, candidate_bounds)]
        rejected: list[Candidate] = []
        plausible_candidates: list[Candidate] = []

        for candidate in candidates:
          reason = _plate_rejection_reason(
            candidate,
            previous=pending_plate,
            shoulder=shoulder,
            width=width,
            height=height,
            bootstrapping=True,
          )
          if reason:
            rejected.append(candidate)
            rejected_candidate_count += 1
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
            if reason == "stationary_hardware_like":
              stationary_hardware_rejection_count += 1
            if tracking_mode in {"initializing", "reacquiring"}:
              bootstrap_rejection_reason_counts[reason] = bootstrap_rejection_reason_counts.get(reason, 0) + 1
          else:
            plausible_candidates.append(candidate)

        if not plausible_candidates:
          if tracking_mode in {"initializing", "reacquiring"}:
            bootstrap_diagnostic = self._record_bootstrap_diagnostic(
              frame_index=frame_index,
              tracking_mode=tracking_mode,
              detection_diagnostics=detection_diagnostics,
              shoulder=shoulder,
              wrist_points=wrist_points,
              selected_plate=None,
            )
            if bootstrap_diagnostic:
              self._log_bootstrap_diagnostic(bootstrap_diagnostic)
          self._record_tracking_frame_diagnostic(
            frame_index=frame_index,
            timestamp=timestamp,
            tracking_mode=tracking_mode,
            selected_plate=None,
            final_bar_point=None,
            pose_predicted_point=None,
            predicted_collar=None,
            refined_collar=None,
            point=None,
            width=width,
            height=height,
            local_tracker_type=local_tracker_type,
            optical_flow_inlier_count=optical_flow_inlier_count,
            template_match_score=template_match_score,
            collar_rejection_reason=None,
            point_source="no_emission",
          )
          samples.append(None)
          if debug_writer:
            write_debug_frame(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=debug_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=None,
                predicted_collar=None,
                refined_collar=None,
                rejection_reason="no_plausible_candidates",
                mode=tracking_mode,
              )
            )
          previous_gray = gray
          frame_index += 1
          continue

        descriptor_source_candidates = plausible_candidates
        if tracking_mode in {"initializing", "reacquiring"}:
          plate_sized_candidates = [
            candidate
            for candidate in plausible_candidates
            if candidate.radius >= max(min(width, height) * 0.07, 1.0)
          ]
          if plate_sized_candidates:
            descriptor_source_candidates = plate_sized_candidates

        descriptor_candidates: list[dict[str, Any]] = []
        for candidate in descriptor_source_candidates:
          descriptor = self._collar_descriptor_from_plate(
            cv2,
            frame,
            plate=candidate,
            previous=pending_plate,
            shoulder=shoulder,
            width=width,
            height=height,
            bootstrapping=True,
          )
          collar_candidate_count += 1
          reason = descriptor["final_bar_reason"]
          if reason:
            rejected.append(candidate)
            rejected_candidate_count += 1
            bad_candidate_rejection_counts[reason] = bad_candidate_rejection_counts.get(reason, 0) + 1
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
            if tracking_mode in {"initializing", "reacquiring"}:
              bootstrap_rejection_reason_counts[reason] = bootstrap_rejection_reason_counts.get(reason, 0) + 1
            continue
          descriptor_candidates.append(descriptor)

        if rep_anchor_x_values:
          rep_anchor_x = sum(rep_anchor_x_values[-12:]) / len(rep_anchor_x_values[-12:])
          rep_axis_limit = max(30.0, width * 0.075)
          axis_consistent_descriptors = [
            descriptor
            for descriptor in descriptor_candidates
            if abs(descriptor["plate"].x - rep_anchor_x) <= rep_axis_limit
          ]
          rejected_axis_count = len(descriptor_candidates) - len(axis_consistent_descriptors)
          if rejected_axis_count:
            bad_candidate_rejection_counts["rep_axis_drift"] = (
              bad_candidate_rejection_counts.get("rep_axis_drift", 0) + rejected_axis_count
            )
            rejection_reason_counts["rep_axis_drift"] = (
              rejection_reason_counts.get("rep_axis_drift", 0) + rejected_axis_count
            )
          descriptor_candidates = axis_consistent_descriptors

        selection_candidates = descriptor_candidates
        selected_matches_pending = False
        if pending_plate is not None:
          pending_matches = [
            descriptor
            for descriptor in descriptor_candidates
            if math.hypot(
              descriptor["target_point"][0] - pending_plate["target_x"],
              descriptor["target_point"][1] - pending_plate["target_y"],
            )
            <= max(30.0, max(width, height) * 0.06)
            and abs(descriptor["plate"].radius - pending_plate["radius"])
            / max(pending_plate["radius"], 1.0)
            <= 0.4
          ]
          if pending_matches:
            selection_candidates = pending_matches
            selected_matches_pending = True
            pending_miss_count = 0
          elif pending_miss_count < 2:
            selection_candidates = []
            pending_miss_count += 1
          else:
            pending_plate = None
            pending_confirmation_count = 0
            pending_miss_count = 0

        selected_descriptor = (
          max(
            selection_candidates,
            key=lambda descriptor: (
              float(descriptor["collar_descriptor_score"])
              + float(descriptor["final_bar_confidence"])
              + (
                _score_plate_candidate(
                  descriptor["plate"],
                  previous=pending_plate,
                  shoulder=shoulder,
                  width=width,
                  height=height,
                )
                * 0.12
              )
              + (
                max(
                  0.0,
                  1.0
                  - (
                    math.hypot(
                      descriptor["target_point"][0] - historical_target_point[0],
                      descriptor["target_point"][1] - historical_target_point[1],
                    )
                    / max(max(width, height) * 0.3, 1.0)
                  ),
                )
                * 0.55
                if historical_target_point is not None
                else 0.0
              )
              + (
                self._plate_color_similarity(
                  descriptor["plate_color_signature"],
                  historical_plate_signature,
                )
                * 0.8
              )
            ),
          )
          if selection_candidates
          else None
        )
        selected_plate = selected_descriptor["plate"] if selected_descriptor else None
        if not selected_plate or not selected_descriptor:
          if tracking_mode in {"initializing", "reacquiring"}:
            bootstrap_diagnostic = self._record_bootstrap_diagnostic(
              frame_index=frame_index,
              tracking_mode=tracking_mode,
              detection_diagnostics=detection_diagnostics,
              shoulder=shoulder,
              wrist_points=wrist_points,
              selected_plate=None,
            )
            if bootstrap_diagnostic:
              self._log_bootstrap_diagnostic(bootstrap_diagnostic)
          self._record_tracking_frame_diagnostic(
            frame_index=frame_index,
            timestamp=timestamp,
            tracking_mode=tracking_mode,
            selected_plate=None,
            final_bar_point=None,
            pose_predicted_point=None,
            predicted_collar=None,
            refined_collar=None,
            point=None,
            width=width,
            height=height,
            local_tracker_type=local_tracker_type,
            optical_flow_inlier_count=optical_flow_inlier_count,
            template_match_score=template_match_score,
            collar_rejection_reason=None,
            point_source="no_emission",
          )
          samples.append(None)
          previous_gray = gray
          frame_index += 1
          continue

        if tracking_mode in {"initializing", "reacquiring"}:
          bootstrap_diagnostic = self._record_bootstrap_diagnostic(
            frame_index=frame_index,
            tracking_mode=tracking_mode,
            detection_diagnostics=detection_diagnostics,
            shoulder=shoulder,
            wrist_points=wrist_points,
            selected_plate=selected_plate,
          )
          if bootstrap_diagnostic:
            self._log_bootstrap_diagnostic(bootstrap_diagnostic)
        selected_offset = _shoulder_relative_offset(selected_plate, shoulder)
        selected_final_bar_point = selected_descriptor["final_bar_point"]
        collar_descriptor_score = float(selected_descriptor["collar_descriptor_score"])
        next_pending = {
          "x": selected_plate.x,
          "y": selected_plate.y,
          "final_bar_x": selected_final_bar_point[0],
          "final_bar_y": selected_final_bar_point[1],
          "target_x": selected_descriptor["target_point"][0],
          "target_y": selected_descriptor["target_point"][1],
          "final_bar_dx": (selected_final_bar_point[0] - shoulder[0]) if shoulder else 0.0,
          "final_bar_dy": (selected_final_bar_point[1] - shoulder[1]) if shoulder else 0.0,
          "dx": selected_offset[0] if selected_offset else 0.0,
          "dy": selected_offset[1] if selected_offset else 0.0,
          "radius": selected_plate.radius,
          "shoulder_x": shoulder[0] if shoulder else selected_plate.x,
          "shoulder_y": shoulder[1] if shoulder else selected_plate.y,
          "collar_direction_x": selected_descriptor["sleeve_direction"][0],
          "collar_direction_y": selected_descriptor["sleeve_direction"][1],
          "collar_descriptor_score": collar_descriptor_score,
        }
        pose_relative_displacement = (
          _pose_relative_displacement(selected_plate, previous=pending_plate, shoulder=shoulder)
          if pending_plate
          else None
        )
        bootstrap_consistency_reason = (
          self._final_bar_point_is_motion_consistent(
            selected_final_bar_point,
            previous=pending_plate,
            shoulder=shoulder,
            width=width,
            height=height,
          )
          if pending_plate
          else None
        )
        if bootstrap_consistency_reason:
          rejected_candidate_count += 1
          rejection_reason_counts[bootstrap_consistency_reason] = (
            rejection_reason_counts.get(bootstrap_consistency_reason, 0) + 1
          )
          bootstrap_rejection_reason_counts[bootstrap_consistency_reason] = (
            bootstrap_rejection_reason_counts.get(bootstrap_consistency_reason, 0) + 1
          )
          if bootstrap_consistency_reason == "stationary_hardware_like":
            stationary_hardware_rejection_count += 1

        if (
          pending_plate
          and bootstrap_consistency_reason is None
          and (
            selected_matches_pending
            or _plate_match_is_consistent(
              selected_plate,
              pending_plate,
              shoulder=shoulder,
              width=width,
              height=height,
            )
          )
        ):
          pending_confirmation_count += 1
          if pose_relative_displacement is not None:
            bootstrap_pose_relative_displacements.append(round(pose_relative_displacement, 3))
        else:
          pending_confirmation_count = 1
          bootstrap_pose_relative_displacements = [0.0]
        pending_plate = next_pending
        if pending_confirmation_count < INIT_CONFIRMATION_FRAMES:
          self._record_tracking_frame_diagnostic(
            frame_index=frame_index,
            timestamp=timestamp,
            tracking_mode=tracking_mode,
            selected_plate=selected_plate,
            final_bar_point=None,
            pose_predicted_point=None,
            predicted_collar=None,
            refined_collar=None,
            point=None,
            width=width,
            height=height,
            local_tracker_type=local_tracker_type,
            optical_flow_inlier_count=optical_flow_inlier_count,
            template_match_score=template_match_score,
            collar_rejection_reason=bootstrap_consistency_reason,
            point_source="bootstrap_pending",
          )
          samples.append(None)
          previous_gray = gray
          if debug_writer:
            write_debug_frame(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=debug_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=selected_plate,
                predicted_collar=None,
                refined_collar=None,
                rejection_reason=bootstrap_consistency_reason,
                mode=tracking_mode,
              )
            )
          frame_index += 1
          continue

        initialization_confirmed = True
        logger.info(
          "Barbell bootstrap locked after %s frames; pose_relative_displacements=%s; rejected_candidate_reasons=%s",
          pending_confirmation_count,
          bootstrap_pose_relative_displacements,
          bootstrap_rejection_reason_counts,
        )
        if has_ever_locked:
          local_tracker_type = "hough_reacquisition"
          consecutive_local_failures = 0
          consecutive_fresh_validation_failures = 0

        predicted_collar = selected_descriptor["predicted_collar"]
        refined_collar = selected_descriptor["refined_collar"]
        sleeve_direction = selected_descriptor["sleeve_direction"]
        final_bar_point = selected_descriptor["final_bar_point"]
        final_bar_confidence = float(selected_descriptor["final_bar_confidence"])
        final_bar_reason = selected_descriptor["final_bar_reason"]
        final_bar_source = selected_descriptor["final_bar_source"]
        fallback_used = bool(selected_descriptor["fallback_used"])
        collar_geometry_valid = True
        collar_rejection_reason = None
        hub_result = selected_descriptor["hub_result"]
        emitted_bar_point = choose_automatic_emit_point(
          final_point=final_bar_point,
          target_point=selected_descriptor["target_point"],
        )

        path_reason, path_residual, path_model = self._path_prior_rejection_reason(
          emitted_bar_point,
          accepted_points_px,
          timestamp=timestamp,
          last_accepted_timestamp=last_accepted_timestamp,
          max_dimension=max(width, height),
        )
        last_path_residual_px = path_residual
        if path_residual is not None:
          path_prior_residuals.append(path_residual)
        if path_reason:
          path_prior_rejection_count += 1
          final_bar_reason_counts[path_reason] = final_bar_reason_counts.get(path_reason, 0) + 1
          self._record_tracking_frame_diagnostic(
            frame_index=frame_index,
            timestamp=timestamp,
            tracking_mode=tracking_mode,
            selected_plate=selected_plate,
            final_bar_point=final_bar_point,
            pose_predicted_point=None,
            predicted_collar=predicted_collar,
            refined_collar=refined_collar,
            point=None,
            width=width,
            height=height,
            local_tracker_type=local_tracker_type,
            optical_flow_inlier_count=optical_flow_inlier_count,
            template_match_score=template_match_score,
            collar_rejection_reason=path_reason,
            point_source="no_emission",
            final_bar_reason=path_reason,
            final_bar_confidence=final_bar_confidence,
            final_bar_source=final_bar_source,
            fallback_used=fallback_used,
            path_residual_px=path_residual,
          )
          samples.append(None)
          if debug_writer:
            write_debug_frame(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=debug_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=selected_plate,
                hub_candidates=list(hub_result.get("candidates") or []),
                rejected_hub_candidates=list(hub_result.get("rejected_candidates") or []),
                final_bar_point=final_bar_point,
                pose_predicted_point=None,
                predicted_collar=predicted_collar,
                refined_collar=refined_collar,
                rejection_reason=path_reason,
                mode=tracking_mode,
              )
            )
          previous_gray = gray
          frame_index += 1
          continue

        tracklet_confirmation_count = max(tracklet_confirmation_count, pending_confirmation_count)
        confidence = final_bar_confidence
        point = {
          "time": timestamp,
          "x": emitted_bar_point[0] / width,
          "y": emitted_bar_point[1] / height,
          "confidence": confidence,
          "trackingState": "automatic",
        }
        real_hub_detection_count += 1
        accepted_points_px.append(emitted_bar_point)
        historical_target_point = emitted_bar_point
        historical_plate_signature = selected_descriptor["plate_color_signature"]
        rep_anchor_x_values.append(float(selected_plate.x))
        last_accepted_timestamp = timestamp
        if current_rep_index is not None:
          rep_detected_counts[current_rep_index] = rep_detected_counts.get(current_rep_index, 0) + 1
        logger.info(
          "Barbell point emitted frame=%s plate=(%.2f, %.2f r=%.2f) final=(%.2f, %.2f) final_reason=%s final_conf=%.3f point_source=%s fallback_used=%s predicted=(%.2f, %.2f) refined=(%.2f, %.2f) normalized=(%.4f, %.4f) pending_confirmation_count=%s",
          frame_index,
          selected_plate.x,
          selected_plate.y,
          selected_plate.radius,
          final_bar_point[0],
          final_bar_point[1],
          final_bar_reason,
          final_bar_confidence,
          "reacquisition" if has_ever_locked else "bootstrap",
          fallback_used,
          predicted_collar[0],
          predicted_collar[1],
          refined_collar[0],
          refined_collar[1],
          point["x"],
          point["y"],
          pending_confirmation_count,
        )
        self._record_tracking_frame_diagnostic(
          frame_index=frame_index,
          timestamp=timestamp,
          tracking_mode=tracking_mode,
          selected_plate=selected_plate,
          final_bar_point=final_bar_point,
          pose_predicted_point=None,
          predicted_collar=predicted_collar,
          refined_collar=refined_collar,
          point=point,
          width=width,
          height=height,
          local_tracker_type=local_tracker_type,
          optical_flow_inlier_count=optical_flow_inlier_count,
          template_match_score=template_match_score,
          collar_rejection_reason=collar_rejection_reason,
          point_source="reacquisition" if has_ever_locked else "bootstrap",
          final_bar_reason=final_bar_reason,
          final_bar_confidence=final_bar_confidence,
          final_bar_source=final_bar_source,
          fallback_used=fallback_used,
          path_residual_px=last_path_residual_px,
          collar_descriptor_score=collar_descriptor_score,
        )
        relative_offset = _shoulder_relative_offset(selected_plate, shoulder)
        tracking_lock = _make_tracking_lock(
          cv2,
          gray,
          plate=selected_plate,
          collar=refined_collar,
          sleeve_direction=sleeve_direction,
          final_bar_point=final_bar_point,
          display_target_point=emitted_bar_point,
          final_bar_confidence=final_bar_confidence,
          final_bar_reason=final_bar_reason,
          shoulder=shoulder,
        )
        if has_ever_locked:
          reacquisition_success_count += 1
        has_ever_locked = True
        tracking_lock.update(
          {
            "dx": relative_offset[0] if relative_offset else 0.0,
            "dy": relative_offset[1] if relative_offset else 0.0,
            "predicted_collar": predicted_collar,
            "refined_collar": refined_collar,
            "collar_geometry_valid": True,
            "fallback_used": fallback_used,
            "final_bar_source": final_bar_source,
            "collar_descriptor_score": collar_descriptor_score,
          }
        )
        samples.append(point)
        detected_count += 1
        previous_gray = gray
        if debug_writer:
          write_debug_frame(
            _draw_debug_frame(
              cv2,
              frame,
              bounds=debug_bounds,
              candidates=candidates,
              rejected=rejected,
              selected_plate=selected_plate,
              hub_candidates=list(hub_result.get("candidates") or []),
              rejected_hub_candidates=list(hub_result.get("rejected_candidates") or []),
              final_bar_point=final_bar_point,
              pose_predicted_point=None,
              predicted_collar=predicted_collar,
              refined_collar=refined_collar,
              emitted_point=final_bar_point,
              mode=tracking_mode,
            )
          )
        frame_index += 1
    finally:
      capture.release()
      if debug_writer:
        debug_writer.release()

    sampled_count = len(samples)
    processing_duration_ms = int((time.perf_counter() - started) * 1000)
    average_crop_width = round(sum(crop_widths) / len(crop_widths), 1) if crop_widths else None
    average_crop_height = round(sum(crop_heights) / len(crop_heights), 1) if crop_heights else None
    per_rep_coverage = [
      {
        "rep_index": int(window["rep_index"]),
        "start": round(float(window["start"]), 4),
        "bottom": round(float(window["bottom"]), 4),
        "end": round(float(window["end"]), 4),
        "sampled_frame_count": rep_sample_counts.get(int(window["rep_index"]), 0),
        "detected_point_count": rep_detected_counts.get(int(window["rep_index"]), 0),
        "coverage": round(
          rep_detected_counts.get(int(window["rep_index"]), 0)
          / max(rep_sample_counts.get(int(window["rep_index"]), 0), 1),
          3,
        ),
      }
      for window in normalized_rep_windows
    ]
    if sampled_count == 0:
      result = _empty_result(
        "no_sampled_frames",
        skipped_no_pose_frame_count=skipped_no_pose_frame_count,
        processing_duration_ms=processing_duration_ms,
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        rejected_candidate_count=rejected_candidate_count,
        rejection_reason_counts=rejection_reason_counts,
        crop_width=average_crop_width,
        crop_height=average_crop_height,
        selected_plate=selected_plate,
        predicted_collar=predicted_collar,
        refined_collar=refined_collar,
        sleeve_direction=sleeve_direction,
        collar_rejection_reason=collar_rejection_reason,
        collar_geometry_valid=collar_geometry_valid,
        fallback_used=fallback_used,
        tracking_mode=tracking_mode,
        local_tracker_type=local_tracker_type,
        initialization_confirmed=initialization_confirmed,
        initialization_frame_count=initialization_frame_count,
        hough_detection_count=hough_detection_count,
        optical_flow_point_count=optical_flow_point_count,
        optical_flow_inlier_count=optical_flow_inlier_count,
        template_match_score=template_match_score,
        local_tracking_confidence=local_tracking_confidence,
        accepted_local_tracking_count=accepted_local_tracking_count,
        fresh_hough_correction_count=fresh_hough_correction_count,
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
        coasted_estimated_point_count=coasted_estimated_point_count,
        selected_side=normalized_selected_side,
        coordinate_space=coordinate_space,
        collar_candidate_count=collar_candidate_count,
        collar_descriptor_score=collar_descriptor_score,
        tracklet_confirmation_count=tracklet_confirmation_count,
        bad_candidate_rejection_counts=bad_candidate_rejection_counts,
        path_reset_count=path_reset_count,
        stale_prior_expiration_count=stale_prior_expiration_count,
        reacquisition_success_count=reacquisition_success_count,
        per_rep_coverage=per_rep_coverage,
        manual_accepted_count=self.manual_accepted_count,
        manual_blended_count=self.manual_blended_count,
        manual_rejected_count=self.manual_rejected_count,
        manual_fallback_count=self.manual_fallback_count,
        manual_rejection_reason_counts=self.manual_rejection_reason_counts,
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
      result["diagnostics"]["manual_prior_index_matching"] = manual_prior_index_diagnostics
      return result

    points, interpolated_count = _interpolate_missing(
      samples,
      blocked_gap_indices=non_interpolable_gap_indices,
    )
    points, outlier_removed_count = _remove_motion_outliers(points)
    manual_lane_points = (
      list((pin_lane_result.get("barbellPath") or {}).get("points") or [])
      if pin_lane_result
      else []
    )
    lane_fusion_diagnostics: dict[str, Any] = {
      "enabled": False,
      "reason": "missing_manual_lane",
      "frames": [],
    }
    if manual_lane_points:
      points, lane_fusion_diagnostics = _fuse_barbell_lanes(
        points,
        manual_lane_points,
        width=width,
        height=height,
      )
      sampled_count = max(
        sampled_count,
        int((pin_lane_result.get("diagnostics") or {}).get("sampled_frame_count") or 0),
      )
    if normalized_rep_windows:
      points = [
        point
        for point in points
        if any(
          float(window["start"]) <= float(point["time"]) <= float(window["end"])
          for window in normalized_rep_windows
        )
      ]
    self.manual_point_count = sum(bool(point.get("manual_assisted")) for point in points)
    self.automatic_point_count = len(points) - self.manual_point_count
    coverage = len(points) / sampled_count if sampled_count else 0.0
    bar_vertical_range_px = (
      (max(float(point["y"]) for point in points) - min(float(point["y"]) for point in points)) * height
      if points
      else 0.0
    )
    shoulder_vertical_range_px = (
      max(sampled_shoulder_y_values) - min(sampled_shoulder_y_values)
      if sampled_shoulder_y_values
      else 0.0
    )
    path_prior_last_residual_px = round(last_path_residual_px, 2) if last_path_residual_px is not None else None
    path_prior_max_residual_px = round(max(path_prior_residuals), 2) if path_prior_residuals else None
    path_prior_mean_residual_px = (
      round(sum(path_prior_residuals) / len(path_prior_residuals), 2)
      if path_prior_residuals
      else None
    )

    if len(points) < MIN_TRACK_POINTS or coverage < MIN_TRACK_COVERAGE:
      result = _empty_result(
        "low_barbell_tracking_coverage",
        sampled_frame_count=sampled_count,
        detected_point_count=detected_count,
        skipped_no_pose_frame_count=skipped_no_pose_frame_count,
        processing_duration_ms=processing_duration_ms,
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        rejected_candidate_count=rejected_candidate_count,
        rejection_reason_counts=rejection_reason_counts,
        crop_width=average_crop_width,
        crop_height=average_crop_height,
        selected_plate=selected_plate,
        predicted_collar=predicted_collar,
        refined_collar=refined_collar,
        sleeve_direction=sleeve_direction,
        collar_rejection_reason=collar_rejection_reason,
        collar_geometry_valid=collar_geometry_valid,
        fallback_used=fallback_used,
        tracking_mode=tracking_mode,
        local_tracker_type=local_tracker_type,
        initialization_confirmed=initialization_confirmed,
        initialization_frame_count=initialization_frame_count,
        hough_detection_count=hough_detection_count,
        optical_flow_point_count=optical_flow_point_count,
        optical_flow_inlier_count=optical_flow_inlier_count,
        template_match_score=template_match_score,
        local_tracking_confidence=local_tracking_confidence,
        accepted_local_tracking_count=accepted_local_tracking_count,
        fresh_hough_correction_count=fresh_hough_correction_count,
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
        coasted_estimated_point_count=coasted_estimated_point_count,
        interpolated_point_count=interpolated_count,
        outlier_removed_count=outlier_removed_count,
        bar_vertical_range_px=round(bar_vertical_range_px, 2),
        shoulder_vertical_range_px=round(shoulder_vertical_range_px, 2),
        final_bar_point=final_bar_point,
        final_bar_confidence=final_bar_confidence,
        final_bar_reason=final_bar_reason,
        final_bar_reason_counts=final_bar_reason_counts,
        real_hub_detection_count=real_hub_detection_count,
        hub_rejected_count=hub_rejected_count,
        path_prior_rejection_count=path_prior_rejection_count,
        path_prior_last_residual_px=path_prior_last_residual_px,
        path_prior_max_residual_px=path_prior_max_residual_px,
        path_prior_mean_residual_px=path_prior_mean_residual_px,
        selected_side=normalized_selected_side,
        coordinate_space=coordinate_space,
        collar_candidate_count=collar_candidate_count,
        collar_descriptor_score=collar_descriptor_score,
        tracklet_confirmation_count=tracklet_confirmation_count,
        bad_candidate_rejection_counts=bad_candidate_rejection_counts,
        path_reset_count=path_reset_count,
        stale_prior_expiration_count=stale_prior_expiration_count,
        reacquisition_success_count=reacquisition_success_count,
        per_rep_coverage=per_rep_coverage,
        manual_point_count=self.manual_point_count,
        automatic_point_count=self.automatic_point_count,
        manual_accepted_count=self.manual_accepted_count,
        manual_blended_count=self.manual_blended_count,
        manual_rejected_count=self.manual_rejected_count,
        manual_fallback_count=self.manual_fallback_count,
        manual_rejection_reason_counts=self.manual_rejection_reason_counts,
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
      result["diagnostics"]["manual_prior_index_matching"] = manual_prior_index_diagnostics
      result["diagnostics"]["barbell_lane_fusion"] = lane_fusion_diagnostics
      return result

    if shoulder_vertical_range_px >= 18.0 and bar_vertical_range_px < max(5.0, shoulder_vertical_range_px * 0.2):
      result = _empty_result(
        "implausible_barbell_motion",
        sampled_frame_count=sampled_count,
        detected_point_count=detected_count,
        skipped_no_pose_frame_count=skipped_no_pose_frame_count,
        processing_duration_ms=processing_duration_ms,
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        rejected_candidate_count=rejected_candidate_count,
        rejection_reason_counts=rejection_reason_counts,
        crop_width=average_crop_width,
        crop_height=average_crop_height,
        selected_plate=selected_plate,
        predicted_collar=predicted_collar,
        refined_collar=refined_collar,
        sleeve_direction=sleeve_direction,
        collar_rejection_reason="implausible_barbell_motion",
        collar_geometry_valid=collar_geometry_valid,
        fallback_used=fallback_used,
        tracking_mode=tracking_mode,
        local_tracker_type=local_tracker_type,
        initialization_confirmed=initialization_confirmed,
        initialization_frame_count=initialization_frame_count,
        hough_detection_count=hough_detection_count,
        optical_flow_point_count=optical_flow_point_count,
        optical_flow_inlier_count=optical_flow_inlier_count,
        template_match_score=template_match_score,
        local_tracking_confidence=local_tracking_confidence,
        accepted_local_tracking_count=accepted_local_tracking_count,
        fresh_hough_correction_count=fresh_hough_correction_count,
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
        coasted_estimated_point_count=coasted_estimated_point_count,
        interpolated_point_count=interpolated_count,
        outlier_removed_count=outlier_removed_count,
        bar_vertical_range_px=round(bar_vertical_range_px, 2),
        shoulder_vertical_range_px=round(shoulder_vertical_range_px, 2),
        final_bar_point=final_bar_point,
        final_bar_confidence=final_bar_confidence,
        final_bar_reason=final_bar_reason,
        final_bar_reason_counts=final_bar_reason_counts,
        real_hub_detection_count=real_hub_detection_count,
        hub_rejected_count=hub_rejected_count,
        path_prior_rejection_count=path_prior_rejection_count,
        path_prior_last_residual_px=path_prior_last_residual_px,
        path_prior_max_residual_px=path_prior_max_residual_px,
        path_prior_mean_residual_px=path_prior_mean_residual_px,
        selected_side=normalized_selected_side,
        coordinate_space=coordinate_space,
        collar_candidate_count=collar_candidate_count,
        collar_descriptor_score=collar_descriptor_score,
        tracklet_confirmation_count=tracklet_confirmation_count,
        bad_candidate_rejection_counts=bad_candidate_rejection_counts,
        path_reset_count=path_reset_count,
        stale_prior_expiration_count=stale_prior_expiration_count,
        reacquisition_success_count=reacquisition_success_count,
        per_rep_coverage=per_rep_coverage,
        manual_point_count=self.manual_point_count,
        automatic_point_count=self.automatic_point_count,
        manual_accepted_count=self.manual_accepted_count,
        manual_blended_count=self.manual_blended_count,
        manual_rejected_count=self.manual_rejected_count,
        manual_fallback_count=self.manual_fallback_count,
        manual_rejection_reason_counts=self.manual_rejection_reason_counts,
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
      result["diagnostics"]["manual_prior_index_matching"] = manual_prior_index_diagnostics
      result["diagnostics"]["barbell_lane_fusion"] = lane_fusion_diagnostics
      return result

    smoothed_points, smoothing_diagnostics = _smooth_points_with_diagnostics(
      points,
      width=width,
      height=height,
    )
    source_state_counts: dict[str, int] = {}
    source_switch_count = 0
    previous_source_state: str | None = None
    for point in smoothed_points:
      source_state = str(point.get("trackingState") or "automatic")
      source_state_counts[source_state] = source_state_counts.get(source_state, 0) + 1
      if previous_source_state is not None and source_state != previous_source_state:
        source_switch_count += 1
      previous_source_state = source_state
    manual_fusion_mean_residual_px = (
      round(sum(manual_visual_residuals) / len(manual_visual_residuals), 2)
      if manual_visual_residuals
      else None
    )
    manual_fusion_max_residual_px = (
      round(max(manual_visual_residuals), 2)
      if manual_visual_residuals
      else None
    )
    coverage = round(coverage, 3)
    point_times = [float(point["time"]) for point in smoothed_points]
    if normalized_rep_windows:
      rep_gap_by_index: dict[int, float] = {}
      for window in normalized_rep_windows:
        rep_index = int(window["rep_index"])
        start = float(window["start"])
        end = float(window["end"])
        rep_times = [time for time in point_times if start <= time <= end]
        gap_boundaries = [start, *rep_times, end]
        rep_gap_by_index[rep_index] = max(
          (next_time - previous_time for previous_time, next_time in zip(gap_boundaries, gap_boundaries[1:])),
          default=max(end - start, 0.0),
        )
      max_point_gap_seconds = max(rep_gap_by_index.values(), default=0.0)
      per_rep_coverage = [
        {
          **item,
          "max_point_gap_seconds": round(rep_gap_by_index.get(int(item["rep_index"]), 0.0), 4),
        }
        for item in per_rep_coverage
      ]
    else:
      max_point_gap_seconds = (
        max(next_time - previous_time for previous_time, next_time in zip(point_times, point_times[1:]))
        if len(point_times) >= 2
        else 0.0
      )
    effective_tracking_fps = (
      (len(point_times) - 1) / (point_times[-1] - point_times[0])
      if len(point_times) >= 2 and point_times[-1] > point_times[0]
      else 0.0
    )
    return {
      "barbellPath": {
        "available": True,
        "target": TRACKING_TARGET,
        "source": TRACKING_SOURCE,
        "coverage": coverage,
        "points": smoothed_points,
      },
      "diagnostics": {
        "available": True,
        "target": TRACKING_TARGET,
        "source": TRACKING_SOURCE,
        "coverage": coverage,
        "sampled_frame_count": sampled_count,
        "detected_point_count": detected_count,
        "manual_point_count": self.manual_point_count,
        "automatic_point_count": self.automatic_point_count,
        "manual_accepted_count": self.manual_accepted_count,
        "manual_blended_count": self.manual_blended_count,
        "manual_rejected_count": self.manual_rejected_count,
        "manual_fallback_count": self.manual_fallback_count,
        "manual_rejection_reason_counts": self.manual_rejection_reason_counts,
        "manual_validation_missing_count": manual_validation_missing_count,
        "manual_fusion_mean_residual_px": manual_fusion_mean_residual_px,
        "manual_fusion_max_residual_px": manual_fusion_max_residual_px,
        "manual_visual_offset_x": round(manual_visual_offset[0], 2) if manual_visual_offset else None,
        "manual_visual_offset_y": round(manual_visual_offset[1], 2) if manual_visual_offset else None,
        "manual_visual_offset_source": manual_visual_offset_source,
        "manual_visual_offset_frame_index": manual_visual_offset_frame_index,
        "manual_visual_recovery_active": manual_visual_recovery_active,
        "manual_visual_mismatch_streak": manual_visual_mismatch_streak,
        "manual_visual_match_streak": manual_visual_match_streak,
        "manual_visual_recovery_emitted_count": manual_visual_recovery_emitted_count,
        "manual_visual_recovery_gap_count": manual_visual_recovery_gap_count,
        "manual_prior_index_matching": manual_prior_index_diagnostics,
        "barbell_lane_fusion": lane_fusion_diagnostics,
        "source_switch_count": source_switch_count,
        "source_state_counts": source_state_counts,
        "smoothing": smoothing_diagnostics,
        "interpolated_point_count": interpolated_count,
        "coasted_estimated_point_count": coasted_estimated_point_count,
        "rejected_frame_count": max(
          sampled_count - detected_count - interpolated_count - coasted_estimated_point_count,
          0,
        ),
        "rejected_candidate_count": rejected_candidate_count,
        "rejection_reason_counts": rejection_reason_counts,
        "skipped_no_pose_frame_count": skipped_no_pose_frame_count,
        "reused_nearest_pose_frame_count": reused_nearest_pose_frame_count,
        "failure_reason": None,
        "processing_duration_ms": processing_duration_ms,
        "target_fps": BARBELL_TRACK_TARGET_FPS,
        "tracking_frame_step": tracking_frame_step,
        "tracking_mode": tracking_mode,
        "local_tracker_type": local_tracker_type,
        "initialization_confirmed": initialization_confirmed,
        "initialization_frame_count": initialization_frame_count,
        "hough_detection_count": hough_detection_count,
        "optical_flow_point_count": optical_flow_point_count,
        "optical_flow_inlier_count": optical_flow_inlier_count,
        "template_match_score": template_match_score,
        "local_tracking_confidence": round(local_tracking_confidence, 3),
        "accepted_local_tracking_count": accepted_local_tracking_count,
        "fresh_hough_correction_count": fresh_hough_correction_count,
        "max_point_gap_seconds": round(max_point_gap_seconds, 4),
        "effective_tracking_fps": round(effective_tracking_fps, 2),
        "stationary_hardware_rejection_count": stationary_hardware_rejection_count,
        "reacquisition_count": reacquisition_count,
        "local_tracking_failure_count": local_tracking_failure_count,
        "local_descriptor_bridge_count": local_descriptor_bridge_count,
        "outlier_removed_count": outlier_removed_count,
        "bar_vertical_range_px": round(bar_vertical_range_px, 2),
        "shoulder_vertical_range_px": round(shoulder_vertical_range_px, 2),
        "crop_width": average_crop_width,
        "crop_height": average_crop_height,
        "average_crop_width": average_crop_width,
        "average_crop_height": average_crop_height,
        "selected_candidate_type": "plate" if selected_plate else "none",
        "plate_center_x": round(selected_plate.x, 2) if selected_plate else None,
        "plate_center_y": round(selected_plate.y, 2) if selected_plate else None,
        "plate_radius": round(selected_plate.radius, 2) if selected_plate else None,
        "final_bar_point_x": round(final_bar_point[0], 2) if final_bar_point else None,
        "final_bar_point_y": round(final_bar_point[1], 2) if final_bar_point else None,
        "final_bar_confidence": round(final_bar_confidence, 3),
        "final_bar_reason": final_bar_reason,
        "final_bar_reason_counts": final_bar_reason_counts,
        "real_hub_detection_count": real_hub_detection_count,
        "hub_rejected_count": hub_rejected_count,
        "path_prior_rejection_count": path_prior_rejection_count,
        "path_prior_last_residual_px": path_prior_last_residual_px,
        "path_prior_max_residual_px": path_prior_max_residual_px,
        "path_prior_mean_residual_px": path_prior_mean_residual_px,
        "selected_side": normalized_selected_side,
        "coordinate_space": coordinate_space,
        "collar_candidate_count": collar_candidate_count,
        "collar_descriptor_score": collar_descriptor_score,
        "tracklet_confirmation_count": tracklet_confirmation_count,
        "bad_candidate_rejection_counts": bad_candidate_rejection_counts,
        "path_reset_count": path_reset_count,
        "stale_prior_expiration_count": stale_prior_expiration_count,
        "reacquisition_success_count": reacquisition_success_count,
        "per_rep_coverage": per_rep_coverage,
        "sleeve_direction_x": round(sleeve_direction[0], 4) if sleeve_direction else None,
        "sleeve_direction_y": round(sleeve_direction[1], 4) if sleeve_direction else None,
        "predicted_collar_x": round(predicted_collar[0], 2) if predicted_collar else None,
        "predicted_collar_y": round(predicted_collar[1], 2) if predicted_collar else None,
        "refined_collar_x": round(refined_collar[0], 2) if refined_collar else None,
        "refined_collar_y": round(refined_collar[1], 2) if refined_collar else None,
        "final_collar_x": round(refined_collar[0], 2) if refined_collar else None,
        "final_collar_y": round(refined_collar[1], 2) if refined_collar else None,
        "collar_rejection_reason": collar_rejection_reason,
        "collar_geometry_valid": collar_geometry_valid,
        "fallback_used": fallback_used,
        "bootstrap_diagnostics": self.bootstrap_diagnostics,
      },
    }
