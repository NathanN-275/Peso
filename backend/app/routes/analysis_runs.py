from __future__ import annotations

import json
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..services.analysis_trace import AnalysisTraceService, get_analysis_trace_service
from ..services.auth import get_current_user_id
from ..services.config import get_settings


router = APIRouter(prefix="/dev/analysis-runs", tags=["development"])


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
