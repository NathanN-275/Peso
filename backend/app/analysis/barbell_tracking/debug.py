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

  return debug
