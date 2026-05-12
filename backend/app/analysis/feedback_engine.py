from __future__ import annotations

from collections import Counter
from statistics import pstdev
from typing import Any


def build_feedback(reps: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
  if not reps:
    return (
      ["No clear squat reps detected"],
      ["Use a clearer side-view squat video with your full body in frame."],
    )

  summary_flags: list[str] = []
  coach_feedback: list[str] = []

  depth_scores = [rep["depth_score"] for rep in reps]
  torso_changes = [rep["torso_angle_change"] for rep in reps]
  flag_counter = Counter(flag for rep in reps for flag in rep["flags"])

  if any(score < 0.6 for score in depth_scores):
    summary_flags.append("Insufficient depth")
    coach_feedback.append("Sit deeper into the squat and keep the hip crease at or below knee level.")

  if flag_counter.get("forward_lean", 0) > 0:
    summary_flags.append("Forward lean")
    coach_feedback.append("Keep your chest taller and brace harder to reduce forward torso collapse.")

  if len(depth_scores) > 1 and pstdev(depth_scores) > 0.12:
    summary_flags.append("Inconsistent depth")
    coach_feedback.append("Aim to hit the same depth on each rep.")

  if len(torso_changes) > 1 and pstdev(torso_changes) > 6:
    summary_flags.append("Inconsistent torso position")
    coach_feedback.append("Keep the bar path and torso angle more consistent rep to rep.")

  if not summary_flags:
    coach_feedback.append("Reps looked consistent. Keep the same depth and torso control.")

  return summary_flags, coach_feedback
