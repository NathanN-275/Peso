from __future__ import annotations

from typing import Any

from ..metrics_calculator import clamp, joint_angle
from .base import BaseExerciseAnalyzer
from .squat import _build_pose_frames


PRESSING_EXERCISES = {
  "bench press",
  "incline bench press",
  "overhead press",
}

MIN_PRESS_REP_AMPLITUDE = 0.035
LOW_CONFIDENCE_THRESHOLD = 0.45


def is_pressing_exercise(exercise_type: str) -> bool:
  return exercise_type.strip().lower() in PRESSING_EXERCISES


def _point(frame: dict[str, Any], name: str) -> dict[str, float] | None:
  point = (frame.get("landmarks") or {}).get(name)
  if not isinstance(point, dict):
    return None
  return {
    "x": float(point.get("x", 0.0) or 0.0),
    "y": float(point.get("y", 0.0) or 0.0),
    "z": float(point.get("z", 0.0) or 0.0),
    "visibility": float(point.get("visibility", 0.0) or 0.0),
  }


def _average_points(points: list[dict[str, float]]) -> dict[str, float] | None:
  usable = [point for point in points if point.get("visibility", 0.0) >= 0.15]
  if not usable:
    return None
  total_visibility = sum(max(point["visibility"], 0.01) for point in usable)
  return {
    "x": sum(point["x"] * max(point["visibility"], 0.01) for point in usable) / total_visibility,
    "y": sum(point["y"] * max(point["visibility"], 0.01) for point in usable) / total_visibility,
    "z": sum(point.get("z", 0.0) * max(point["visibility"], 0.01) for point in usable) / total_visibility,
    "visibility": max(point["visibility"] for point in usable),
  }


def _pose_bar_proxy(frame: dict[str, Any]) -> dict[str, float] | None:
  wrists = [
    point for point in (_point(frame, "left_wrist"), _point(frame, "right_wrist"))
    if point is not None
  ]
  return _average_points(wrists)


def _signal_from_pose(frames: list[dict[str, Any]]) -> list[dict[str, float]]:
  signal: list[dict[str, float]] = []
  for frame in frames:
    proxy = _pose_bar_proxy(frame)
    if proxy is None:
      continue
    signal.append({
      "time": float(frame.get("timestamp_ms", 0.0) or 0.0) / 1000.0,
      "x": proxy["x"],
      "y": proxy["y"],
      "confidence": proxy["visibility"],
      "source": "pose_wrist_proxy",
    })
  return signal


def _signal_from_barbell_path(barbell_path: dict[str, Any] | None) -> list[dict[str, float]]:
  if not isinstance(barbell_path, dict) or not barbell_path.get("available"):
    return []
  signal: list[dict[str, float]] = []
  for point in barbell_path.get("points") or []:
    if not isinstance(point, dict):
      continue
    if not all(isinstance(point.get(name), (int, float)) for name in ("time", "x", "y")):
      continue
    confidence = float(point.get("confidence") or 0.0)
    if confidence < 0.15:
      continue
    signal.append({
      "time": float(point["time"]),
      "x": float(point["x"]),
      "y": float(point["y"]),
      "confidence": confidence,
      "source": str(point.get("selectedSource") or point.get("source") or "barbell_path"),
    })
  return sorted(signal, key=lambda item: item["time"])


def _detect_press_reps(signal: list[dict[str, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  if len(signal) < 3:
    return [], {
      "reason": "insufficient_press_motion_signal",
      "motion_amplitude": 0.0,
      "source": signal[0]["source"] if signal else None,
    }

  smoothed = signal
  y_values = [point["y"] for point in smoothed]
  amplitude = max(y_values) - min(y_values)
  if amplitude < MIN_PRESS_REP_AMPLITUDE:
    return [], {
      "reason": "insufficient_press_motion_signal",
      "motion_amplitude": round(amplitude, 4),
      "source": smoothed[0]["source"],
    }

  top_threshold = min(y_values) + (amplitude * 0.35)
  bottom_threshold = min(y_values) + (amplitude * 0.72)
  reps: list[dict[str, Any]] = []
  state = "seeking_bottom"
  start_index = 0
  bottom_index: int | None = None

  for index, point in enumerate(smoothed):
    if state == "seeking_bottom" and point["y"] >= bottom_threshold:
      bottom_index = index
      state = "seeking_top"
      continue
    if state == "seeking_top" and bottom_index is not None:
      if point["y"] > smoothed[bottom_index]["y"]:
        bottom_index = index
      if point["y"] <= top_threshold:
        top_index = index
        rep_points = smoothed[start_index:top_index + 1]
        reps.append({
          "start_index": start_index,
          "bottom_index": bottom_index,
          "top_index": top_index,
          "end_index": top_index,
          "start_time": smoothed[start_index]["time"],
          "bottom_time": smoothed[bottom_index]["time"],
          "top_time": smoothed[top_index]["time"],
          "end_time": smoothed[top_index]["time"],
          "bar_travel": smoothed[bottom_index]["y"] - smoothed[top_index]["y"],
          "path_drift": abs(smoothed[bottom_index]["x"] - smoothed[top_index]["x"]),
          "confidence": sum(point["confidence"] for point in rep_points) / len(rep_points),
        })
        start_index = top_index
        bottom_index = None
        state = "seeking_bottom"

  return reps, {
    "reason": None if reps else "no_complete_press_reps",
    "motion_amplitude": round(amplitude, 4),
    "source": smoothed[0]["source"],
    "top_threshold": round(top_threshold, 4),
    "bottom_threshold": round(bottom_threshold, 4),
  }


def _nearest_frame(frames: list[dict[str, Any]], time_seconds: float) -> dict[str, Any] | None:
  if not frames:
    return None
  return min(
    frames,
    key=lambda frame: abs((float(frame.get("timestamp_ms", 0.0) or 0.0) / 1000.0) - time_seconds),
  )


def _elbow_angle(frame: dict[str, Any], side: str) -> float | None:
  shoulder = _point(frame, f"{side}_shoulder")
  elbow = _point(frame, f"{side}_elbow")
  wrist = _point(frame, f"{side}_wrist")
  if not shoulder or not elbow or not wrist:
    return None
  if min(shoulder["visibility"], elbow["visibility"], wrist["visibility"]) < 0.2:
    return None
  return joint_angle(shoulder, elbow, wrist)


def _average_elbow_angle(frame: dict[str, Any] | None) -> float | None:
  if frame is None:
    return None
  angles = [
    angle for angle in (_elbow_angle(frame, "left"), _elbow_angle(frame, "right"))
    if angle is not None
  ]
  return sum(angles) / len(angles) if angles else None


def _elbow_angle_for_side(frame: dict[str, Any] | None, side: str | None) -> float | None:
  if side in {"left", "right"}:
    return _elbow_angle(frame or {}, side)
  return _average_elbow_angle(frame)


def _front_symmetry_delta(frame: dict[str, Any] | None) -> float | None:
  if frame is None:
    return None
  left = _point(frame, "left_wrist")
  right = _point(frame, "right_wrist")
  if not left or not right or min(left["visibility"], right["visibility"]) < 0.35:
    return None
  return abs(left["y"] - right["y"])


class PressingAnalyzer(BaseExerciseAnalyzer):
  def analyze(
    self,
    *,
    video_id: str,
    exercise_type: str,
    view_type: str,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
    barbell_path: dict[str, Any] | None = None,
    selected_side: str | None = None,
  ) -> dict[str, Any]:
    signal = _signal_from_barbell_path(barbell_path) or _signal_from_pose(frames)
    reps, rep_detection = _detect_press_reps(signal)
    pose_coverage = len(frames) / max(sampled_frame_count or len(frames), 1)
    upper_body_visibilities: list[float] = []
    for frame in frames:
      points = [
        point for point in (
          _point(frame, "left_shoulder"),
          _point(frame, "right_shoulder"),
          _point(frame, "left_elbow"),
          _point(frame, "right_elbow"),
          _point(frame, "left_wrist"),
          _point(frame, "right_wrist"),
        )
        if point is not None
      ]
      if points:
        upper_body_visibilities.append(sum(point["visibility"] for point in points) / len(points))
    upper_body_visibility = (
      sum(upper_body_visibilities) / len(upper_body_visibilities)
      if upper_body_visibilities
      else 0.0
    )
    quality_flags: list[str] = []
    if pose_coverage < 0.55:
      quality_flags.append("low_pose_coverage")
    if upper_body_visibility < 0.50:
      quality_flags.append("upper_body_occluded")
    if rep_detection.get("reason"):
      quality_flags.append(str(rep_detection["reason"]))

    rep_summaries: list[dict[str, Any]] = []
    for index, rep in enumerate(reps, start=1):
      top_frame = _nearest_frame(frames, rep["top_time"])
      bottom_frame = _nearest_frame(frames, rep["bottom_time"])
      top_elbow_angle = _elbow_angle_for_side(top_frame, selected_side)
      bottom_elbow_angle = _elbow_angle_for_side(bottom_frame, selected_side)
      elbow_range = (
        abs(top_elbow_angle - bottom_elbow_angle)
        if top_elbow_angle is not None and bottom_elbow_angle is not None
        else None
      )
      symmetry_delta = _front_symmetry_delta(top_frame) if view_type == "front" else None
      flags: list[str] = []
      if rep["confidence"] < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low_tracking_confidence")
      else:
        if rep["bar_travel"] < 0.055:
          flags.append("short_range_of_motion")
        if top_elbow_angle is not None and top_elbow_angle < 155:
          flags.append("incomplete_lockout")
        if rep["path_drift"] > 0.08:
          flags.append("bar_path_drift")
        if symmetry_delta is not None and symmetry_delta > 0.045:
          flags.append("front_view_asymmetry")

      rep_summaries.append({
        "rep_index": index,
        "startTime": round(rep["start_time"], 3),
        "bottomTime": round(rep["bottom_time"], 3),
        "endTime": round(rep["end_time"], 3),
        "duration": round(max(rep["end_time"] - rep["start_time"], 0.0), 3),
        "confidence": round(rep["confidence"], 3),
        "bar_travel": round(rep["bar_travel"], 4),
        "barTravel": round(rep["bar_travel"], 4),
        "path_drift": round(rep["path_drift"], 4),
        "pathDrift": round(rep["path_drift"], 4),
        "top_elbow_angle": round(top_elbow_angle, 1) if top_elbow_angle is not None else None,
        "topElbowAngle": round(top_elbow_angle, 1) if top_elbow_angle is not None else None,
        "elbow_range": round(elbow_range, 1) if elbow_range is not None else None,
        "elbowRange": round(elbow_range, 1) if elbow_range is not None else None,
        "front_symmetry_delta": round(symmetry_delta, 4) if symmetry_delta is not None else None,
        "frontSymmetryDelta": round(symmetry_delta, 4) if symmetry_delta is not None else None,
        "flags": flags,
      })

    summary_flags = sorted({flag for rep in rep_summaries for flag in rep.get("flags", [])})
    if not rep_summaries and rep_detection.get("reason"):
      summary_flags.append(str(rep_detection["reason"]))
    coaching_feedback = _feedback_for_flags(summary_flags)
    quality_score = clamp((pose_coverage * 0.45) + (upper_body_visibility * 0.45) + (0.10 if reps else 0.0), 0.0, 1.0)

    return {
      "video_id": video_id,
      "exercise": exercise_type,
      "view": view_type,
      "analysis_limited": False,
      "rep_count": len(rep_summaries),
      "reps": rep_summaries,
      "summary_flags": summary_flags,
      "summaryFlags": summary_flags,
      "coach_feedback": coaching_feedback,
      "coachingFeedback": coaching_feedback,
      "videoId": video_id,
      "cameraView": view_type,
      "duration": 0,
      "poseFrames": _build_pose_frames(frames),
      "diagnostics": {
        "quality_score": round(quality_score, 3),
        "pose_coverage": round(pose_coverage, 3),
        "upper_body_visibility": round(upper_body_visibility, 3),
        "quality_flags": quality_flags,
        "rep_detection": rep_detection,
        "pressing_analysis": {
          "barbell_path_used": bool(_signal_from_barbell_path(barbell_path)),
          "signal_point_count": len(signal),
          "selected_side": selected_side if selected_side in {"left", "right"} else None,
          "pin_guided_wrist_signal_used": any(
            point.get("source") == "manual_wrist_lane" for point in signal
          ),
        },
      },
      "videoQuality": {
        "overallQuality": round(quality_score, 3),
        "poseCoverage": round(pose_coverage, 3),
        "upperBodyVisibility": round(upper_body_visibility, 3),
        "pressMotionSignal": rep_detection.get("motion_amplitude", 0.0),
      },
    }


def _feedback_for_flags(flags: list[str]) -> list[str]:
  messages = {
    "low_tracking_confidence": "Press tracking confidence was limited, so form warnings were withheld for affected reps.",
    "short_range_of_motion": "Some reps had shorter bar travel than expected for a full press.",
    "incomplete_lockout": "Some reps may not have reached a clear elbow lockout.",
    "bar_path_drift": "Some reps showed noticeable horizontal bar path drift.",
    "front_view_asymmetry": "Front-view tracking found a left-right height mismatch near lockout.",
    "insufficient_press_motion_signal": "Press rep motion was too small or unclear to count reliably.",
    "no_complete_press_reps": "No complete press reps were detected in this clip.",
  }
  return [messages[flag] for flag in flags if flag in messages]
