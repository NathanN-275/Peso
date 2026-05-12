from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
  supabase_url: str
  supabase_service_role_key: str
  supabase_jwt_secret: str
  video_bucket: str = "videos"
  model_version: str = "mediapipe-pose-v1"
  cors_origins: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  supabase_url = os.getenv("SUPABASE_URL", "").strip()
  supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
  supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
  video_bucket = os.getenv("VIDEO_BUCKET", "videos").strip() or "videos"
  model_version = os.getenv("MODEL_VERSION", "mediapipe-pose-v1").strip() or "mediapipe-pose-v1"
  cors_origins_raw = os.getenv(
    "BACKEND_CORS_ORIGINS",
    "http://localhost:8081,http://127.0.0.1:8081,http://localhost:8082,http://127.0.0.1:8082,http://localhost:19006,http://127.0.0.1:19006,http://localhost:3000,http://127.0.0.1:3000",
  )
  cors_origins = tuple(origin.strip() for origin in cors_origins_raw.split(",") if origin.strip())

  missing = [
    name
    for name, value in (
      ("SUPABASE_URL", supabase_url),
      ("SUPABASE_SERVICE_ROLE_KEY", supabase_service_role_key),
      ("SUPABASE_JWT_SECRET", supabase_jwt_secret),
    )
    if not value
  ]

  if missing:
    raise RuntimeError(f"Missing required backend environment variables: {', '.join(missing)}")

  return Settings(
    supabase_url=supabase_url,
    supabase_service_role_key=supabase_service_role_key,
    supabase_jwt_secret=supabase_jwt_secret,
    video_bucket=video_bucket,
    model_version=model_version,
    cors_origins=cors_origins,
  )
