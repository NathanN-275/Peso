from __future__ import annotations

from .models import BODY_POINT_NAMES, NormalizedPoint, ResolvedBodyPoint, TrackingPrior


class SquatExerciseResolver:
  def __init__(self, *, min_visibility: float = 0.25) -> None:
    self.min_visibility = min_visibility

  def resolve_frame(
    self,
    landmarks: dict[str, dict[str, float]],
    *,
    selected_side: str,
    priors: dict[str, TrackingPrior] | None = None,
  ) -> list[ResolvedBodyPoint]:
    priors = priors or {}
    resolved: list[ResolvedBodyPoint] = []
    for name in BODY_POINT_NAMES:
      landmark_name = f"{selected_side}_{'shoulder' if name == 'upper_back' else name}"
      landmark = landmarks.get(landmark_name) or {}
      visibility = float(landmark.get("visibility") or 0.0)
      if visibility >= self.min_visibility:
        point = NormalizedPoint(float(landmark.get("x", 0.0)), float(landmark.get("y", 0.0))).clamped()
        prior = priors.get(name)
        source = "pose"
        confidence = visibility
        if prior and not prior.stale and point.distance_to(prior.center) <= 0.08:
          source = "pose_pin_prior"
          confidence = max(confidence, min(float(prior.confidence), 0.95))
        resolved.append(
          ResolvedBodyPoint(
            name=name,
            point=point,
            confidence=confidence,
            source=source,
            accepted_source="automatic" if source == "pose" else "automatic_pin_prior",
            chain_valid=True,
            visual_only=False,
          )
        )
        continue

      prior = priors.get(name)
      fallback_point = prior.center if prior else NormalizedPoint(0.0, 0.0)
      resolved.append(
        ResolvedBodyPoint(
          name=name,
          point=fallback_point,
          confidence=min(float(prior.confidence), 0.24) if prior else 0.0,
          source="pin_visual_fallback" if prior else "gap",
          accepted_source="gap",
          chain_valid=False,
          visual_only=True,
          rejection_reason="low_pose_confidence",
        )
      )
    return resolved
