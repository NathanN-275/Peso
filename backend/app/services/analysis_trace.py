from __future__ import annotations

import copy
import csv
import io
import json
import math
import threading
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

from .config import get_settings


TRACE_FORMAT_VERSION = 1
FEEDBACK_FORMAT_VERSION = 1
REVIEW_SNAPSHOT_NAMES = {"raw_pose", "pin_fusion", "pose_repair", "barbell_tracking", "exercise_metrics"}
REVIEW_LANDMARK_SUFFIXES = {
  "shoulder", "upper_back", "hip", "knee", "ankle", "elbow", "wrist",
}
EXPORT_REDACTED_KEYS = {
  "authorization",
  "access_token",
  "refresh_token",
  "token",
  "secret",
  "service_role",
  "service_role_key",
  "supabase_jwt_secret",
  "user_id",
  "video_id",
  "storage_path",
  "playback_path",
  "original_storage_path",
  "thumbnail_path",
  "video_url",
  "signed_url",
  "export_url",
}
EXPORT_REDACTED_COMPACT_KEYS = {
  "userid",
  "videoid",
  "storagepath",
  "playbackpath",
  "playbackurl",
  "originalstoragepath",
  "thumbnailpath",
  "videourl",
  "signedurl",
  "exporturl",
  "downloadurl",
}


def _utc_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
  """Convert analysis internals to the JSON-only trace format."""
  if value is None or isinstance(value, (str, bool, int)):
    return value
  if isinstance(value, float):
    return value if math.isfinite(value) else None
  if isinstance(value, Path):
    return str(value)
  if is_dataclass(value):
    return _json_safe(asdict(value))
  if isinstance(value, dict):
    return {str(key): _json_safe(item) for key, item in value.items()}
  if isinstance(value, (list, tuple, set)):
    return [_json_safe(item) for item in value]
  if hasattr(value, "__dict__"):
    return _json_safe(vars(value))
  return str(value)


def _redact_export(value: Any, key: str | None = None) -> Any:
  normalized_key = (key or "").lower()
  compact_key = "".join(character for character in normalized_key if character.isalnum())
  if (
    normalized_key in EXPORT_REDACTED_KEYS
    or compact_key in EXPORT_REDACTED_COMPACT_KEYS
    or compact_key.endswith("url")
    or any(
      sensitive in normalized_key
      for sensitive in ("token", "secret", "authorization", "service_role", "storage_path", "signed_url", "video_url")
    )
  ):
    return "[redacted]"
  if isinstance(value, dict):
    return {str(child_key): _redact_export(child_value, str(child_key)) for child_key, child_value in value.items()}
  if isinstance(value, list):
    return [_redact_export(item) for item in value]
  return value


class AnalysisTraceRun:
  def __init__(self, service: "AnalysisTraceService", run_id: str) -> None:
    self._service = service
    self.run_id = run_id

  def event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
    self._service.append_event(self.run_id, event_type, payload or {})

  def stage(self, name: str, duration_ms: int, **details: Any) -> None:
    self.event("stage_completed", {"name": name, "duration_ms": duration_ms, **details})

  def snapshot(self, name: str, **payload: Any) -> None:
    self.event("snapshot", {"name": name, **payload})

  def complete(self, result: dict[str, Any], stage_timings_ms: dict[str, int]) -> None:
    self._service.finalize(self.run_id, "completed", {
      "result": result,
      "stage_timings_ms": stage_timings_ms,
    })

  def fail(self, error: Exception, stage_timings_ms: dict[str, int]) -> None:
    self._service.finalize(self.run_id, "failed", {
      "error": {"type": type(error).__name__, "message": str(error)},
      "stage_timings_ms": stage_timings_ms,
    })


class AnalysisTraceService:
  """Development-only, local-disk analysis trace recorder and reader."""

  def __init__(self, *, enabled: bool, trace_dir: Path, max_runs: int) -> None:
    self.enabled = enabled
    self.trace_dir = trace_dir
    self.feedback_dir = trace_dir.parent / "analysis-feedback"
    self.max_runs = max_runs
    self._runs: dict[str, dict[str, Any]] = {}
    self._condition = threading.Condition(threading.RLock())

  def start(
    self,
    *,
    video_id: str,
    user_id: str,
    exercise_type: str,
    view_type: str,
    model_version: str,
  ) -> AnalysisTraceRun:
    run_id = str(uuid4())
    if not self.enabled:
      return AnalysisTraceRun(self, run_id)

    document = {
      "format_version": TRACE_FORMAT_VERSION,
      "run_id": run_id,
      "status": "running",
      "created_at": _utc_now(),
      "finished_at": None,
      "metadata": {
        "video_id": video_id,
        "user_id": user_id,
        "exercise_type": exercise_type,
        "view_type": view_type,
        "model_version": model_version,
      },
      "events": [],
    }
    with self._condition:
      self._runs[run_id] = document
      self._append_event_locked(document, "analysis_started", {"stage": "initializing"})
      self._persist_locked(document)
      self._condition.notify_all()
    return AnalysisTraceRun(self, run_id)

  def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    if not self.enabled:
      return
    with self._condition:
      document = self._runs.get(run_id)
      if not document or document.get("status") != "running":
        return
      self._append_event_locked(document, event_type, payload)
      self._persist_locked(document)
      self._condition.notify_all()

  def finalize(self, run_id: str, status: str, payload: dict[str, Any]) -> None:
    if not self.enabled:
      return
    with self._condition:
      document = self._runs.get(run_id)
      if not document or document.get("status") != "running":
        return
      self._append_event_locked(document, f"analysis_{status}", payload)
      document["status"] = status
      document["finished_at"] = _utc_now()
      self._persist_locked(document)
      self._prune_locked()
      self._condition.notify_all()

  def list_runs(self, user_id: str) -> list[dict[str, Any]]:
    if not self.enabled:
      return []
    with self._condition:
      documents = self._all_documents_locked()
      summaries = [self._summary(document) for document in documents if self._is_owned_by(document, user_id)]
    return sorted(summaries, key=lambda item: item["created_at"], reverse=True)

  def get_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
    if not self.enabled:
      return None
    with self._condition:
      document = self._document_locked(run_id)
      if document is None or not self._is_owned_by(document, user_id):
        return None
      stored = copy.deepcopy(document)
      return {**stored, **self._summary(stored)}

  def get_review(self, run_id: str, user_id: str) -> dict[str, Any] | None:
    """Return the small, dashboard-specific projection of one owned trace."""
    if not self.enabled:
      return None
    with self._condition:
      document = self._document_locked(run_id)
      if document is None or not self._is_owned_by(document, user_id):
        return None
      stored = copy.deepcopy(document)
    return self._review_projection(stored)

  def iter_events(
    self,
    run_id: str,
    user_id: str,
    *,
    after: int = 0,
  ) -> Generator[dict[str, Any], None, None]:
    next_index = max(after, 0)
    while True:
      with self._condition:
        document = self._document_locked(run_id)
        if document is None or not self._is_owned_by(document, user_id):
          return
        events = document.get("events") or []
        if next_index < len(events):
          pending = copy.deepcopy(events[next_index:])
          next_index = len(events)
        else:
          pending = []
          if document.get("status") != "running":
            return
          self._condition.wait(timeout=15)
      if pending:
        for event in pending:
          yield event
      else:
        yield {"type": "keepalive", "at": _utc_now(), "payload": {}}

  def build_export(self, run_id: str, user_id: str) -> bytes | None:
    document = self.get_run(run_id, user_id)
    if document is None:
      return None
    redacted = _redact_export(document)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      self._write_trace_export(archive, redacted)
    return stream.getvalue()

  def get_feedback(self, run_id: str, user_id: str) -> dict[str, Any] | None:
    """Return local review annotations for one owned trace, without local owner metadata."""
    if not self.enabled:
      return None
    with self._condition:
      trace = self._document_locked(run_id)
      if trace is None or not self._is_owned_by(trace, user_id):
        return None
      feedback = self._feedback_document_locked(run_id)
      if feedback is None or str(feedback.get("user_id") or "") != user_id:
        return {
          "format_version": FEEDBACK_FORMAT_VERSION,
          "run_id": run_id,
          "updated_at": None,
          "annotations": [],
        }
      return self._public_feedback(feedback)

  def save_feedback(
    self,
    run_id: str,
    user_id: str,
    annotations: list[dict[str, Any]],
  ) -> dict[str, Any] | None:
    """Atomically persist validated dashboard annotations beside local traces."""
    if not self.enabled:
      return None
    with self._condition:
      trace = self._document_locked(run_id)
      if trace is None or not self._is_owned_by(trace, user_id):
        return None
      document = {
        "format_version": FEEDBACK_FORMAT_VERSION,
        "run_id": run_id,
        "user_id": user_id,
        "updated_at": _utc_now(),
        "annotations": _json_safe(annotations),
      }
      self._persist_feedback_locked(document)
      return self._public_feedback(document)

  def build_feedback_export(self, run_id: str, user_id: str) -> bytes | None:
    """Build a redacted trace bundle augmented with local review annotations."""
    document = self.get_run(run_id, user_id)
    feedback = self.get_feedback(run_id, user_id)
    if document is None or feedback is None:
      return None
    redacted_trace = _redact_export(document)
    redacted_feedback = _redact_export(feedback)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      self._write_trace_export(archive, redacted_trace)
      archive.writestr("feedback.json", json.dumps(redacted_feedback, indent=2, sort_keys=True))
      archive.writestr("feedback-summary.md", self._feedback_summary_markdown(redacted_trace, redacted_feedback))
    return stream.getvalue()

  def _append_event_locked(self, document: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
    document["events"].append({
      "index": len(document["events"]),
      "type": event_type,
      "at": _utc_now(),
      "payload": _json_safe(payload),
    })

  def _persist_locked(self, document: dict[str, Any]) -> None:
    self.trace_dir.mkdir(parents=True, exist_ok=True)
    destination = self.trace_dir / f"{document['run_id']}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)

  def _persist_feedback_locked(self, document: dict[str, Any]) -> None:
    self.feedback_dir.mkdir(parents=True, exist_ok=True)
    destination = self._feedback_path(document["run_id"])
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)

  def _document_locked(self, run_id: str) -> dict[str, Any] | None:
    if run_id in self._runs:
      return self._runs[run_id]
    path = self.trace_dir / f"{run_id}.json"
    if not path.is_file():
      return None
    try:
      return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
      return None

  def _all_documents_locked(self) -> list[dict[str, Any]]:
    documents = {run_id: document for run_id, document in self._runs.items()}
    if self.trace_dir.is_dir():
      for path in self.trace_dir.glob("*.json"):
        if path.stem in documents:
          continue
        try:
          documents[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
          continue
    return list(documents.values())

  def _feedback_document_locked(self, run_id: str) -> dict[str, Any] | None:
    path = self._feedback_path(run_id)
    if not path.is_file():
      return None
    try:
      document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
      return None
    return document if str(document.get("run_id") or "") == run_id else None

  def _feedback_path(self, run_id: str) -> Path:
    return self.feedback_dir / f"{run_id}.json"

  @staticmethod
  def _is_owned_by(document: dict[str, Any], user_id: str) -> bool:
    return str((document.get("metadata") or {}).get("user_id") or "") == user_id

  @staticmethod
  def _summary(document: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata") or {}
    return {
      "run_id": document.get("run_id"),
      "status": document.get("status"),
      "created_at": document.get("created_at"),
      "finished_at": document.get("finished_at"),
      "video_id": metadata.get("video_id"),
      "exercise_type": metadata.get("exercise_type"),
      "view_type": metadata.get("view_type"),
      "model_version": metadata.get("model_version"),
      "event_count": len(document.get("events") or []),
    }

  @classmethod
  def _review_projection(cls, document: dict[str, Any]) -> dict[str, Any]:
    """Keep browser review data bounded while retaining full-trace export."""
    events: list[dict[str, Any]] = []
    for event in document.get("events") or []:
      payload = event.get("payload") or {}
      snapshot_name = payload.get("name") if event.get("type") == "snapshot" else None
      if snapshot_name and snapshot_name not in REVIEW_SNAPSHOT_NAMES:
        continue
      projected_payload: dict[str, Any]
      if snapshot_name:
        projected_payload = {"name": snapshot_name}
        frames = payload.get("frames")
        if isinstance(frames, list):
          projected_payload["frames"] = [cls._review_frame(frame) for frame in frames if isinstance(frame, dict)]
        if snapshot_name == "barbell_tracking":
          projected_payload["barbell_path"] = cls._review_barbell_path(payload.get("barbell_path"))
          projected_payload["diagnostics"] = cls._review_value(payload.get("diagnostics"))
        elif snapshot_name == "pose_repair":
          projected_payload["pose_repair"] = cls._review_value(payload.get("pose_repair"))
        elif snapshot_name == "pin_fusion":
          projected_payload["manual_tracking"] = cls._review_manual_tracking(payload.get("manual_tracking"))
          projected_payload["tracking_assistance"] = cls._review_value(payload.get("tracking_assistance"))
        elif snapshot_name == "exercise_metrics":
          projected_payload["result"] = cls._review_value(payload.get("result"))
      else:
        projected_payload = cls._review_value(payload)
      events.append({
        "index": event.get("index"),
        "type": event.get("type"),
        "at": event.get("at"),
        "payload": projected_payload,
      })
    return {
      "format_version": document.get("format_version", TRACE_FORMAT_VERSION),
      **cls._summary(document),
      "metadata": {
        "exercise_type": (document.get("metadata") or {}).get("exercise_type"),
        "view_type": (document.get("metadata") or {}).get("view_type"),
        "model_version": (document.get("metadata") or {}).get("model_version"),
      },
      "events": events,
    }

  @staticmethod
  def _review_frame(frame: dict[str, Any]) -> dict[str, Any]:
    landmarks = frame.get("landmarks") or {}
    projected_landmarks = {
      name: {
        key: point.get(key)
        for key in (
          "x", "y", "visibility", "confidence", "accepted_source", "tracking_state",
          "manual_source", "pose_repair_reasons", "chain_failure_reason", "occluded",
          "tracking_lost", "stale_track", "chain_valid", "visual_only",
        )
        if key in point
      }
      for name, point in landmarks.items()
      if isinstance(point, dict) and (
        name.endswith("_upper_back") or name.rsplit("_", 1)[-1] in REVIEW_LANDMARK_SUFFIXES
      )
    }
    return {
      key: frame.get(key)
      for key in ("source_frame_index", "timestamp_ms", "frame_width", "frame_height", "processed_frame_width", "processed_frame_height")
      if key in frame
    } | {"landmarks": projected_landmarks}

  @staticmethod
  def _review_barbell_path(value: Any) -> dict[str, Any]:
    path = value if isinstance(value, dict) else {}
    points = path.get("points") if isinstance(path.get("points"), list) else []
    return {
      "available": path.get("available"),
      "coverage": path.get("coverage"),
      "target": path.get("target"),
      "points": [
        {
          key: point.get(key)
          for key in ("time", "x", "y", "markerX", "markerY", "confidence", "trackingState", "tracking_state", "selectedSource", "selected_source", "manual_assisted", "gap_reason")
          if key in point
        }
        for point in points
        if isinstance(point, dict)
      ],
    }

  @staticmethod
  def _review_manual_tracking(value: Any) -> dict[str, Any]:
    manual_tracking = value if isinstance(value, dict) else {}
    tracks = manual_tracking.get("tracks") if isinstance(manual_tracking.get("tracks"), dict) else {}
    return {
      "tracks": {
        str(name): {
          str(frame_index): {
            key: point.get(key)
            for key in ("x", "y", "confidence", "visibility", "accepted_source", "tracking_state")
            if key in point
          }
          for frame_index, point in track.items()
          if isinstance(point, dict)
        }
        for name, track in tracks.items()
        if isinstance(track, dict)
      },
    }

  @classmethod
  def _review_value(cls, value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
      return value
    if depth >= 3:
      return {"item_count": len(value)} if isinstance(value, (dict, list)) else str(value)
    if isinstance(value, list):
      if len(value) > 24:
        return {"item_count": len(value)}
      return [cls._review_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
      return {str(key): cls._review_value(item, depth=depth + 1) for key, item in value.items()}
    return str(value)

  @staticmethod
  def _public_feedback(document: dict[str, Any]) -> dict[str, Any]:
    return {
      "format_version": document.get("format_version", FEEDBACK_FORMAT_VERSION),
      "run_id": document.get("run_id"),
      "updated_at": document.get("updated_at"),
      "annotations": copy.deepcopy(document.get("annotations") or []),
    }

  def _write_trace_export(self, archive: zipfile.ZipFile, redacted: dict[str, Any]) -> None:
    summary = {
      "format_version": TRACE_FORMAT_VERSION,
      "run_id": redacted["run_id"],
      "status": redacted["status"],
      "created_at": redacted["created_at"],
      "finished_at": redacted["finished_at"],
      "exercise_type": redacted.get("metadata", {}).get("exercise_type"),
      "view_type": redacted.get("metadata", {}).get("view_type"),
      "model_version": redacted.get("metadata", {}).get("model_version"),
      "event_count": len(redacted.get("events") or []),
    }
    archive.writestr("summary.json", json.dumps(summary, indent=2, sort_keys=True))
    archive.writestr("trace.json", json.dumps(redacted, indent=2, sort_keys=True))
    archive.writestr("stage-events.csv", self._stage_events_csv(redacted))
    archive.writestr("frame-timeline.csv", self._frame_timeline_csv(redacted))

  @staticmethod
  def _feedback_summary_markdown(trace: dict[str, Any], feedback: dict[str, Any]) -> str:
    metadata = trace.get("metadata") or {}
    lines = [
      "# Peso analysis feedback",
      "",
      f"- Run: {trace.get('run_id')}",
      f"- Exercise: {metadata.get('exercise_type') or 'unknown'} · {metadata.get('view_type') or 'unknown'}",
      f"- Model: {metadata.get('model_version') or 'unknown'}",
      f"- Updated: {feedback.get('updated_at') or 'not yet saved'}",
      "",
      "## Annotations",
      "",
    ]
    annotations = feedback.get("annotations") or []
    if not annotations:
      lines.append("No annotations recorded.")
      return "\n".join(lines) + "\n"

    for index, annotation in enumerate(annotations, start=1):
      start_ms = annotation.get("start_ms", 0)
      end_ms = annotation.get("end_ms", start_ms)
      lines.extend([
        f"### {index}. {annotation.get('status', 'uncertain').title()} · {start_ms / 1000:.2f}s–{end_ms / 1000:.2f}s",
        "",
        f"- Systems: {', '.join(annotation.get('systems') or []) or 'none'}",
        f"- Issue types: {', '.join(annotation.get('issue_types') or []) or 'none'}",
        f"- Landmarks: {', '.join(annotation.get('landmarks') or []) or 'none'}",
        f"- Expected behavior: {', '.join(annotation.get('expected_behaviors') or []) or 'none'}",
        f"- Responsible stages: {', '.join(annotation.get('source_stages') or []) or 'not attributed'}",
        f"- Severity: {annotation.get('severity') or 'not set'}",
        f"- Keyframes: {len(annotation.get('keyframes') or [])}",
        f"- Point corrections: {len(annotation.get('corrections') or [])}",
      ])
      note = str(annotation.get("notes") or "").strip()
      if note:
        lines.append(f"- Notes: {note}")
      lines.append("")
    return "\n".join(lines)

  def _prune_locked(self) -> None:
    documents = sorted(
      self._all_documents_locked(),
      key=lambda document: document.get("finished_at") or document.get("created_at") or "",
      reverse=True,
    )
    finished = [document for document in documents if document.get("status") != "running"]
    for document in finished[self.max_runs:]:
      run_id = str(document.get("run_id") or "")
      if not run_id:
        continue
      self._runs.pop(run_id, None)
      (self.trace_dir / f"{run_id}.json").unlink(missing_ok=True)
      self._feedback_path(run_id).unlink(missing_ok=True)

  @staticmethod
  def _stage_events_csv(document: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["index", "at", "type", "stage", "duration_ms", "payload"])
    writer.writeheader()
    for event in document.get("events") or []:
      payload = event.get("payload") or {}
      writer.writerow({
        "index": event.get("index"),
        "at": event.get("at"),
        "type": event.get("type"),
        "stage": payload.get("name") or payload.get("stage") or "",
        "duration_ms": payload.get("duration_ms") if payload.get("duration_ms") is not None else "",
        "payload": json.dumps(payload, separators=(",", ":")),
      })
    return output.getvalue()

  @staticmethod
  def _frame_timeline_csv(document: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
      output,
      fieldnames=["snapshot", "source_frame_index", "timestamp_ms", "landmark_sources", "repair_reasons"],
    )
    writer.writeheader()
    for event in document.get("events") or []:
      if event.get("type") != "snapshot":
        continue
      payload = event.get("payload") or {}
      for frame in payload.get("frames") or []:
        landmarks = frame.get("landmarks") or {}
        sources = {
          name: point.get("accepted_source") or point.get("tracking_state")
          for name, point in landmarks.items()
          if isinstance(point, dict) and (point.get("accepted_source") or point.get("tracking_state"))
        }
        repair_reasons = {
          name: point.get("pose_repair_reasons")
          for name, point in landmarks.items()
          if isinstance(point, dict) and point.get("pose_repair_reasons")
        }
        writer.writerow({
          "snapshot": payload.get("name") or "",
          "source_frame_index": frame.get("source_frame_index") if frame.get("source_frame_index") is not None else "",
          "timestamp_ms": frame.get("timestamp_ms") if frame.get("timestamp_ms") is not None else "",
          "landmark_sources": json.dumps(sources, separators=(",", ":")),
          "repair_reasons": json.dumps(repair_reasons, separators=(",", ":")),
        })
    return output.getvalue()


@lru_cache(maxsize=1)
def get_analysis_trace_service() -> AnalysisTraceService:
  settings = get_settings()
  return AnalysisTraceService(
    enabled=settings.analysis_trace_enabled,
    trace_dir=settings.analysis_trace_dir,
    max_runs=settings.analysis_trace_max_runs,
  )


def reset_analysis_trace_service() -> None:
  get_analysis_trace_service.cache_clear()
