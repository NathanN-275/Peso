from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..services.config import get_settings
from ..services.supabase_client import get_supabase_admin_client


router = APIRouter(prefix="/internal/budget-admission", include_in_schema=False)
logger = logging.getLogger(__name__)


def _authorize_budget_token(token: str | None) -> None:
  expected = get_settings().budget_shutdown_token
  if not expected or not token or not hmac.compare_digest(expected, token):
    logger.warning("Budget webhook rejected event=budget_webhook_auth_failure")
    raise HTTPException(status_code=401, detail="Invalid budget webhook authorization.")


class IntakeMeasurement(BaseModel):
  model_config = ConfigDict(extra="forbid")
  observed_at: AwareDatetime
  projected_monthly_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
  storage_used_bytes: int = Field(ge=0, strict=True)


@router.post("/evaluate")
def evaluate_budget_admission(
  measurement: IntakeMeasurement,
  x_budget_token: str | None = Header(default=None),
) -> dict[str, object]:
  """Consume a trusted monitor sample; never automatically reopen intake."""
  _authorize_budget_token(x_budget_token)
  settings = get_settings()
  age = (datetime.now(timezone.utc) - measurement.observed_at).total_seconds()
  if age < -30 or age > 300:
    raise HTTPException(status_code=422, detail="Intake measurements must be current (within five minutes).")
  if settings.intake_stop_projected_monthly_usd is None:
    raise HTTPException(status_code=503, detail="The owner-reviewed intake spend threshold is not configured.")
  reasons = []
  if measurement.projected_monthly_usd >= settings.intake_stop_projected_monthly_usd:
    reasons.append("projected_spend")
  if measurement.storage_used_bytes >= settings.object_storage_limit_bytes * settings.storage_block_ratio:
    reasons.append("storage_pressure")
  if reasons:
    get_supabase_admin_client().rpc("disable_video_upload_admission", {}).execute()
    logger.warning("Intake stop event=intake_stop reasons=%s", ",".join(reasons))
  alert = measurement.projected_monthly_usd >= Decimal("35")
  if alert:
    logger.warning("Projected monthly spend alert event=projected_spend_alert threshold_usd=35")
  # stop_triggered describes this sample. A healthy sample does not imply the
  # durable switch is enabled; it may already be stopped by another event.
  return {"stop_triggered": bool(reasons), "reasons": reasons, "spend_alert": alert}


@router.post("/disable")
def disable_budget_admission(x_budget_token: str | None = Header(default=None)) -> dict[str, bool]:
  _authorize_budget_token(x_budget_token)
  get_supabase_admin_client().rpc("disable_video_upload_admission", {}).execute()
  logger.warning("New upload reservations disabled event=budget_admission_shutdown")
  return {"uploads_enabled": False}
