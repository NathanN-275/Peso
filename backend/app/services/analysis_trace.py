from __future__ import annotations

import copy
import csv
import io
import json
import math
import threading
import time
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

from .config import Settings, get_settings


TRACE_FORMAT_VERSION = 1
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
  if normalized_key in EXPORT_REDACTED_KEYS or any(
    sensitive in normalized_key
    for sensitive in ("token", "secret", "authorization", "storage_path", "signed_url", "video_url")
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
      return copy.deepcopy(document)

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
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("summary.json", json.dumps(summary, indent=2, sort_keys=True))
      archive.writestr("trace.json", json.dumps(redacted, indent=2, sort_keys=True))
      archive.writestr("stage-events.csv", self._stage_events_csv(redacted))
      archive.writestr("frame-timeline.csv", self._frame_timeline_csv(redacted))
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
        "duration_ms": payload.get("duration_ms") or "",
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
          "source_frame_index": frame.get("source_frame_index") or "",
          "timestamp_ms": frame.get("timestamp_ms") or "",
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
