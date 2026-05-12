from __future__ import annotations

from typing import Any

from ..feedback_engine import build_feedback
from ..metrics_calculator import (
  hip_depth_ratio,
  point_for_side,
  select_tracking_side,
  squat_depth_score,
  torso_angle_change,
  torso_angle_from_vertical,
)
from ..rep_detector import detect_reps
from .base import BaseExerciseAnalyzer


class SquatAnalyzer(BaseExerciseAnalyzer):
  def analyze(
    self,
    *,
    video_id: str,
    exercise_type: str,
    view_type: str,
    frames: list[dict[str, Any]],
  ) -> dict[str, Any]:
    tracking_side_per_frame = [select_tracking_side(frame) for frame in frames]
    hip_depths = []

    for frame, side in zip(frames, tracking_side_per_frame, strict=False):
      shoulder = point_for_side(frame, side, "shoulder")
      hip = point_for_side(frame, side, "hip")
      ankle = point_for_side(frame, side, "ankle")
      hip_depths.append(hip_depth_ratio(shoulder, hip, ankle))

    reps = detect_reps(hip_depths, frames)
    rep_summaries: list[dict[str, Any]] = []

    for rep_index, rep in enumerate(reps, start=1):
      start_frame = frames[rep["start_index"]]
      bottom_frame = frames[rep["bottom_index"]]
      side = tracking_side_per_frame[rep["bottom_index"]]

      start_shoulder = point_for_side(start_frame, side, "shoulder")
      start_hip = point_for_side(start_frame, side, "hip")
      bottom_shoulder = point_for_side(bottom_frame, side, "shoulder")
      bottom_hip = point_for_side(bottom_frame, side, "hip")
      bottom_knee = point_for_side(bottom_frame, side, "knee")
      bottom_ankle = point_for_side(bottom_frame, side, "ankle")

      start_torso = torso_angle_from_vertical(start_shoulder, start_hip)
      bottom_torso = torso_angle_from_vertical(bottom_shoulder, bottom_hip)
      depth_score = squat_depth_score(bottom_hip, bottom_knee, bottom_ankle)
      torso_delta = torso_angle_change(start_torso, bottom_torso)

      flags: list[str] = []
      if depth_score < 0.6:
        flags.append("insufficient_depth")
      if bottom_torso > 42 or torso_delta > 18:
        flags.append("forward_lean")

      rep_summaries.append(
        {
          "rep_index": rep_index,
          "depth_score": depth_score,
          "torso_angle": round(bottom_torso, 2),
          "torso_angle_change": torso_delta,
          "flags": flags,
          "timestamps_ms": {
            "start": rep["start_timestamp_ms"],
            "bottom": rep["bottom_timestamp_ms"],
            "end": rep["end_timestamp_ms"],
          },
        }
      )

    summary_flags, coach_feedback = build_feedback(rep_summaries)

    return {
      "video_id": video_id,
      "exercise": exercise_type,
      "view": view_type,
      "analysis_limited": False,
      "rep_count": len(rep_summaries),
      "reps": rep_summaries,
      "summary_flags": summary_flags,
      "coach_feedback": coach_feedback,
    }
