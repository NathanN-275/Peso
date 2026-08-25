from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routes.videos import router as videos_router
from .routes.analysis_runs import router as analysis_runs_router
from .routes.saved_lift_exports import router as saved_lift_exports_router
from .services.config import get_settings
from .services.http_client import close_pooled_http_client
from .services.analysis_job_repository import AnalysisJobRepository


logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title="Peso Video Analysis API", version="1.0.0")


class LocalDevPrivateNetworkMiddleware(BaseHTTPMiddleware):
  async def dispatch(self, request, call_next):
    response = await call_next(request)

    response.headers.setdefault("Cache-Control", "no-store")

    if settings.cors_allow_private_network:
      response.headers["Access-Control-Allow-Private-Network"] = "true"

    return response

app.add_middleware(
  CORSMiddleware,
  allow_origins=list(settings.cors_origins),
  allow_origin_regex=settings.cors_origin_regex,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(LocalDevPrivateNetworkMiddleware)

app.include_router(videos_router)
app.include_router(analysis_runs_router)
app.include_router(saved_lift_exports_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
  return {"status": "ok"}


@app.get("/health/ready")
def readinesscheck() -> dict[str, str]:
  try:
    AnalysisJobRepository().check_readiness()
  except Exception as error:
    logging.exception("Analysis queue readiness check failed.")
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Analysis queue schema is not ready.",
    ) from error

  return {"status": "ready"}


@app.on_event("shutdown")
def shutdown_http_clients() -> None:
  close_pooled_http_client()
