from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any

from .candidate import Candidate
from .constants import (
  BARBELL_TRACK_TARGET_FPS,
  INIT_CONFIRMATION_FRAMES,
  MAX_LOCAL_TRACKING_FAILURES,
  MIN_TRACK_COVERAGE,
  MIN_TRACK_POINTS,
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
  _validate_collar_geometry,
)
from .local_tracker import _make_tracking_lock, _track_local_patch
from .pose import _pose_bounds
from .postprocess import _interpolate_missing, _remove_motion_outliers, _smooth_points
from .results import _empty_result
from .selection import (
  _best_initial_plate,
  _plate_rejection_reason,
  _plate_match_is_consistent,
  _pose_relative_displacement,
  _score_plate_candidate,
  _shoulder_relative_offset,
)

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


class BarbellTracker:
  def __init__(self) -> None:
    self.bootstrap_diagnostics: dict[str, Any] = {"frames": []}

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
    }
    frames.append(diagnostic)
    logger.info(
      "[BARBELL_TRACK_DIAG] frame=%s time=%.4f mode=%s source=%s plate=(%s, %s r=%s) final=(%s, %s) final_reason=%s final_conf=%s final_source=%s fallback=%s pose_pred=(%s, %s) predicted=(%s, %s) refined=(%s, %s) emitted_norm=(%s, %s) emitted_px=(%s, %s) local=%s flow_inliers=%s template=%s collar_reason=%s",
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
      if shoulder_motion >= 4.0 and point_motion <= max(1.5, shoulder_motion * 0.22):
        return "stationary_hardware_like"

    return None

  def _fresh_plate_candidate(
    self,
    cv2: Any,
    frame: Any,
    *,
    bounds: tuple[float, float, float, float],
    landmarks: dict[str, Any],
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
      landmarks=landmarks,
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

  def track(
    self,
    file_path: str,
    *,
    pose_frames: list[dict[str, Any]],
    frame_step: int,
    processed_width: int | None,
    processed_height: int | None,
    debug_output_path: str | None = None,
  ) -> dict[str, Any]:
    import cv2

    self.bootstrap_diagnostics = {"frames": []}
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

    pose_frame_step = max(int(frame_step or 1), 1)
    target_frame_step = max(int(round(fps / BARBELL_TRACK_TARGET_FPS)), 1) if fps > 0 else pose_frame_step
    tracking_frame_step = pose_frame_step * max(int(round(target_frame_step / pose_frame_step)), 1)
    pose_by_source_index = {
      int(frame.get("source_frame_index", -1)): frame
      for frame in pose_frames
      if frame.get("source_frame_index") is not None
    }
    if not pose_by_source_index:
      capture.release()
      return _empty_result(
        "no_pose_frames",
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
    )

    samples: list[dict[str, Any] | None] = []
    tracking_lock: dict[str, Any] | None = None
    pending_plate: dict[str, float] | None = None
    pending_confirmation_count = 0
    previous_gray = None
    detected_count = 0
    rejected_candidate_count = 0
    rejection_reason_counts: dict[str, int] = {}
    skipped_no_pose_frame_count = 0
    crop_widths: list[int] = []
    crop_heights: list[int] = []
    selected_plate: Candidate | None = None
    final_bar_point: tuple[float, float] | None = None
    final_bar_confidence = 0.0
    final_bar_reason: str | None = None
    final_bar_source: str | None = None
    final_bar_reason_counts: dict[str, int] = {}
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
    stationary_hardware_rejection_count = 0
    reacquisition_count = 0
    local_tracking_failure_count = 0
    consecutive_local_failures = 0
    frame_index = 0
    debug_writer = None
    sampled_shoulder_y_values: list[float] = []

    if debug_output_path:
      debug_writer = cv2.VideoWriter(
        debug_output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        BARBELL_TRACK_TARGET_FPS,
        (width, height),
      )

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
        pose_frame = pose_by_source_index.get(frame_index)
        if not pose_frame:
          skipped_no_pose_frame_count += 1
          frame_index += 1
          continue

        bounds = _pose_bounds(pose_frame, width=width, height=height)
        shoulder = bounds[4]
        if shoulder:
          sampled_shoulder_y_values.append(shoulder[1])
        landmarks = pose_frame.get("landmarks") or {}
        wrist_points = _wrist_points_from_landmarks(landmarks, width=width, height=height)
        candidate_bounds = bounds[:4]

        if tracking_lock and previous_gray is not None and consecutive_local_failures <= MAX_LOCAL_TRACKING_FAILURES:
          next_lock, local_stats = _track_local_patch(
            cv2,
            previous_gray,
            gray,
            tracking_lock,
            shoulder=shoulder,
            width=width,
            height=height,
          )
          optical_flow_point_count = local_stats["optical_flow_point_count"]
          optical_flow_inlier_count = local_stats["optical_flow_inlier_count"]
          template_match_score = local_stats["template_match_score"]
          local_tracker_type = local_stats["local_tracker_type"]
          fallback_used = bool(local_stats["fallback_used"])
          collar_rejection_reason = local_stats["collar_rejection_reason"]
          hub_result_for_debug: dict[str, Any] | None = None

          if next_lock:
            pose_predicted_point = self._pose_predicted_bar_point(tracking_lock, shoulder)
            local_final_bar_point = next_lock.get("final_bar_point") or (
              next_lock["plate"].x,
              next_lock["plate"].y,
            )
            local_final_rejection_reason = self._final_bar_point_is_motion_consistent(
              local_final_bar_point,
              previous=tracking_lock,
              shoulder=shoulder,
              width=width,
              height=height,
            )
            fresh_plate = self._fresh_plate_candidate(
              cv2,
              frame,
              bounds=candidate_bounds,
              landmarks=landmarks,
              previous=tracking_lock,
              shoulder=shoulder,
              width=width,
              height=height,
            )
            if fresh_plate:
              fresh_hub_result = self._final_bar_point_from_plate(
                cv2,
                frame,
                plate=fresh_plate,
                previous=tracking_lock,
              )
              hub_result_for_debug = fresh_hub_result
              fresh_final_bar_point = fresh_hub_result.get("point")
              fresh_motion_reason = (
                self._final_bar_point_is_motion_consistent(
                  fresh_final_bar_point,
                  previous=tracking_lock,
                  shoulder=shoulder,
                  width=width,
                  height=height,
                )
                if fresh_final_bar_point
                else None
              )
              if self._hub_result_is_emit_safe(fresh_hub_result) and fresh_motion_reason is None and fresh_final_bar_point:
                fresh_predicted_collar, fresh_sleeve_direction = _estimate_collar_from_plate(
                  fresh_plate,
                  shoulder=shoulder,
                  width=width,
                  height=height,
                  previous=tracking_lock,
                )
                fresh_refined_collar, _, fresh_refinement_reason = _refine_collar_point(
                  cv2,
                  frame,
                  predicted=fresh_predicted_collar,
                  plate=fresh_plate,
                  sleeve_direction=fresh_sleeve_direction,
                  previous=tracking_lock,
                )
                fresh_geometry_reason = _validate_collar_geometry(
                  fresh_refined_collar,
                  plate=fresh_plate,
                  sleeve_direction=fresh_sleeve_direction,
                  previous=tracking_lock,
                )
                if fresh_refinement_reason or fresh_geometry_reason:
                  fresh_refined_collar = fresh_predicted_collar
                next_lock = _make_tracking_lock(
                  cv2,
                  gray,
                  plate=fresh_plate,
                  collar=fresh_refined_collar,
                  sleeve_direction=fresh_sleeve_direction,
                  final_bar_point=fresh_final_bar_point,
                  final_bar_confidence=float(fresh_hub_result.get("confidence") or 0.0),
                  final_bar_reason=fresh_hub_result.get("reason"),
                  shoulder=shoulder,
                )
                next_lock["predicted_collar"] = fresh_predicted_collar
                next_lock["refined_collar"] = fresh_refined_collar
                next_lock["collar_geometry_valid"] = fresh_geometry_reason is None
                next_lock["fallback_used"] = bool(fresh_refinement_reason or fresh_geometry_reason)
                next_lock["final_bar_source"] = fresh_hub_result.get("source")
                local_tracker_type = "fresh_hough_validation"
                local_stats["local_tracker_type"] = local_tracker_type
                collar_rejection_reason = fresh_refinement_reason or fresh_geometry_reason
                local_stats["collar_rejection_reason"] = collar_rejection_reason
                local_final_rejection_reason = None
              else:
                next_lock = None
                local_final_rejection_reason = fresh_motion_reason or fresh_hub_result.get("reason") or "low_confidence_hub"
                local_stats["collar_rejection_reason"] = local_final_rejection_reason
                collar_rejection_reason = local_final_rejection_reason
            else:
              next_lock = None
              local_final_rejection_reason = "fresh_hub_not_found"
              local_stats["collar_rejection_reason"] = local_final_rejection_reason
              collar_rejection_reason = local_final_rejection_reason

            if local_final_rejection_reason:
              next_lock = None
              local_stats["collar_rejection_reason"] = local_final_rejection_reason
              collar_rejection_reason = local_final_rejection_reason

          if next_lock:

            tracking_mode = "local_tracking"
            tracking_lock = next_lock
            selected_plate = tracking_lock["plate"]
            final_bar_point = tracking_lock.get("final_bar_point") or (selected_plate.x, selected_plate.y)
            final_bar_confidence = float(tracking_lock.get("final_bar_confidence", 0.65))
            final_bar_reason = tracking_lock.get("final_bar_reason")
            final_bar_source = tracking_lock.get("final_bar_source")
            predicted_collar = tracking_lock["predicted_collar"]
            refined_collar = tracking_lock["refined_collar"]
            sleeve_direction = (tracking_lock["collar_direction_x"], tracking_lock["collar_direction_y"])
            collar_geometry_valid = True
            consecutive_local_failures = 0
            point = {
              "time": timestamp,
              "x": final_bar_point[0] / width,
              "y": final_bar_point[1] / height,
              "confidence": min(float(selected_plate.confidence) + 0.2, 1.0),
            }
            real_hub_detection_count += 1
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
            )
            samples.append(point)
            detected_count += 1
            previous_gray = gray
            if debug_writer:
              debug_writer.write(
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
          if collar_rejection_reason:
            hub_rejected_count += 1
            final_bar_reason_counts[collar_rejection_reason] = final_bar_reason_counts.get(collar_rejection_reason, 0) + 1
          if collar_rejection_reason == "stationary_hardware_like":
            stationary_hardware_rejection_count += 1
          if consecutive_local_failures <= MAX_LOCAL_TRACKING_FAILURES:
            tracking_mode = "local_tracking"
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
            )
            samples.append(None)
            # Keep previous_gray aligned with tracking_lock/features after a failed local update.
            if debug_writer:
              debug_writer.write(
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
          landmarks=landmarks,
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
            debug_writer.write(
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

        selected_plate = _best_initial_plate(
          plausible_candidates,
          pending_plate=pending_plate,
          shoulder=shoulder,
          width=width,
          height=height,
        )
        if not selected_plate:
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
        next_pending = {
          "x": selected_plate.x,
          "y": selected_plate.y,
          "dx": selected_offset[0] if selected_offset else 0.0,
          "dy": selected_offset[1] if selected_offset else 0.0,
          "radius": selected_plate.radius,
          "shoulder_x": shoulder[0] if shoulder else selected_plate.x,
          "shoulder_y": shoulder[1] if shoulder else selected_plate.y,
        }
        pose_relative_displacement = (
          _pose_relative_displacement(selected_plate, previous=pending_plate, shoulder=shoulder)
          if pending_plate
          else None
        )
        bootstrap_consistency_reason = (
          self._final_bar_point_is_motion_consistent(
            (selected_plate.x, selected_plate.y),
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
          and _plate_match_is_consistent(selected_plate, pending_plate, shoulder=shoulder, width=width, height=height)
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
            debug_writer.write(
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

        predicted_collar, sleeve_direction = _estimate_collar_from_plate(
          selected_plate,
          shoulder=shoulder,
          width=width,
          height=height,
          previous=None,
        )
        refined_candidate, collar_confidence_penalty, collar_refinement_reason = _refine_collar_point(
          cv2,
          frame,
          predicted=predicted_collar,
          plate=selected_plate,
          sleeve_direction=sleeve_direction,
          previous=None,
        )
        collar_rejection_reason = _validate_collar_geometry(
          refined_candidate,
          plate=selected_plate,
          sleeve_direction=sleeve_direction,
          previous=None,
        )
        fallback_used = collar_rejection_reason is not None
        if collar_refinement_reason is not None:
          fallback_used = True
          collar_rejection_reason = collar_refinement_reason
        refined_collar = predicted_collar if fallback_used else refined_candidate
        final_geometry_reason = _validate_collar_geometry(
          refined_collar,
          plate=selected_plate,
          sleeve_direction=sleeve_direction,
          previous=None,
        )
        if final_geometry_reason is not None:
          collar_rejection_reason = final_geometry_reason
        elif collar_refinement_reason is not None:
          collar_rejection_reason = collar_refinement_reason
        collar_geometry_valid = final_geometry_reason is None
        if not collar_geometry_valid:
          self._record_tracking_frame_diagnostic(
            frame_index=frame_index,
            timestamp=timestamp,
            tracking_mode=tracking_mode,
            selected_plate=selected_plate,
            final_bar_point=None,
            pose_predicted_point=None,
            predicted_collar=predicted_collar,
            refined_collar=None,
            point=None,
            width=width,
            height=height,
            local_tracker_type=local_tracker_type,
            optical_flow_inlier_count=optical_flow_inlier_count,
            template_match_score=template_match_score,
            collar_rejection_reason=collar_rejection_reason,
            point_source="no_emission",
          )
          samples.append(None)
          if debug_writer:
            debug_writer.write(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=debug_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=selected_plate,
                final_bar_point=None,
                pose_predicted_point=None,
                predicted_collar=predicted_collar,
                refined_collar=None,
                rejection_reason=collar_rejection_reason,
                mode=tracking_mode,
              )
            )
          previous_gray = gray
          frame_index += 1
          continue

        hub_result = self._final_bar_point_from_plate(
          cv2,
          frame,
          plate=selected_plate,
          previous=None,
        )
        final_bar_point = hub_result.get("point")
        final_bar_confidence = float(hub_result.get("confidence") or 0.0)
        final_bar_reason = hub_result.get("reason")
        final_bar_source = hub_result.get("source")
        if not self._hub_result_is_emit_safe(hub_result) or final_bar_point is None:
          collar_rejection_reason = final_bar_reason or "low_confidence_hub"
          hub_rejected_count += 1
          final_bar_reason_counts[collar_rejection_reason] = final_bar_reason_counts.get(collar_rejection_reason, 0) + 1
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
            collar_rejection_reason=collar_rejection_reason,
            point_source="no_emission",
            final_bar_reason=collar_rejection_reason,
            final_bar_confidence=final_bar_confidence,
            final_bar_source=final_bar_source,
            fallback_used=fallback_used,
          )
          samples.append(None)
          if debug_writer:
            debug_writer.write(
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
                rejection_reason=collar_rejection_reason,
                mode=tracking_mode,
              )
            )
          previous_gray = gray
          frame_index += 1
          continue

        confidence = max(
          min(
            _score_plate_candidate(
              selected_plate,
              previous=pending_plate,
              shoulder=shoulder,
              width=width,
              height=height,
            ),
            1.0,
          ) - collar_confidence_penalty,
          0.0,
        )
        if final_bar_reason is not None:
          confidence = min(confidence, max(final_bar_confidence, 0.42))
        point = {
          "time": timestamp,
          "x": final_bar_point[0] / width,
          "y": final_bar_point[1] / height,
          "confidence": confidence,
        }
        real_hub_detection_count += 1
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
        )
        relative_offset = _shoulder_relative_offset(selected_plate, shoulder)
        tracking_lock = _make_tracking_lock(
          cv2,
          gray,
          plate=selected_plate,
          collar=refined_collar,
          sleeve_direction=sleeve_direction,
          final_bar_point=final_bar_point,
          final_bar_confidence=final_bar_confidence,
          final_bar_reason=final_bar_reason,
          shoulder=shoulder,
        )
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
          }
        )
        samples.append(point)
        detected_count += 1
        previous_gray = gray
        if debug_writer:
          debug_writer.write(
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
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
      return result

    points, interpolated_count = _interpolate_missing(samples)
    points, outlier_removed_count = _remove_motion_outliers(points)
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
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
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
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
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
        stationary_hardware_rejection_count=stationary_hardware_rejection_count,
        reacquisition_count=reacquisition_count,
        local_tracking_failure_count=local_tracking_failure_count,
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
      )
      result["diagnostics"]["bootstrap_diagnostics"] = self.bootstrap_diagnostics
      return result

    smoothed_points = _smooth_points(points)
    coverage = round(coverage, 3)
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
        "interpolated_point_count": interpolated_count,
        "rejected_frame_count": max(sampled_count - detected_count - interpolated_count, 0),
        "rejected_candidate_count": rejected_candidate_count,
        "rejection_reason_counts": rejection_reason_counts,
        "skipped_no_pose_frame_count": skipped_no_pose_frame_count,
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
        "stationary_hardware_rejection_count": stationary_hardware_rejection_count,
        "reacquisition_count": reacquisition_count,
        "local_tracking_failure_count": local_tracking_failure_count,
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
