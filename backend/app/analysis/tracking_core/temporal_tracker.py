from __future__ import annotations

from dataclasses import dataclass, field

from .config import TrackingCoreConfig
from .models import Detection, DetectionFrame, HARDWARE_KINDS, NormalizedPoint, TrackingPrior


@dataclass
class TrackPoint:
  time: float
  point: NormalizedPoint
  confidence: float
  tracking_state: str
  identity_state: str
  source: str
  track_id: str = "barbell-collar-0"
  object_class: str = "barbell_collar"
  coasting: bool = False
  hardware_rejected: bool = False
  gap_reason: str | None = None
  rejection_reason: str | None = None

  def to_public(self) -> dict[str, object]:
    return {
      "time": float(self.time),
      **self.point.to_public(),
      "markerX": self.point.clamped().x,
      "markerY": self.point.clamped().y,
      "confidence": float(self.confidence),
      "trackingState": self.tracking_state,
      "selectedSource": self.source,
      "trackId": self.track_id,
      "identityState": self.identity_state,
      "objectClass": self.object_class,
      "coastingFrame": self.coasting,
      "hardwareRejected": self.hardware_rejected,
      **({"gapReason": self.gap_reason} if self.gap_reason else {}),
      **({"rejectionReason": self.rejection_reason} if self.rejection_reason else {}),
    }


@dataclass
class BarbellTrackerDiagnostics:
  source_counts: dict[str, int] = field(default_factory=dict)
  hardware_rejection_count: int = 0
  identity_gap_count: int = 0
  coasting_count: int = 0
  reacquire_count: int = 0
  initial_lock_count: int = 0
  frames: list[dict[str, object]] = field(default_factory=list)

  def note_source(self, source: str) -> None:
    self.source_counts[source] = self.source_counts.get(source, 0) + 1


class BarbellIdentityTracker:
  def __init__(self, config: TrackingCoreConfig | None = None) -> None:
    self.config = config or TrackingCoreConfig(core="apache_v1")
    self.diagnostics = BarbellTrackerDiagnostics()
    self._locked = False
    self._pending_lock_streak = 0
    self._reacquire_streak = 0
    self._miss_count = 0
    self._last_point: TrackPoint | None = None
    self._previous_point: TrackPoint | None = None

  def track(
    self,
    frames: list[DetectionFrame],
    *,
    priors_by_frame: dict[int, TrackingPrior] | None = None,
  ) -> tuple[list[TrackPoint], dict[str, object]]:
    output: list[TrackPoint] = []
    priors_by_frame = priors_by_frame or {}
    for frame in sorted(frames, key=lambda item: item.time):
      track_point = self.update(frame, prior=priors_by_frame.get(frame.source_frame_index))
      if track_point is not None:
        output.append(track_point)
    return output, self.to_diagnostics()

  def update(self, frame: DetectionFrame, *, prior: TrackingPrior | None = None) -> TrackPoint | None:
    candidate = self._select_collar(frame.detections)
    hardware = self._select_hardware(frame.detections)
    reason: str | None = None
    if hardware is not None and (candidate is None or hardware.confidence >= candidate.confidence):
      self.diagnostics.hardware_rejection_count += 1
      reason = f"hardware_{hardware.kind}_rejected"
      candidate = None

    if candidate is not None and candidate.confidence < self.config.min_collar_confidence:
      reason = "low_collar_confidence"
      candidate = None

    if candidate is not None and not self._candidate_near_expected(candidate, time_seconds=frame.time, prior=prior):
      reason = "outside_predicted_collar_lane"
      candidate = None

    if candidate is not None:
      return self._accept_candidate(frame, candidate, prior=prior)

    return self._handle_missing(frame, reason=reason or "missing_collar_detection")

  def _accept_candidate(
    self,
    frame: DetectionFrame,
    candidate: Detection,
    *,
    prior: TrackingPrior | None,
  ) -> TrackPoint | None:
    confidence = float(candidate.confidence)
    source = "detector_tracklet"
    if prior and not prior.stale:
      distance = candidate.center.distance_to(prior.center)
      if distance <= self.config.max_lane_distance:
        confidence = min(max(confidence, float(prior.confidence)), 0.98)
        source = "detector_pin_prior"

    if not self._locked:
      self._pending_lock_streak += 1
      threshold = self.config.initial_lock_frames if self._last_point is None else self.config.reacquire_frames
      if self._pending_lock_streak < threshold:
        self._record_frame(frame, source="pending_lock", reason="awaiting_tracklet_confirmation")
        self.diagnostics.note_source("pending_lock")
        return None
      self._locked = True
      self._miss_count = 0
      self._reacquire_streak += 1
      self.diagnostics.initial_lock_count += 1 if self._last_point is None else 0
      self.diagnostics.reacquire_count += 1 if self._last_point is not None else 0

    point = TrackPoint(
      time=frame.time,
      point=candidate.center,
      confidence=confidence,
      tracking_state="guided",
      identity_state="locked",
      source=source,
      object_class=candidate.kind,
      track_id=candidate.track_id or "barbell-collar-0",
    )
    self._advance(point)
    self._pending_lock_streak = 0
    self._miss_count = 0
    self.diagnostics.note_source(source)
    self._record_frame(frame, source=source, emitted=point)
    return point

  def _handle_missing(self, frame: DetectionFrame, *, reason: str) -> TrackPoint | None:
    self._pending_lock_streak = 0
    if not self._locked or self._last_point is None:
      self.diagnostics.identity_gap_count += 1
      self.diagnostics.note_source("gap")
      self._record_frame(frame, source="gap", reason=reason)
      return None

    self._miss_count += 1
    if self._miss_count <= self.config.max_coast_frames:
      predicted = self._predict(frame.time)
      point = TrackPoint(
        time=frame.time,
        point=predicted,
        confidence=min(float(self._last_point.confidence) * 0.65, 0.42),
        tracking_state="estimated",
        identity_state="coasting",
        source="coast",
        coasting=True,
        gap_reason=reason,
      )
      self._advance(point)
      self.diagnostics.coasting_count += 1
      self.diagnostics.note_source("coast")
      self._record_frame(frame, source="coast", reason=reason, emitted=point)
      return point

    self._locked = False
    self._reacquire_streak = 0
    self.diagnostics.identity_gap_count += 1
    self.diagnostics.note_source("gap")
    self._record_frame(frame, source="gap", reason=reason)
    return None

  def _select_collar(self, detections: tuple[Detection, ...]) -> Detection | None:
    candidates = [detection for detection in detections if detection.kind == "barbell_collar"]
    return max(candidates, key=lambda item: item.confidence, default=None)

  def _select_hardware(self, detections: tuple[Detection, ...]) -> Detection | None:
    candidates = [detection for detection in detections if detection.kind in HARDWARE_KINDS]
    return max(candidates, key=lambda item: item.confidence, default=None)

  def _candidate_near_expected(
    self,
    candidate: Detection,
    *,
    time_seconds: float,
    prior: TrackingPrior | None,
  ) -> bool:
    if prior and not prior.stale and candidate.center.distance_to(prior.center) <= self.config.max_lane_distance * 1.4:
      return True
    if self._last_point is None:
      return True
    expected = self._predict(time_seconds)
    return candidate.center.distance_to(expected) <= self.config.max_lane_distance

  def _predict(self, time_seconds: float) -> NormalizedPoint:
    if self._last_point is None:
      return NormalizedPoint(0.0, 0.0)
    if self._previous_point is None or self._last_point.time <= self._previous_point.time:
      return self._last_point.point
    dt = self._last_point.time - self._previous_point.time
    horizon = max(0.0, time_seconds - self._last_point.time)
    scale = min(horizon / dt, 2.0)
    return NormalizedPoint(
      x=self._last_point.point.x + ((self._last_point.point.x - self._previous_point.point.x) * scale),
      y=self._last_point.point.y + ((self._last_point.point.y - self._previous_point.point.y) * scale),
    ).clamped()

  def _advance(self, point: TrackPoint) -> None:
    self._previous_point = self._last_point
    self._last_point = point

  def _record_frame(
    self,
    frame: DetectionFrame,
    *,
    source: str,
    reason: str | None = None,
    emitted: TrackPoint | None = None,
  ) -> None:
    if len(self.diagnostics.frames) >= 200:
      return
    self.diagnostics.frames.append({
      "time": round(float(frame.time), 4),
      "source_frame_index": frame.source_frame_index,
      "source": source,
      "reason": reason,
      "detection_count": len(frame.detections),
      "emitted": emitted.to_public() if emitted else None,
    })

  def to_diagnostics(self) -> dict[str, object]:
    return {
      "source_counts": dict(self.diagnostics.source_counts),
      "hardware_rejection_count": self.diagnostics.hardware_rejection_count,
      "identity_gap_count": self.diagnostics.identity_gap_count,
      "coasting_count": self.diagnostics.coasting_count,
      "reacquire_count": self.diagnostics.reacquire_count,
      "initial_lock_count": self.diagnostics.initial_lock_count,
      "frames": list(self.diagnostics.frames),
    }
