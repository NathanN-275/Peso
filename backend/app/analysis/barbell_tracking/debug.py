from __future__ import annotations

from typing import Any

from .candidate import Candidate


def _draw_debug_frame(
  cv2: Any,
  frame: Any,
  *,
  bounds: tuple[float, float, float, float],
  candidates: list[Candidate],
  rejected: list[Candidate],
  selected_plate: Candidate | None,
  predicted_collar: tuple[float, float] | None,
  refined_collar: tuple[float, float] | None,
  hub_candidates: list[dict[str, Any]] | None = None,
  rejected_hub_candidates: list[dict[str, Any]] | None = None,
  final_bar_point: tuple[float, float] | None = None,
  pose_predicted_point: tuple[float, float] | None = None,
  emitted_point: tuple[float, float] | None = None,
  rejection_reason: str | None = None,
  mode: str | None = None,
) -> Any:
  debug = frame.copy()
  min_x, min_y, max_x, max_y = bounds
  cv2.rectangle(debug, (int(min_x), int(min_y)), (int(max_x), int(max_y)), (255, 180, 0), 2)
  rejected_ids = {id(candidate) for candidate in rejected}

  for candidate in candidates:
    color = (0, 0, 255) if id(candidate) in rejected_ids else (0, 255, 255)
    cv2.circle(debug, (int(candidate.x), int(candidate.y)), max(int(candidate.radius), 3), color, 2)

  if selected_plate:
    cv2.circle(debug, (int(selected_plate.x), int(selected_plate.y)), max(int(selected_plate.radius), 4), (0, 255, 0), 3)
    cv2.circle(debug, (int(selected_plate.x), int(selected_plate.y)), 3, (0, 255, 0), -1)

  for hub_candidate in hub_candidates or []:
    point = hub_candidate.get("point")
    if not point:
      continue
    cv2.circle(
      debug,
      (int(point[0]), int(point[1])),
      max(int(round(float(hub_candidate.get("radius") or 4))), 4),
      (255, 255, 255),
      1,
    )

  for hub_candidate in rejected_hub_candidates or []:
    point = hub_candidate.get("point")
    if not point:
      continue
    cv2.circle(
      debug,
      (int(point[0]), int(point[1])),
      max(int(round(float(hub_candidate.get("radius") or 4))), 4),
      (0, 120, 255),
      1,
    )
    reason = hub_candidate.get("reason")
    if reason:
      cv2.putText(
        debug,
        str(reason),
        (int(point[0]) + 5, int(point[1]) - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (0, 120, 255),
        1,
      )

  if final_bar_point:
    cv2.drawMarker(
      debug,
      (int(final_bar_point[0]), int(final_bar_point[1])),
      (255, 255, 255),
      markerType=cv2.MARKER_DIAMOND,
      markerSize=14,
      thickness=2,
    )

  if pose_predicted_point:
    cv2.drawMarker(
      debug,
      (int(pose_predicted_point[0]), int(pose_predicted_point[1])),
      (255, 220, 90),
      markerType=cv2.MARKER_CROSS,
      markerSize=16,
      thickness=2,
    )

  if emitted_point:
    cv2.drawMarker(
      debug,
      (int(emitted_point[0]), int(emitted_point[1])),
      (80, 255, 80),
      markerType=cv2.MARKER_STAR,
      markerSize=14,
      thickness=2,
    )

  if predicted_collar:
    cv2.drawMarker(
      debug,
      (int(predicted_collar[0]), int(predicted_collar[1])),
      (255, 0, 255),
      markerType=cv2.MARKER_CROSS,
      markerSize=12,
      thickness=2,
    )

  if refined_collar:
    cv2.drawMarker(
      debug,
      (int(refined_collar[0]), int(refined_collar[1])),
      (40, 235, 52),
      markerType=cv2.MARKER_TILTED_CROSS,
      markerSize=12,
      thickness=2,
    )

  if mode:
    cv2.putText(debug, mode, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 235, 52), 2)
  if rejection_reason:
    cv2.putText(debug, rejection_reason, (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 120, 255), 2)

  return debug
