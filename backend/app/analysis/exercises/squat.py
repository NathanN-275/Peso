from __future__ import annotations

from typing import Any

from ..feedback_engine import build_feedback
from ..metrics_calculator import (
  average_visibility,
  blended_point,
  clamp,
  hip_flexion_score,
  hip_depth_ratio,
  knee_flexion_score,
  point_for_side,
  select_tracking_side_for_clip,
  squat_depth_score,
  torso_angle_change,
  torso_angle_from_vertical,
)
from ..rep_detector import detect_reps
from .base import BaseExerciseAnalyzer


def _build_pose_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [
    {
      "time": frame["timestamp_ms"] / 1000,
      "keypoints": [
        {
          "name": name,
          "x": point["x"],
          "y": point["y"],
          "confidence": point["visibility"],
        }
        for name, point in frame["landmarks"].items()
      ],
    }
    for frame in frames
  ]


def _calculate_velocity_stats(
  *,
  frames: list[dict[str, Any]],
  start_index: int,
  end_index: int,
) -> dict[str, float]:
  if end_index <= start_index:
    return {
      "avg_velocity": 0.0,
      "peak_velocity": 0.0,
    }

  hip_points = [
    (
      frames[index]["timestamp_ms"] / 1000,
      blended_point(frames[index], "hip")["y"],
    )
    for index in range(start_index, end_index + 1)
  ]
  velocities: list[float] = []
  total_distance = 0.0

  for previous, current in zip(hip_points, hip_points[1:], strict=False):
    previous_time, previous_y = previous
    current_time, current_y = current
    elapsed = current_time - previous_time

    if elapsed <= 0:
      continue

    distance = abs(current_y - previous_y)
    total_distance += distance
    velocities.append(distance / elapsed)

  duration = hip_points[-1][0] - hip_points[0][0]

  return {
    "avg_velocity": round(total_distance / duration, 3) if duration > 0 else 0.0,
    "peak_velocity": round(max(velocities), 3) if velocities else 0.0,
  }


class SquatAnalyzer(BaseExerciseAnalyzer):
  def _build_quality_report(
    self,
    *,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
  ) -> dict[str, Any]:
    if not frames:
      return {
        "quality_score": 0.0,
        "pose_coverage": 0.0,
        "lower_body_visibility": 0.0,
        "subject_height": 0.0,
        "side_view_score": 0.0,
        "selected_side": None,
        "tracking_side_confidence": 0.0,
        "quality_flags": ["low_pose_coverage"],
      }

    selected_side, tracking_confidence = select_tracking_side_for_clip(frames)
    pose_coverage = len(frames) / max(sampled_frame_count or len(frames), 1)
    lower_body_visibility = sum(
      (
        point_for_side(frame, selected_side, "hip")["visibility"]
        + point_for_side(frame, selected_side, "knee")["visibility"]
        + point_for_side(frame, selected_side, "ankle")["visibility"]
      ) / 3
      for frame in frames
    ) / len(frames)
    subject_heights: list[float] = []
    side_view_scores: list[float] = []

    for frame in frames:
      landmarks = frame["landmarks"]
      tracked_points = [
        point_for_side(frame, selected_side, "shoulder"),
        point_for_side(frame, selected_side, "hip"),
        point_for_side(frame, selected_side, "knee"),
        point_for_side(frame, selected_side, "ankle"),
      ]
      y_values = [point["y"] for point in tracked_points if point["visibility"] >= 0.35]

      if y_values:
        subject_heights.append(max(y_values) - min(y_values))

      shoulder_gap = abs(landmarks["left_shoulder"]["x"] - landmarks["right_shoulder"]["x"])
      hip_gap = abs(landmarks["left_hip"]["x"] - landmarks["right_hip"]["x"])
      side_view_scores.append(clamp(1.0 - ((shoulder_gap + hip_gap) / 0.42), 0.0, 1.0))

    subject_height = sum(subject_heights) / max(len(subject_heights), 1)
    side_view_score = sum(side_view_scores) / max(len(side_view_scores), 1)
    quality_flags: list[str] = []

    if pose_coverage < 0.55:
      quality_flags.append("low_pose_coverage")
    if lower_body_visibility < 0.58:
      quality_flags.append("lower_body_occluded")
    if subject_height < 0.32:
      quality_flags.append("subject_too_small")
    if side_view_score < 0.42:
      quality_flags.append("camera_not_side_view")
    if tracking_confidence < 0.08 and min(
      average_visibility(frame, selected_side) for frame in frames
    ) < 0.55:
      quality_flags.append("ambiguous_tracking_side")

    component_scores = [
      clamp(pose_coverage, 0.0, 1.0),
      clamp(lower_body_visibility, 0.0, 1.0),
      clamp(subject_height / 0.55, 0.0, 1.0),
      clamp(side_view_score, 0.0, 1.0),
    ]
    quality_score = sum(component_scores) / len(component_scores)

    return {
      "quality_score": round(quality_score, 3),
      "pose_coverage": round(pose_coverage, 3),
      "lower_body_visibility": round(lower_body_visibility, 3),
      "subject_height": round(subject_height, 3),
      "side_view_score": round(side_view_score, 3),
      "selected_side": selected_side,
      "tracking_side_confidence": tracking_confidence,
      "quality_flags": quality_flags,
    }

  def analyze(
    self,
    *,
    video_id: str,
    exercise_type: str,
    view_type: str,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
  ) -> dict[str, Any]:
    diagnostics = self._build_quality_report(
      frames=frames,
      sampled_frame_count=sampled_frame_count,
    )
    selected_side = diagnostics["selected_side"] or "left"
    hip_depths = []
    knee_flexions = []
    hip_flexions = []

    for frame in frames:
      shoulder = blended_point(frame, "shoulder")
      hip = blended_point(frame, "hip")
      knee = blended_point(frame, "knee")
      ankle = blended_point(frame, "ankle")
      hip_depths.append(hip_depth_ratio(shoulder, hip, ankle))
      knee_flexions.append(knee_flexion_score(hip, knee, ankle))
      hip_flexions.append(hip_flexion_score(shoulder, hip, knee))

    reps, rep_detection = detect_reps(
      hip_depths=hip_depths,
      knee_flexions=knee_flexions,
      hip_flexions=hip_flexions,
      frames=frames,
    )
    diagnostics["rep_detection"] = rep_detection

    if rep_detection.get("reason") and rep_detection["reason"] not in diagnostics["quality_flags"]:
      diagnostics["quality_flags"].append(rep_detection["reason"])

    rep_summaries: list[dict[str, Any]] = []

    for rep_index, rep in enumerate(reps, start=1):
      start_frame = frames[rep["start_index"]]
      bottom_frame = frames[rep["bottom_index"]]
      duration_seconds = max(
        (rep["end_timestamp_ms"] - rep["start_timestamp_ms"]) / 1000,
        0.001,
      )
      velocity_stats = _calculate_velocity_stats(
        frames=frames,
        start_index=rep["start_index"],
        end_index=rep["end_index"],
      )

      start_shoulder = point_for_side(start_frame, selected_side, "shoulder")
      start_hip = point_for_side(start_frame, selected_side, "hip")
      bottom_shoulder = point_for_side(bottom_frame, selected_side, "shoulder")
      bottom_hip = point_for_side(bottom_frame, selected_side, "hip")
      bottom_knee = point_for_side(bottom_frame, selected_side, "knee")
      bottom_ankle = point_for_side(bottom_frame, selected_side, "ankle")

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
          "repIndex": rep_index,
          "startTime": rep["start_timestamp_ms"] / 1000,
          "endTime": rep["end_timestamp_ms"] / 1000,
          "duration": round(duration_seconds, 3),
          "repSpeed": round(1 / duration_seconds, 3),
          "avgVelocity": velocity_stats["avg_velocity"],
          "peakVelocity": velocity_stats["peak_velocity"],
          "depthScore": depth_score,
          "torsoAngleChangeDeg": torso_delta,
          "depth_score": depth_score,
          "torso_angle": round(bottom_torso, 2),
          "torso_angle_change": torso_delta,
          "estimated_body_velocity": velocity_stats,
          "flags": flags,
          "timestamps_ms": {
            "start": rep["start_timestamp_ms"],
            "bottom": rep["bottom_timestamp_ms"],
            "end": rep["end_timestamp_ms"],
          },
        }
      )

    summary_flags, coach_feedback = build_feedback(rep_summaries, diagnostics)

    return {
      "video_id": video_id,
      "exercise": exercise_type,
      "view": view_type,
      "analysis_limited": False,
      "rep_count": len(rep_summaries),
      "reps": rep_summaries,
      "summary_flags": summary_flags,
      "coach_feedback": coach_feedback,
      "diagnostics": diagnostics,
      "videoId": video_id,
      "cameraView": view_type,
      "duration": frames[-1]["timestamp_ms"] / 1000 if frames else 0,
      "poseFrames": _build_pose_frames(frames),
      "summaryFlags": summary_flags,
      "videoQuality": {
        "overallQuality": diagnostics.get("quality_score", 0),
        "poseCoverage": diagnostics.get("pose_coverage", 0),
        "lowerBodyVisibility": diagnostics.get("lower_body_visibility", 0),
        "sideViewConfidence": diagnostics.get("side_view_score", 0),
        "squatMotionSignal": diagnostics.get("rep_detection", {}).get("motion_amplitude", 0),
      },
      "coachingFeedback": coach_feedback,
    }
