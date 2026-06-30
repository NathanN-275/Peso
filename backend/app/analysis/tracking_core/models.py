from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

DetectionKind = Literal[
  "barbell_collar",
  "sleeve",
  "plate_face",
  "rack_upright",
  "j_hook",
  "storage_peg",
]

HardwareKind = Literal["rack_upright", "j_hook", "storage_peg"]
BODY_POINT_NAMES = ("upper_back", "hip", "knee", "ankle")
HARDWARE_KINDS: set[str] = {"rack_upright", "j_hook", "storage_peg"}


@dataclass(frozen=True)
class NormalizedPoint:
  x: float
  y: float

  def clamped(self) -> "NormalizedPoint":
    return NormalizedPoint(
      x=min(max(float(self.x), 0.0), 1.0),
      y=min(max(float(self.y), 0.0), 1.0),
    )

  def distance_to(self, other: "NormalizedPoint") -> float:
    return math.hypot(float(self.x) - float(other.x), float(self.y) - float(other.y))

  def to_public(self) -> dict[str, float]:
    point = self.clamped()
    return {"x": point.x, "y": point.y}


@dataclass(frozen=True)
class Detection:
  kind: DetectionKind
  confidence: float
  center: NormalizedPoint
  bbox: tuple[float, float, float, float] | None = None
  track_id: str | None = None

  @classmethod
  def from_pixel_box(
    cls,
    *,
    kind: DetectionKind,
    confidence: float,
    bbox: tuple[float, float, float, float],
    width: int | float,
    height: int | float,
    track_id: str | None = None,
  ) -> "Detection":
    x0, y0, x1, y1 = bbox
    width = max(float(width), 1.0)
    height = max(float(height), 1.0)
    center = NormalizedPoint(
      x=((float(x0) + float(x1)) / 2.0) / width,
      y=((float(y0) + float(y1)) / 2.0) / height,
    ).clamped()
    normalized_bbox = (
      min(max(float(x0) / width, 0.0), 1.0),
      min(max(float(y0) / height, 0.0), 1.0),
      min(max(float(x1) / width, 0.0), 1.0),
      min(max(float(y1) / height, 0.0), 1.0),
    )
    return cls(
      kind=kind,
      confidence=float(confidence),
      center=center,
      bbox=normalized_bbox,
      track_id=track_id,
    )

  def to_public(self) -> dict[str, object]:
    payload: dict[str, object] = {
      "kind": self.kind,
      "confidence": float(self.confidence),
      "center": self.center.to_public(),
    }
    if self.bbox is not None:
      payload["bbox"] = list(self.bbox)
    if self.track_id:
      payload["trackId"] = self.track_id
    return payload


@dataclass(frozen=True)
class DetectionFrame:
  source_frame_index: int
  time: float
  detections: tuple[Detection, ...]


@dataclass(frozen=True)
class TrackingPrior:
  name: str
  center: NormalizedPoint
  confidence: float
  source: str = "pin"
  stale: bool = False


@dataclass(frozen=True)
class ResolvedBodyPoint:
  name: str
  point: NormalizedPoint
  confidence: float
  source: str
  accepted_source: str
  chain_valid: bool
  visual_only: bool
  rejection_reason: str | None = None
  track_id: str | None = None

  def to_keypoint(self, *, side: str) -> dict[str, object]:
    return {
      "name": f"{side}_{self.name}",
      **self.point.to_public(),
      "confidence": float(self.confidence),
      "source": self.source,
      "acceptedSource": self.accepted_source,
      "chainValid": self.chain_valid,
      "visualOnly": self.visual_only,
      **({"rejectionReason": self.rejection_reason} if self.rejection_reason else {}),
      **({"trackId": self.track_id} if self.track_id else {}),
    }
