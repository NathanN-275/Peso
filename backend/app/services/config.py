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
DEFAULT_MODEL_VERSION = "mediapipe-rtmpose-v3-pin-assisted"
DEFAULT_SAVED_VIDEO_STORAGE_TTL_HOURS = 24
DEFAULT_EXPORT_CACHE_TTL_HOURS = 6
DEFAULT_EXPORT_STORAGE_TTL_HOURS = DEFAULT_EXPORT_CACHE_TTL_HOURS
DEFAULT_ORPHAN_STORAGE_MIN_AGE_HOURS = 24
DEFAULT_STALE_PROCESSING_HOURS = 6
DEFAULT_OBJECT_STORAGE_LIMIT_BYTES = 1024 * 1024 * 1024
DEFAULT_DATABASE_LIMIT_BYTES = 512 * 1024 * 1024
DEFAULT_MONTHLY_EGRESS_LIMIT_BYTES = 5 * 1024 * 1024 * 1024
DEFAULT_STORAGE_WARNING_RATIO = 0.80
DEFAULT_STORAGE_BLOCK_RATIO = 0.95
DEFAULT_PLAYBACK_STORAGE_ESTIMATE_RATIO = 1.0
DEFAULT_THUMBNAIL_STORAGE_ALLOWANCE_BYTES = 1024 * 1024
DEFAULT_ANALYSIS_JOB_LEASE_SECONDS = 60 * 60
DEFAULT_ANALYSIS_WORKER_POLL_SECONDS = 5
DEFAULT_MAX_USER_IN_PROGRESS_VIDEOS = 3
DEFAULT_MAX_USER_UPLOADS_PER_HOUR = 20
DEFAULT_MAX_VIDEO_DURATION_MS = 5 * 60 * 1000
DEFAULT_SIGNED_URL_TTL_SECONDS = 300
DEFAULT_STORAGE_DOWNLOAD_SIGNED_URL_TTL_SECONDS = 120
DEFAULT_FFMPEG_TIMEOUT_SECONDS = 120
DEFAULT_MAX_GLOBAL_VIDEO_WORKERS = 2
DEFAULT_EXPORT_COOLDOWN_SECONDS = 30


@dataclass(frozen=True)
class Settings:
  backend_env: str
  supabase_url: str
  supabase_service_role_key: str
  supabase_jwt_secret: str
  cleanup_job_token: str | None = None
  storage_cleanup_token: str = ""
  video_bucket: str = "videos"
  max_video_upload_bytes: int = 50 * 1024 * 1024
  model_version: str = DEFAULT_MODEL_VERSION
  saved_video_storage_ttl_hours: int = DEFAULT_SAVED_VIDEO_STORAGE_TTL_HOURS
  export_cache_ttl_hours: int = DEFAULT_EXPORT_CACHE_TTL_HOURS
  export_storage_ttl_hours: int = DEFAULT_EXPORT_STORAGE_TTL_HOURS
  orphan_storage_min_age_hours: int = DEFAULT_ORPHAN_STORAGE_MIN_AGE_HOURS
  stale_processing_hours: int = DEFAULT_STALE_PROCESSING_HOURS
  cors_origins: tuple[str, ...] = ()
  cors_origin_regex: str | None = None
  cors_allow_private_network: bool = False
  object_storage_limit_bytes: int = DEFAULT_OBJECT_STORAGE_LIMIT_BYTES
  database_limit_bytes: int = DEFAULT_DATABASE_LIMIT_BYTES
  monthly_egress_limit_bytes: int = DEFAULT_MONTHLY_EGRESS_LIMIT_BYTES
  storage_warning_ratio: float = DEFAULT_STORAGE_WARNING_RATIO
  storage_block_ratio: float = DEFAULT_STORAGE_BLOCK_RATIO
  playback_storage_estimate_ratio: float = DEFAULT_PLAYBACK_STORAGE_ESTIMATE_RATIO
  thumbnail_storage_allowance_bytes: int = DEFAULT_THUMBNAIL_STORAGE_ALLOWANCE_BYTES
  analysis_job_lease_seconds: int = DEFAULT_ANALYSIS_JOB_LEASE_SECONDS
  analysis_worker_poll_seconds: int = DEFAULT_ANALYSIS_WORKER_POLL_SECONDS
  allow_unauthenticated_dev_cleanup: bool = False
  expose_storage_quota_details: bool = False
  max_user_in_progress_videos: int = DEFAULT_MAX_USER_IN_PROGRESS_VIDEOS
  max_user_uploads_per_hour: int = DEFAULT_MAX_USER_UPLOADS_PER_HOUR
  max_video_duration_ms: int = DEFAULT_MAX_VIDEO_DURATION_MS
  signed_url_ttl_seconds: int = DEFAULT_SIGNED_URL_TTL_SECONDS
  storage_download_signed_url_ttl_seconds: int = DEFAULT_STORAGE_DOWNLOAD_SIGNED_URL_TTL_SECONDS
  ffmpeg_timeout_seconds: int = DEFAULT_FFMPEG_TIMEOUT_SECONDS
  max_global_video_workers: int = DEFAULT_MAX_GLOBAL_VIDEO_WORKERS
  export_cooldown_seconds: int = DEFAULT_EXPORT_COOLDOWN_SECONDS


def _parse_positive_int_env(name: str, default: int, *aliases: str) -> int:
  raw_value = ""

  for env_name in (name, *aliases):
    raw_value = os.getenv(env_name, "").strip()

    if raw_value:
      break

  if not raw_value:
    raw_value = str(default)

  try:
    parsed_value = int(raw_value)
  except ValueError as error:
    raise RuntimeError(f"{name} must be a positive integer.") from error

  if parsed_value <= 0:
    raise RuntimeError(f"{name} must be a positive integer.")

  return parsed_value


def _parse_positive_float_env(name: str, default: float) -> float:
  raw_value = os.getenv(name, str(default)).strip() or str(default)

  try:
    parsed_value = float(raw_value)
  except ValueError as error:
    raise RuntimeError(f"{name} must be a positive number.") from error

  if parsed_value <= 0:
    raise RuntimeError(f"{name} must be a positive number.")

  return parsed_value


def _parse_bool_env(name: str, default: bool = False) -> bool:
  raw_value = os.getenv(name, "").strip().lower()

  if not raw_value:
    return default

  return raw_value in {"1", "true", "yes", "on"}


def _origin_is_local(origin: str) -> bool:
  return (
    origin.startswith("http://localhost")
    or origin.startswith("https://localhost")
    or origin.startswith("http://127.0.0.1")
    or origin.startswith("https://127.0.0.1")
    or origin.startswith("http://0.0.0.0")
    or origin.startswith("https://0.0.0.0")
  )


def _origin_is_wildcard(origin: str) -> bool:
  return origin == "*" or origin == "null"


def _private_network_origin_regex_is_unsafe(value: str | None) -> bool:
  if not value:
    return False

  normalized_value = value.lower()
  return (
    "localhost" in normalized_value
    or "127\\." in normalized_value
    or "127." in normalized_value
    or "0\\.0\\.0\\.0" in normalized_value
    or "0.0.0.0" in normalized_value
    or "10\\." in normalized_value
    or "10." in normalized_value
    or "172\\." in normalized_value
    or "172." in normalized_value
    or "192\\.168" in normalized_value
    or "192\\\\.168" in normalized_value
    or "192.168" in normalized_value
  )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  backend_env_raw = os.getenv("BACKEND_ENV", "").strip().lower()
  deployed_environment = any(
    os.getenv(name, "").strip()
    for name in ("RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "VERCEL", "NETLIFY", "AWS_REGION")
  )

  if not backend_env_raw and deployed_environment:
    raise RuntimeError("BACKEND_ENV must be explicitly configured in deployed environments.")

  backend_env = backend_env_raw or "development"
  supabase_url = os.getenv("SUPABASE_URL", "").strip()
  supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
  supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
  cleanup_job_token = (
    os.getenv("STORAGE_CLEANUP_TOKEN", "").strip()
    or os.getenv("CLEANUP_JOB_TOKEN", "").strip()
    or None
  )
  video_bucket = os.getenv("VIDEO_BUCKET", "videos").strip() or "videos"
  max_video_upload_bytes = _parse_positive_int_env(
    "MAX_VIDEO_UPLOAD_BYTES",
    DEFAULT_MAX_VIDEO_UPLOAD_BYTES,
  )
  saved_video_storage_ttl_hours = _parse_positive_int_env(
    "SAVED_VIDEO_STORAGE_TTL_HOURS",
    DEFAULT_SAVED_VIDEO_STORAGE_TTL_HOURS,
  )
  export_cache_ttl_hours = _parse_positive_int_env(
    "EXPORT_CACHE_TTL_HOURS",
    DEFAULT_EXPORT_CACHE_TTL_HOURS,
    "EXPORT_STORAGE_TTL_HOURS",
  )
  orphan_storage_min_age_hours = _parse_positive_int_env(
    "ORPHAN_STORAGE_MIN_AGE_HOURS",
    DEFAULT_ORPHAN_STORAGE_MIN_AGE_HOURS,
  )
  stale_processing_hours = _parse_positive_int_env(
    "STALE_PROCESSING_HOURS",
    DEFAULT_STALE_PROCESSING_HOURS,
  )
  object_storage_limit_bytes = _parse_positive_int_env(
    "OBJECT_STORAGE_LIMIT_BYTES",
    DEFAULT_OBJECT_STORAGE_LIMIT_BYTES,
  )
  database_limit_bytes = _parse_positive_int_env(
    "DATABASE_LIMIT_BYTES",
    DEFAULT_DATABASE_LIMIT_BYTES,
  )
  monthly_egress_limit_bytes = _parse_positive_int_env(
    "MONTHLY_EGRESS_LIMIT_BYTES",
    DEFAULT_MONTHLY_EGRESS_LIMIT_BYTES,
  )
  storage_warning_ratio = _parse_positive_float_env(
    "STORAGE_WARNING_RATIO",
    DEFAULT_STORAGE_WARNING_RATIO,
  )
  storage_block_ratio = _parse_positive_float_env(
    "STORAGE_BLOCK_RATIO",
    DEFAULT_STORAGE_BLOCK_RATIO,
  )
  playback_storage_estimate_ratio = _parse_positive_float_env(
    "PLAYBACK_STORAGE_ESTIMATE_RATIO",
    DEFAULT_PLAYBACK_STORAGE_ESTIMATE_RATIO,
  )
  thumbnail_storage_allowance_bytes = _parse_positive_int_env(
    "THUMBNAIL_STORAGE_ALLOWANCE_BYTES",
    DEFAULT_THUMBNAIL_STORAGE_ALLOWANCE_BYTES,
  )
  analysis_job_lease_seconds = _parse_positive_int_env(
    "ANALYSIS_JOB_LEASE_SECONDS",
    DEFAULT_ANALYSIS_JOB_LEASE_SECONDS,
  )
  analysis_worker_poll_seconds = _parse_positive_int_env(
    "ANALYSIS_WORKER_POLL_SECONDS",
    DEFAULT_ANALYSIS_WORKER_POLL_SECONDS,
  )
  max_user_in_progress_videos = _parse_positive_int_env(
    "MAX_USER_IN_PROGRESS_VIDEOS",
    DEFAULT_MAX_USER_IN_PROGRESS_VIDEOS,
  )
  max_user_uploads_per_hour = _parse_positive_int_env(
    "MAX_USER_UPLOADS_PER_HOUR",
    DEFAULT_MAX_USER_UPLOADS_PER_HOUR,
  )
  max_video_duration_ms = _parse_positive_int_env(
    "MAX_VIDEO_DURATION_MS",
    DEFAULT_MAX_VIDEO_DURATION_MS,
  )
  signed_url_ttl_seconds = _parse_positive_int_env(
    "SIGNED_URL_TTL_SECONDS",
    DEFAULT_SIGNED_URL_TTL_SECONDS,
  )
  storage_download_signed_url_ttl_seconds = _parse_positive_int_env(
    "STORAGE_DOWNLOAD_SIGNED_URL_TTL_SECONDS",
    DEFAULT_STORAGE_DOWNLOAD_SIGNED_URL_TTL_SECONDS,
  )
  ffmpeg_timeout_seconds = _parse_positive_int_env(
    "FFMPEG_TIMEOUT_SECONDS",
    DEFAULT_FFMPEG_TIMEOUT_SECONDS,
  )
  max_global_video_workers = _parse_positive_int_env(
    "MAX_GLOBAL_VIDEO_WORKERS",
    DEFAULT_MAX_GLOBAL_VIDEO_WORKERS,
  )
  export_cooldown_seconds = _parse_positive_int_env(
    "EXPORT_COOLDOWN_SECONDS",
    DEFAULT_EXPORT_COOLDOWN_SECONDS,
  )

  if storage_warning_ratio >= storage_block_ratio or storage_block_ratio > 1:
    raise RuntimeError(
      "Storage quota ratios must satisfy 0 < STORAGE_WARNING_RATIO < "
      "STORAGE_BLOCK_RATIO <= 1."
    )

  model_version = (
    os.getenv("MODEL_VERSION", DEFAULT_MODEL_VERSION).strip()
    or DEFAULT_MODEL_VERSION
  )
  cors_origins_raw = os.getenv(
    "BACKEND_CORS_ORIGINS",
    ",".join(DEFAULT_CORS_ORIGINS),
  )
  cors_origins = tuple(origin.strip() for origin in cors_origins_raw.split(",") if origin.strip())
  allow_unauthenticated_dev_cleanup = _parse_bool_env(
    "BACKEND_ALLOW_UNAUTHENTICATED_DEV_CLEANUP",
    False,
  )
  expose_storage_quota_details = _parse_bool_env("BACKEND_EXPOSE_STORAGE_QUOTA_DETAILS", False)
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

  if backend_env in {"production", "prod"}:
    if not cleanup_job_token:
      raise RuntimeError("CLEANUP_JOB_TOKEN must be configured in production.")

    if not os.getenv("BACKEND_CORS_ORIGINS", "").strip():
      raise RuntimeError("BACKEND_CORS_ORIGINS must be explicitly configured in production.")

    if any(_origin_is_local(origin) for origin in cors_origins):
      raise RuntimeError("BACKEND_CORS_ORIGINS must not include local origins in production.")

    if any(_origin_is_wildcard(origin) for origin in cors_origins):
      raise RuntimeError("BACKEND_CORS_ORIGINS must not include wildcard origins in production.")

    if _private_network_origin_regex_is_unsafe(os.getenv("BACKEND_CORS_ORIGIN_REGEX", "").strip() or None):
      raise RuntimeError("BACKEND_CORS_ORIGIN_REGEX must not allow local or private-network origins in production.")

    if _parse_bool_env("BACKEND_CORS_ALLOW_PRIVATE_NETWORK", False):
      raise RuntimeError("BACKEND_CORS_ALLOW_PRIVATE_NETWORK must not be enabled in production.")

    if os.getenv("POSE_DEBUG_LANDMARK_EXPORT_DIR", "").strip():
      raise RuntimeError("POSE_DEBUG_LANDMARK_EXPORT_DIR must not be enabled in production.")

  if cleanup_job_token is None and not (
    backend_env in {"development", "dev", "local", "test"} and allow_unauthenticated_dev_cleanup
  ):
    raise RuntimeError("CLEANUP_JOB_TOKEN must be configured unless unauthenticated dev cleanup is explicitly enabled.")

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
    cleanup_job_token=cleanup_job_token,
    storage_cleanup_token=cleanup_job_token or "",
    video_bucket=video_bucket,
    max_video_upload_bytes=max_video_upload_bytes,
    model_version=model_version,
    saved_video_storage_ttl_hours=saved_video_storage_ttl_hours,
    export_cache_ttl_hours=export_cache_ttl_hours,
    export_storage_ttl_hours=export_cache_ttl_hours,
    orphan_storage_min_age_hours=orphan_storage_min_age_hours,
    stale_processing_hours=stale_processing_hours,
    cors_origins=cors_origins,
    cors_origin_regex=cors_origin_regex,
    cors_allow_private_network=cors_allow_private_network,
    object_storage_limit_bytes=object_storage_limit_bytes,
    database_limit_bytes=database_limit_bytes,
    monthly_egress_limit_bytes=monthly_egress_limit_bytes,
    storage_warning_ratio=storage_warning_ratio,
    storage_block_ratio=storage_block_ratio,
    playback_storage_estimate_ratio=playback_storage_estimate_ratio,
    thumbnail_storage_allowance_bytes=thumbnail_storage_allowance_bytes,
    analysis_job_lease_seconds=analysis_job_lease_seconds,
    analysis_worker_poll_seconds=analysis_worker_poll_seconds,
    allow_unauthenticated_dev_cleanup=allow_unauthenticated_dev_cleanup,
    expose_storage_quota_details=expose_storage_quota_details,
    max_user_in_progress_videos=max_user_in_progress_videos,
    max_user_uploads_per_hour=max_user_uploads_per_hour,
    max_video_duration_ms=max_video_duration_ms,
    signed_url_ttl_seconds=signed_url_ttl_seconds,
    storage_download_signed_url_ttl_seconds=storage_download_signed_url_ttl_seconds,
    ffmpeg_timeout_seconds=ffmpeg_timeout_seconds,
    max_global_video_workers=max_global_video_workers,
    export_cooldown_seconds=export_cooldown_seconds,
  )
