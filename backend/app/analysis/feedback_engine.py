from __future__ import annotations

from collections import Counter
from statistics import pstdev
from typing import Any


QUALITY_FLAG_LABELS = {
  "low_pose_coverage": "Pose tracking was inconsistent",
  "lower_body_occluded": "Lower body was hard to track",
  "subject_too_small": "Athlete was too small in frame",
  "camera_not_side_view": "Camera angle was not clearly side view",
  "excessive_landmark_jitter": "Pose tracking was jittery",
  "unreliable_pose_landmarks": "Some squat landmarks were unreliable",
  "plate_rack_occlusion_suspected": "Rack or plates may have blocked key landmarks",
  "ambiguous_tracking_side": "Tracking side was ambiguous",
  "low_squat_motion": "Squat motion was too small to measure",
  "no_complete_rep_cycle": "No complete squat cycle detected",
}


QUALITY_FLAG_FEEDBACK = {
  "low_pose_coverage": "Record with steadier lighting and keep your full body visible for the entire set.",
  "lower_body_occluded": "Keep hips, knees, ankles, and feet visible so the app can follow squat depth.",
  "subject_too_small": "Move the camera closer or crop less so your body fills more of the frame.",
  "camera_not_side_view": "Place the camera squarely to your side for this version of squat analysis.",
  "excessive_landmark_jitter": "Use steadier lighting and keep the camera still so joint tracking is less noisy.",
  "unreliable_pose_landmarks": "Keep the bar, rack, and plates from blocking your hips and shoulders when possible.",
  "plate_rack_occlusion_suspected": "The rack or plates may be covering the hip or shoulder; use the clearest side angle you can while keeping the lift safe.",
  "ambiguous_tracking_side": "Use a cleaner side angle with less overlap from the rack or other people.",
  "low_squat_motion": "Use a clip with a full descent and return to standing.",
  "no_complete_rep_cycle": "Include the start, bottom, and return-to-standing portions of each rep.",
}


def build_feedback(
  reps: list[dict[str, Any]],
  diagnostics: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
  # Convert rep metrics and quality flags into coaching text.
  quality_flags = (diagnostics or {}).get("quality_flags", [])

  if not reps:
    summary_flags = ["No clear squat reps detected"]
    coach_feedback: list[str] = []

    for flag in quality_flags:
      label = QUALITY_FLAG_LABELS.get(flag)
      feedback = QUALITY_FLAG_FEEDBACK.get(flag)

      if label and label not in summary_flags:
        summary_flags.append(label)
      if feedback and feedback not in coach_feedback:
        coach_feedback.append(feedback)

    if not coach_feedback:
      coach_feedback.append("Use a clearer side-view squat video with your full body in frame.")

    return (
      summary_flags,
      coach_feedback,
    )

  summary_flags: list[str] = []
  coach_feedback: list[str] = []

  depth_scores = [rep["depth_score"] for rep in reps]
  torso_changes = [rep["torso_angle_change"] for rep in reps]
  flag_counter = Counter(flag for rep in reps for flag in rep["flags"])
  depth_statuses = [rep.get("depth_status") or rep.get("depthStatus") for rep in reps]

  if flag_counter.get("insufficient_depth", 0) > 0 or "insufficient_depth" in depth_statuses:
    summary_flags.append("Insufficient depth")
    coach_feedback.append("Sit deeper into the squat and keep the hip crease at or below knee level.")

  if flag_counter.get("forward_lean", 0) > 0:
    summary_flags.append("Forward lean")
    coach_feedback.append("Keep your chest taller and brace harder to reduce forward torso collapse.")

  if flag_counter.get("low_depth_confidence", 0) > 0:
    summary_flags.append("Depth confidence was limited")
    coach_feedback.append("Keep hips, knees, and ankles clearly visible at the bottom of each rep.")

  if len(depth_scores) > 1 and pstdev(depth_scores) > 0.12:
    summary_flags.append("Inconsistent depth")
    coach_feedback.append("Aim to hit the same depth on each rep.")

  if len(torso_changes) > 1 and pstdev(torso_changes) > 6:
    summary_flags.append("Inconsistent torso position")
    coach_feedback.append("Keep the bar path and torso angle more consistent rep to rep.")

  quality_warning_flags = [
    flag for flag in quality_flags
    if flag in {
      "low_pose_coverage",
      "lower_body_occluded",
      "subject_too_small",
      "camera_not_side_view",
      "excessive_landmark_jitter",
      "unreliable_pose_landmarks",
      "plate_rack_occlusion_suspected",
      "ambiguous_tracking_side",
    }
  ]

  if quality_warning_flags:
    summary_flags.append("Video quality limited confidence")
    feedback = QUALITY_FLAG_FEEDBACK.get(quality_warning_flags[0])
    if feedback:
      coach_feedback.append(feedback)

  if not summary_flags:
    coach_feedback.append("Reps looked consistent. Keep the same depth and torso control.")

  return summary_flags, coach_feedback
