from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routes.videos import router as videos_router
from .routes.analysis_runs import router as analysis_runs_router
from .routes.saved_lift_exports import router as saved_lift_exports_router
from .routes.upload_reservations import router as upload_reservations_router
from .routes.budget_admission import router as budget_admission_router
from .services.security_logging import configure_security_logging
from .services.config import get_settings
from .services.http_client import close_pooled_http_client
from .services.analysis_job_repository import AnalysisJobRepository


configure_security_logging()

settings = get_settings()
is_production = settings.backend_env in {"production", "prod"}
app = FastAPI(
  title="Peso Video Analysis API",
  version="1.0.0",
  docs_url=None if is_production else "/docs",
  redoc_url=None if is_production else "/redoc",
  openapi_url=None if is_production else "/openapi.json",
)


class LocalDevPrivateNetworkMiddleware(BaseHTTPMiddleware):
  async def dispatch(self, request, call_next):
    response = await call_next(request)

    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    # Interactive documentation is development-only and loads its own assets.
    if is_production or request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
      response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    if settings.backend_env in {"production", "prod"}:
      response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

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
app.include_router(upload_reservations_router)
app.include_router(budget_admission_router)


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
