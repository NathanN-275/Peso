from __future__ import annotations

import logging
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
from .geometry import _estimate_collar_from_plate, _refine_collar_point, _validate_collar_geometry
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
        landmarks = pose_frame.get("landmarks") or {}
        wrist_points = _wrist_points_from_landmarks(landmarks, width=width, height=height)

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

          if next_lock:
            tracking_mode = "local_tracking"
            tracking_lock = next_lock
            selected_plate = tracking_lock["plate"]
            predicted_collar = tracking_lock["predicted_collar"]
            refined_collar = tracking_lock["refined_collar"]
            sleeve_direction = (tracking_lock["collar_direction_x"], tracking_lock["collar_direction_y"])
            collar_geometry_valid = True
            consecutive_local_failures = 0
            samples.append(
              {
                "time": timestamp,
                "x": refined_collar[0] / width,
                "y": refined_collar[1] / height,
                "confidence": min(float(selected_plate.confidence) + 0.25, 1.0),
              }
            )
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
                  predicted_collar=predicted_collar,
                  refined_collar=refined_collar,
                  mode=tracking_mode,
                )
              )
            frame_index += 1
            continue

          local_tracking_failure_count += 1
          consecutive_local_failures += 1
          if collar_rejection_reason == "stationary_hardware_like":
            stationary_hardware_rejection_count += 1
          if consecutive_local_failures <= MAX_LOCAL_TRACKING_FAILURES:
            tracking_mode = "local_tracking"
            samples.append(None)
            previous_gray = gray
            if debug_writer:
              debug_writer.write(
                _draw_debug_frame(
                  cv2,
                  frame,
                  bounds=bounds[:4],
                  candidates=[],
                  rejected=[],
                  selected_plate=tracking_lock["plate"],
                  predicted_collar=tracking_lock.get("predicted_collar"),
                  refined_collar=None,
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

        candidate_bounds = bounds[:4]
        hough_detection_count += 1
        candidates, crop_width, crop_height, detection_diagnostics = _detect_crop_candidates(
          cv2,
          frame,
          candidate_bounds,
          landmarks=landmarks,
        )
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
          samples.append(None)
          if debug_writer:
            debug_writer.write(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=candidate_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=None,
                predicted_collar=None,
                refined_collar=None,
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
        if pending_plate and _plate_match_is_consistent(selected_plate, pending_plate, shoulder=shoulder, width=width, height=height):
          pending_confirmation_count += 1
          if pose_relative_displacement is not None:
            bootstrap_pose_relative_displacements.append(round(pose_relative_displacement, 3))
        else:
          pending_confirmation_count = 1
          bootstrap_pose_relative_displacements = [0.0]
        pending_plate = next_pending
        if pending_confirmation_count < INIT_CONFIRMATION_FRAMES:
          samples.append(None)
          previous_gray = gray
          if debug_writer:
            debug_writer.write(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=candidate_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=selected_plate,
                predicted_collar=None,
                refined_collar=None,
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
          previous=pending_plate,
        )
        refined_candidate, collar_confidence_penalty, collar_refinement_reason = _refine_collar_point(
          cv2,
          frame,
          predicted=predicted_collar,
          plate=selected_plate,
          sleeve_direction=sleeve_direction,
          previous=pending_plate,
        )
        collar_rejection_reason = _validate_collar_geometry(
          refined_candidate,
          plate=selected_plate,
          sleeve_direction=sleeve_direction,
          previous=pending_plate,
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
          previous=pending_plate,
        )
        if final_geometry_reason is not None:
          collar_rejection_reason = final_geometry_reason
        elif collar_refinement_reason is not None:
          collar_rejection_reason = collar_refinement_reason
        collar_geometry_valid = final_geometry_reason is None
        if not collar_geometry_valid:
          samples.append(None)
          if debug_writer:
            debug_writer.write(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=candidate_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=selected_plate,
                predicted_collar=predicted_collar,
                refined_collar=None,
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
        point = {
          "time": timestamp,
          "x": refined_collar[0] / width,
          "y": refined_collar[1] / height,
          "confidence": confidence,
        }
        relative_offset = _shoulder_relative_offset(selected_plate, shoulder)
        tracking_lock = _make_tracking_lock(
          cv2,
          gray,
          plate=selected_plate,
          collar=refined_collar,
          sleeve_direction=sleeve_direction,
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
              bounds=candidate_bounds,
              candidates=candidates,
              rejected=rejected,
              selected_plate=selected_plate,
              predicted_collar=predicted_collar,
              refined_collar=refined_collar,
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
        outlier_removed_count=outlier_removed_count,
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
        "crop_width": average_crop_width,
        "crop_height": average_crop_height,
        "average_crop_width": average_crop_width,
        "average_crop_height": average_crop_height,
        "selected_candidate_type": "plate" if selected_plate else "none",
        "plate_center_x": round(selected_plate.x, 2) if selected_plate else None,
        "plate_center_y": round(selected_plate.y, 2) if selected_plate else None,
        "plate_radius": round(selected_plate.radius, 2) if selected_plate else None,
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
