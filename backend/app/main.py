from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routes.videos import router as videos_router
from .services.config import get_settings


logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title="Peso Video Analysis API", version="1.0.0")


class LocalDevPrivateNetworkMiddleware(BaseHTTPMiddleware):
  async def dispatch(self, request, call_next):
    response = await call_next(request)

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


@app.get("/health")
def healthcheck() -> dict[str, str]:
  return {"status": "ok"}
