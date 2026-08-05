from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from ..services.auth import get_current_user_id
from ..services.saved_lift_exports import MAX_SAVED_LIFT_EXPORT_ITEMS, SavedLiftExportService


router = APIRouter(prefix="/saved-lift-exports", tags=["saved-lift-exports"])


class CreateSavedLiftExportRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  lift_ids: list[UUID] = Field(min_length=1, max_length=MAX_SAVED_LIFT_EXPORT_ITEMS)


class SavedLiftExportJobResponse(BaseModel):
  id: UUID
  status: Literal["queued", "processing", "completed", "failed", "expired"]
  lift_ids: list[UUID]
  lift_count: int
  created_at: str
  completed_at: str | None = None
  expires_at: str | None = None
  download_url: str | None = None
  download_expires_in: int | None = None
  failure_code: str | None = None


def _process_saved_lift_export(job_id: str, user_id: str) -> None:
  SavedLiftExportService().process_job(job_id, user_id)


@router.post("", response_model=SavedLiftExportJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_saved_lift_export(
  request: CreateSavedLiftExportRequest,
  background_tasks: BackgroundTasks,
  user_id: str = Depends(get_current_user_id),
) -> SavedLiftExportJobResponse:
  service = SavedLiftExportService()
  job = service.create_job(user_id, [str(lift_id) for lift_id in request.lift_ids])
  job_id = str(job["id"])
  background_tasks.add_task(_process_saved_lift_export, job_id, user_id)
  return SavedLiftExportJobResponse(**service.job_projection(job_id, user_id))


@router.get("/{job_id}", response_model=SavedLiftExportJobResponse)
def get_saved_lift_export(
  job_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> SavedLiftExportJobResponse:
  return SavedLiftExportJobResponse(
    **SavedLiftExportService().job_projection(str(job_id), user_id)
  )
