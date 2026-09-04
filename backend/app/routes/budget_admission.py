from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from ..services.config import get_settings
from ..services.supabase_client import get_supabase_admin_client


router = APIRouter(prefix="/internal/budget-admission", include_in_schema=False)
logger = logging.getLogger(__name__)


@router.post("/disable")
def disable_budget_admission(x_budget_token: str | None = Header(default=None)) -> dict[str, bool]:
  expected = get_settings().budget_shutdown_token
  if not expected or not x_budget_token or not hmac.compare_digest(expected, x_budget_token):
    logger.warning("Budget webhook rejected event=budget_webhook_auth_failure")
    raise HTTPException(status_code=401, detail="Invalid budget webhook authorization.")
  get_supabase_admin_client().rpc("disable_video_upload_admission", {}).execute()
  logger.warning("New upload reservations disabled event=budget_admission_shutdown")
  return {"uploads_enabled": False}
