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
  candidate_count: int = 0
  rejected_candidate_count: int = 0
  ambiguous_candidate_frame_count: int = 0
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
    self._coast_started_at: float | None = None
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
    if prior and not prior.stale and prior.source in {"reference", "reference_pin"}:
      return self._accept_candidate(
        frame,
        Detection(
          kind="barbell_collar",
          confidence=max(float(prior.confidence), 0.99),
          center=prior.center,
          track_id="barbell-collar-0",
        ),
        prior=prior,
        selection={"candidate_count": 0, "distance_source": "exact_reference_pin"},
      )
    candidate, reason, selection = self._select_collar_candidate(
      frame.detections,
      time_seconds=frame.time,
      prior=prior,
    )

    if candidate is not None:
      return self._accept_candidate(frame, candidate, prior=prior, selection=selection)

    return self._handle_missing(
      frame,
      reason=reason or "missing_collar_detection",
      selection=selection,
    )

  def _accept_candidate(
    self,
    frame: DetectionFrame,
    candidate: Detection,
    *,
    prior: TrackingPrior | None,
    selection: dict[str, object] | None = None,
  ) -> TrackPoint | None:
    confidence = float(candidate.confidence)
    source = "detector_tracklet"
    reference_prior = bool(
      prior and not prior.stale and prior.source in {"reference", "reference_pin"}
    )
    if prior and not prior.stale:
      distance = candidate.center.distance_to(prior.center)
      if distance <= self.config.max_lane_distance:
        confidence = min(max(confidence, float(prior.confidence)), 0.98)
        source = "detector_pin_prior"
    if reference_prior:
      source = "reference_pin"

    if reference_prior:
      self._locked = True
      self._pending_lock_streak = 0
      self._miss_count = 0
      self._coast_started_at = None
    elif not self._locked:
      self._pending_lock_streak += 1
      threshold = self.config.initial_lock_frames if self._last_point is None else self.config.reacquire_frames
      if self._pending_lock_streak < threshold:
        self._record_frame(
          frame,
          source="pending_lock",
          reason="awaiting_tracklet_confirmation",
          selection=selection,
        )
        self.diagnostics.note_source("pending_lock")
        return None
      self._locked = True
      self._miss_count = 0
      self._coast_started_at = None
      self._reacquire_streak += 1
      self.diagnostics.initial_lock_count += 1 if self._last_point is None else 0
      self.diagnostics.reacquire_count += 1 if self._last_point is not None else 0

    point = TrackPoint(
      time=frame.time,
      point=prior.center if reference_prior and prior is not None else candidate.center,
      confidence=confidence,
      tracking_state="reference" if reference_prior else "guided",
      identity_state="locked",
      source=source,
      object_class=candidate.kind,
      track_id=candidate.track_id or "barbell-collar-0",
    )
    self._advance(point)
    self._pending_lock_streak = 0
    self._miss_count = 0
    self._coast_started_at = None
    self.diagnostics.note_source(source)
    self._record_frame(frame, source=source, emitted=point, selection=selection)
    return point

  def _handle_missing(
    self,
    frame: DetectionFrame,
    *,
    reason: str,
    selection: dict[str, object] | None = None,
  ) -> TrackPoint | None:
    self._pending_lock_streak = 0
    if not self._locked or self._last_point is None:
      self.diagnostics.identity_gap_count += 1
      self.diagnostics.note_source("gap")
      self._record_frame(frame, source="gap", reason=reason, selection=selection)
      return None

    self._miss_count += 1
    if self._coast_started_at is None:
      self._coast_started_at = frame.time
    elapsed = max(0.0, frame.time - self._coast_started_at)
    if self._miss_count <= self.config.max_coast_frames and elapsed <= self.config.max_coast_seconds:
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
      self._record_frame(frame, source="coast", reason=reason, emitted=point, selection=selection)
      return point

    self._locked = False
    self._reacquire_streak = 0
    self._coast_started_at = None
    self.diagnostics.identity_gap_count += 1
    self.diagnostics.note_source("gap")
    self._record_frame(frame, source="gap", reason=reason, selection=selection)
    return None

  def _select_collar_candidate(
    self,
    detections: tuple[Detection, ...],
    *,
    time_seconds: float,
    prior: TrackingPrior | None,
  ) -> tuple[Detection | None, str | None, dict[str, object]]:
    candidates = [detection for detection in detections if detection.kind == "barbell_collar"]
    hardware = [detection for detection in detections if detection.kind in HARDWARE_KINDS]
    self.diagnostics.candidate_count += len(candidates)
    if len(candidates) > 1:
      self.diagnostics.ambiguous_candidate_frame_count += 1

    evaluations: list[tuple[float, Detection, float | None, str]] = []
    rejected: list[dict[str, object]] = []
    for candidate in candidates:
      rejection_reason: str | None = None
      if candidate.confidence < self.config.min_collar_confidence:
        rejection_reason = "low_collar_confidence"
      conflicting_hardware = next(
        (item for item in hardware if self._hardware_conflicts_with_candidate(item, candidate)),
        None,
      )
      if conflicting_hardware is not None:
        rejection_reason = f"hardware_{conflicting_hardware.kind}_rejected"
      if rejection_reason is None and not self._candidate_near_expected(
        candidate,
        time_seconds=time_seconds,
        prior=prior,
      ):
        rejection_reason = "outside_predicted_collar_lane"
      if rejection_reason is not None:
        self.diagnostics.rejected_candidate_count += 1
        if rejection_reason.startswith("hardware_"):
          self.diagnostics.hardware_rejection_count += 1
        rejected.append({
          "confidence": round(float(candidate.confidence), 4),
          "reason": rejection_reason,
          "center": candidate.center.to_public(),
        })
        continue

      distance, distance_source = self._association_distance(
        candidate,
        time_seconds=time_seconds,
        prior=prior,
      )
      proximity_bonus = 0.0
      if distance is not None:
        proximity_bonus = max(0.0, 1.0 - (distance / max(self.config.max_lane_distance, 1e-6))) * 0.35
      score = float(candidate.confidence) + proximity_bonus
      evaluations.append((score, candidate, distance, distance_source))

    if not evaluations:
      if not candidates and hardware:
        self.diagnostics.hardware_rejection_count += 1
        reason = f"hardware_{max(hardware, key=lambda item: item.confidence).kind}_rejected"
      else:
        reason = str(rejected[0]["reason"]) if rejected else "missing_collar_detection"
      return None, reason, {
        "candidate_count": len(candidates),
        "rejected": rejected,
      }

    score, selected, distance, distance_source = max(
      evaluations,
      key=lambda value: (value[0], value[1].confidence),
    )
    return selected, None, {
      "candidate_count": len(candidates),
      "selected_score": round(score, 5),
      "selected_confidence": round(float(selected.confidence), 5),
      "selected_distance": round(distance, 5) if distance is not None else None,
      "distance_source": distance_source,
      "rejected": rejected,
    }

  def _association_distance(
    self,
    candidate: Detection,
    *,
    time_seconds: float,
    prior: TrackingPrior | None,
  ) -> tuple[float | None, str]:
    if prior and not prior.stale:
      return candidate.center.distance_to(prior.center), "pin_prior"
    if self._last_point is not None:
      return candidate.center.distance_to(self._predict(time_seconds)), "predicted_lane"
    return None, "initial_confidence"

  def _hardware_conflicts_with_candidate(self, hardware: Detection, candidate: Detection) -> bool:
    """Reject only collar candidates that overlap the detected hardware.

    A rack upright can be confidently visible for an entire clip. It is a negative
    class, not a reason to reject a collar on the opposite side of the frame.
    """
    if hardware.bbox and candidate.bbox:
      hx0, hy0, hx1, hy1 = hardware.bbox
      cx0, cy0, cx1, cy1 = candidate.bbox
      return max(hx0, cx0) <= min(hx1, cx1) and max(hy0, cy0) <= min(hy1, cy1)
    return hardware.center.distance_to(candidate.center) <= self.config.max_lane_distance

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
    selection: dict[str, object] | None = None,
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
      "selection": selection,
    })

  def to_diagnostics(self) -> dict[str, object]:
    return {
      "source_counts": dict(self.diagnostics.source_counts),
      "hardware_rejection_count": self.diagnostics.hardware_rejection_count,
      "identity_gap_count": self.diagnostics.identity_gap_count,
      "coasting_count": self.diagnostics.coasting_count,
      "reacquire_count": self.diagnostics.reacquire_count,
      "initial_lock_count": self.diagnostics.initial_lock_count,
      "candidate_count": self.diagnostics.candidate_count,
      "rejected_candidate_count": self.diagnostics.rejected_candidate_count,
      "ambiguous_candidate_frame_count": self.diagnostics.ambiguous_candidate_frame_count,
      "frames": list(self.diagnostics.frames),
    }
