from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.videos import router as videos_router
from .services.config import get_settings


logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title="Peso Video Analysis API", version="1.0.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=list(settings.cors_origins),
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(videos_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
  return {"status": "ok"}
