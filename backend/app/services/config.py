from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_CORS_ORIGINS = (
  "http://localhost:8081",
  "http://127.0.0.1:8081",
  "http://localhost:8082",
  "http://127.0.0.1:8082",
  "http://localhost:19006",
  "http://127.0.0.1:19006",
  "http://localhost:3000",
  "http://127.0.0.1:3000",
)

LOCAL_DEV_CORS_ORIGIN_REGEX = (
  r"^https?://((localhost|127\.0\.0\.1|0\.0\.0\.0)|"
  r"10\.\d+\.\d+\.\d+|"
  r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
  r"192\.168\.\d+\.\d+):\d+$"
)
DEFAULT_MAX_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
  backend_env: str
  supabase_url: str
  supabase_service_role_key: str
  supabase_jwt_secret: str
  video_bucket: str = "videos"
  max_video_upload_bytes: int = 50 * 1024 * 1024
  model_version: str = "mediapipe-rtmpose-v1-rack-fallback"
  cors_origins: tuple[str, ...] = ()
  cors_origin_regex: str | None = None
  cors_allow_private_network: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  backend_env = os.getenv("BACKEND_ENV", "development").strip().lower() or "development"
  supabase_url = os.getenv("SUPABASE_URL", "").strip()
  supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
  supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
  video_bucket = os.getenv("VIDEO_BUCKET", "videos").strip() or "videos"
  max_video_upload_bytes_raw = os.getenv(
    "MAX_VIDEO_UPLOAD_BYTES",
    str(DEFAULT_MAX_VIDEO_UPLOAD_BYTES),
  ).strip()

  try:
    max_video_upload_bytes = int(max_video_upload_bytes_raw)
  except ValueError as error:
    raise RuntimeError("MAX_VIDEO_UPLOAD_BYTES must be a positive integer.") from error

  if max_video_upload_bytes <= 0:
    raise RuntimeError("MAX_VIDEO_UPLOAD_BYTES must be a positive integer.")

  model_version = (
    os.getenv("MODEL_VERSION", "mediapipe-rtmpose-v1-rack-fallback").strip()
    or "mediapipe-rtmpose-v1-rack-fallback"
  )
  cors_origins_raw = os.getenv(
    "BACKEND_CORS_ORIGINS",
    ",".join(DEFAULT_CORS_ORIGINS),
  )
  cors_origins = tuple(origin.strip() for origin in cors_origins_raw.split(",") if origin.strip())
  cors_origin_regex = (
    None
    if backend_env in {"production", "prod"}
    else os.getenv("BACKEND_CORS_ORIGIN_REGEX", LOCAL_DEV_CORS_ORIGIN_REGEX).strip() or None
  )
  cors_allow_private_network = (
    backend_env not in {"production", "prod"}
    and os.getenv("BACKEND_CORS_ALLOW_PRIVATE_NETWORK", "true").strip().lower()
    in {"1", "true", "yes", "on"}
  )

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
    backend_env=backend_env,
    supabase_url=supabase_url,
    supabase_service_role_key=supabase_service_role_key,
    supabase_jwt_secret=supabase_jwt_secret,
    video_bucket=video_bucket,
    max_video_upload_bytes=max_video_upload_bytes,
    model_version=model_version,
    cors_origins=cors_origins,
    cors_origin_regex=cors_origin_regex,
    cors_allow_private_network=cors_allow_private_network,
  )
