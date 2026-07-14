from __future__ import annotations

import json
from typing import Generator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..services.analysis_trace import AnalysisTraceService, get_analysis_trace_service
from ..services.auth import get_current_user_id
from ..services.config import get_settings


router = APIRouter(prefix="/dev/analysis-runs", tags=["development"])


class StrictFeedbackModel(BaseModel):
  model_config = ConfigDict(extra="forbid")


class FeedbackKeyframe(StrictFeedbackModel):
  timestamp_ms: float = Field(ge=0)
  source_frame_index: int | None = Field(default=None, ge=0)


class FeedbackCorrection(StrictFeedbackModel):
  timestamp_ms: float = Field(ge=0)
  source_frame_index: int | None = Field(default=None, ge=0)
  target: str = Field(min_length=1, max_length=80)
  x: float = Field(ge=0, le=1)
  y: float = Field(ge=0, le=1)
  visibility: Literal["visible", "occluded", "invalid"] = "visible"


class FeedbackAnnotation(StrictFeedbackModel):
  id: str = Field(min_length=1, max_length=100)
  status: Literal["good", "bad", "uncertain"]
  start_ms: float = Field(ge=0)
  end_ms: float = Field(ge=0)
  systems: list[str] = Field(default_factory=list, max_length=8)
  issue_types: list[str] = Field(default_factory=list, max_length=12)
  landmarks: list[str] = Field(default_factory=list, max_length=20)
  expected_behaviors: list[str] = Field(default_factory=list, max_length=12)
  severity: Literal["visual_only", "metric_changing", "blocking"] = "visual_only"
  notes: str = Field(default="", max_length=4000)
  keyframes: list[FeedbackKeyframe] = Field(default_factory=list, max_length=100)
  corrections: list[FeedbackCorrection] = Field(default_factory=list, max_length=100)

  @model_validator(mode="after")
  def end_must_not_precede_start(self) -> "FeedbackAnnotation":
    if self.end_ms < self.start_ms:
      raise ValueError("end_ms must be greater than or equal to start_ms.")
    return self


class FeedbackDocumentRequest(StrictFeedbackModel):
  annotations: list[FeedbackAnnotation] = Field(default_factory=list, max_length=200)


def _trace_service() -> AnalysisTraceService:
  settings = get_settings()
  if not settings.analysis_trace_enabled:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis tracing is disabled.")
  return get_analysis_trace_service()


def _owned_run_or_404(service: AnalysisTraceService, run_id: str, user_id: str) -> dict:
  run = service.get_run(run_id, user_id)
  if run is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis trace not found.")
  return run


@router.get("")
def list_analysis_runs(
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> dict:
  return {"runs": service.list_runs(user_id)}


@router.get("/{run_id}")
def get_analysis_run(
  run_id: str,
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> dict:
  return _owned_run_or_404(service, run_id, user_id)


@router.get("/{run_id}/feedback")
def get_analysis_feedback(
  run_id: str,
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> dict:
  feedback = service.get_feedback(run_id, user_id)
  if feedback is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis trace not found.")
  return feedback


@router.put("/{run_id}/feedback")
def save_analysis_feedback(
  run_id: str,
  request: FeedbackDocumentRequest,
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> dict:
  feedback = service.save_feedback(run_id, user_id, [annotation.model_dump() for annotation in request.annotations])
  if feedback is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis trace not found.")
  return feedback


@router.get("/{run_id}/events")
def stream_analysis_run_events(
  run_id: str,
  after: int = Query(default=0, ge=0),
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> StreamingResponse:
  _owned_run_or_404(service, run_id, user_id)

  def event_stream() -> Generator[str, None, None]:
    for event in service.iter_events(run_id, user_id, after=after):
      yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

  return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
  )


@router.get("/{run_id}/export")
def export_analysis_run(
  run_id: str,
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> StreamingResponse:
  archive = service.build_export(run_id, user_id)
  if archive is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis trace not found.")

  return StreamingResponse(
    iter([archive]),
    media_type="application/zip",
    headers={
      "Content-Disposition": f'attachment; filename="peso-analysis-trace-{run_id}.zip"',
      "Cache-Control": "no-store",
    },
  )


@router.get("/{run_id}/feedback/export")
def export_analysis_feedback(
  run_id: str,
  user_id: str = Depends(get_current_user_id),
  service: AnalysisTraceService = Depends(_trace_service),
) -> StreamingResponse:
  archive = service.build_feedback_export(run_id, user_id)
  if archive is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis trace not found.")

  return StreamingResponse(
    iter([archive]),
    media_type="application/zip",
    headers={
      "Content-Disposition": f'attachment; filename="peso-analysis-feedback-{run_id}.zip"',
      "Cache-Control": "no-store",
    },
  )
