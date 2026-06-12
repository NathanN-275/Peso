from __future__ import annotations

import math

from .candidate import Candidate


def _shoulder_relative_offset(
  candidate: Candidate,
  shoulder: tuple[float, float] | None,
) -> tuple[float, float] | None:
  if not shoulder:
    return None

  return candidate.x - shoulder[0], candidate.y - shoulder[1]


def _score_plate_candidate(
  candidate: Candidate,
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> float:
  score = candidate.confidence
  bootstrapping = previous is None
  min_dimension = max(min(width, height), 1)
  radius_ratio = candidate.radius / min_dimension
  score += min(radius_ratio / 0.18, 1.0) * (1.1 if bootstrapping else 0.52)
  if radius_ratio < 0.08:
    score -= (1.0 - (radius_ratio / 0.08)) * 0.55

  if shoulder:
    horizontal_offset = candidate.x - shoulder[0]
    horizontal_distance_ratio = abs(horizontal_offset) / max(width, 1.0)
    horizontal_band_score = max(0.0, 1.0 - abs(horizontal_distance_ratio - 0.06) / 0.22)
    score += horizontal_band_score * (0.42 if bootstrapping else 0.2)
    if horizontal_distance_ratio > 0.44:
      score -= min((horizontal_distance_ratio - 0.44) / 0.08, 1.0) * 0.8

    shoulder_distance = math.hypot(candidate.x - shoulder[0], candidate.y - shoulder[1])
    score += max(0.0, 0.38 * (1.0 - shoulder_distance / (max(width, height) * 0.42)))
    vertical_offset = (shoulder[1] - candidate.y) / height
    ideal_offset = 0.11
    tolerance = 0.13
    band_score = max(0.0, 1.0 - (abs(vertical_offset - ideal_offset) / tolerance))
    score += band_score * (1.0 if bootstrapping else 0.5)

    if vertical_offset > 0.18:
      score -= min((vertical_offset - 0.18) / 0.08, 1.0) * (1.15 if bootstrapping else 0.72)
    if vertical_offset < -0.12:
      score -= min(abs(vertical_offset + 0.12) / 0.08, 1.0) * (0.8 if bootstrapping else 0.4)

  if previous:
    previous_distance = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    score += max(0.0, 0.18 * (1.0 - previous_distance / (max(width, height) * 0.24)))
    score += _score_plate_relative_to_shoulder(candidate, previous=previous, shoulder=shoulder, width=width, height=height)
    previous_radius = previous.get("radius")
    if previous_radius:
      radius_delta = abs(candidate.radius - previous_radius) / max(previous_radius, 1.0)
      score += max(0.0, 0.34 * (1.0 - radius_delta / 0.24))

  return score


def _score_plate_relative_to_shoulder(
  candidate: Candidate,
  *,
  previous: dict[str, float],
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> float:
  offset = _shoulder_relative_offset(candidate, shoulder)
  if not offset or "dx" not in previous or "dy" not in previous:
    return 0.0

  relative_jump = math.hypot(offset[0] - previous["dx"], offset[1] - previous["dy"])
  score = max(0.0, 0.82 * (1.0 - relative_jump / (max(width, height) * 0.08)))

  previous_shoulder_x = previous.get("shoulder_x")
  previous_shoulder_y = previous.get("shoulder_y")
  if previous_shoulder_x is not None and previous_shoulder_y is not None:
    shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y) if shoulder else 0.0
    pose_relative_motion = _pose_relative_displacement(candidate, previous=previous, shoulder=shoulder)
    if pose_relative_motion is not None and shoulder_motion >= 3.0 and pose_relative_motion > max(2.5, shoulder_motion * 0.45):
      score -= 0.95

  return score


def _pose_relative_displacement(
  candidate: Candidate,
  *,
  previous: dict[str, float],
  shoulder: tuple[float, float] | None,
) -> float | None:
  previous_shoulder_x = previous.get("shoulder_x")
  previous_shoulder_y = previous.get("shoulder_y")
  if previous_shoulder_x is None or previous_shoulder_y is None or shoulder is None:
    return None

  candidate_dx = candidate.x - previous["x"]
  candidate_dy = candidate.y - previous["y"]
  shoulder_dx = shoulder[0] - previous_shoulder_x
  shoulder_dy = shoulder[1] - previous_shoulder_y
  return math.hypot(candidate_dx - shoulder_dx, candidate_dy - shoulder_dy)


def _select_candidate(
  candidates: list[Candidate],
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> Candidate:
  if previous is None and shoulder:
    preferred = [
      candidate
      for candidate in candidates
      if shoulder[1] - (height * 0.18) <= candidate.y <= shoulder[1] + (height * 0.13)
    ]
    if preferred:
      candidates = preferred
    plate_sized = [candidate for candidate in candidates if candidate.radius >= max(min(width, height) * 0.07, 1.0)]
    if plate_sized:
      candidates = plate_sized

  return max(
    candidates,
    key=lambda candidate: _score_plate_candidate(
      candidate,
      previous=previous,
      shoulder=shoulder,
      width=width,
      height=height,
    ),
  )


def _plate_rejection_reason(
  candidate: Candidate,
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
  bootstrapping: bool,
) -> str | None:
  max_bootstrap_radius_ratio = 0.29 if width <= 300 and height > width else 0.23
  if bootstrapping and candidate.radius > min(width, height) * max_bootstrap_radius_ratio:
    return "generic_circle_too_large"

  if shoulder:
    offset = _shoulder_relative_offset(candidate, shoulder)
    if offset:
      if abs(offset[0]) > width * 0.46:
        return "outside_plate_zone"
      if offset[1] < -height * 0.19:
        return "too_high_above_shoulder"
      if offset[1] > height * 0.16:
        return "outside_plate_zone"

    vertical_offset = (shoulder[1] - candidate.y) / height
    if vertical_offset > 0.19:
      return "too_high_above_shoulder"

  if previous:
    jump_distance = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    if jump_distance > max(width, height) * 0.24:
      return "absolute_jump"

    previous_radius = previous.get("radius")
    if previous_radius and abs(candidate.radius - previous_radius) / max(previous_radius, 1.0) > 0.38:
      return "outside_plate_zone"

    offset = _shoulder_relative_offset(candidate, shoulder)
    if offset and "dx" in previous and "dy" in previous:
      relative_jump = math.hypot(offset[0] - previous["dx"], offset[1] - previous["dy"])
      if not bootstrapping and relative_jump > max(width, height) * 0.08:
        return "relative_offset_jump"

      previous_shoulder_x = previous.get("shoulder_x")
      previous_shoulder_y = previous.get("shoulder_y")
      if not bootstrapping and previous_shoulder_x is not None and previous_shoulder_y is not None and shoulder:
        shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y)
        pose_relative_motion = _pose_relative_displacement(candidate, previous=previous, shoulder=shoulder)
        if pose_relative_motion is not None and shoulder_motion >= 3.0 and pose_relative_motion > max(2.5, shoulder_motion * 0.45):
          return "stationary_hardware_like"

  return None


def _plate_match_is_consistent(
  candidate: Candidate,
  previous: dict[str, float],
  *,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> bool:
  rejection_reason = _plate_rejection_reason(
    candidate,
    previous=previous,
    shoulder=shoulder,
    width=width,
    height=height,
    bootstrapping=True,
  )
  if rejection_reason:
    return False

  previous_radius = max(previous.get("radius", candidate.radius), 1.0)
  if abs(candidate.radius - previous_radius) / previous_radius > 0.38:
    return False

  if abs(candidate.x - previous["x"]) > width * 0.2:
    return False

  return True


def _best_initial_plate(
  candidates: list[Candidate],
  *,
  pending_plate: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> Candidate | None:
  rejected_reasons = [
    _plate_rejection_reason(
      candidate,
      previous=pending_plate,
      shoulder=shoulder,
      width=width,
      height=height,
      bootstrapping=True,
    )
    for candidate in candidates
  ]
  plausible = [candidate for candidate, reason in zip(candidates, rejected_reasons) if not reason]
  if not plausible:
    return None

  return _select_candidate(plausible, previous=pending_plate, shoulder=shoulder, width=width, height=height)
