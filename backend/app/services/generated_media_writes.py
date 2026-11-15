from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .config import get_settings
from .storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService
from .video_assets import build_playback_storage_path, build_thumbnail_storage_path
from .video_storage_paths import require_user_storage_path


def _canonical_id(value: Any) -> str:
  if not isinstance(value, str) or str(UUID(value)) != value or UUID(value).int == 0:
    raise ValueError("A canonical nonzero generated-media identity is required.")
  return value


def _require_receipt(data: Any, expected: dict[str, Any]) -> None:
  if (not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict)
      or data[0].keys() != expected.keys()
      or any(type(data[0][key]) is not type(value) or data[0][key] != value
             for key, value in expected.items())):
    raise RuntimeError("Generated-media write admission was not durably acknowledged.")


def write_generated_media(
  *,
  video: dict[str, Any],
  purpose: str,
  local_path: Path,
  storage: StorageService,
  analysis_lease: dict[str, Any] | None = None,
) -> str:
  user_id = _canonical_id(video.get("user_id"))
  video_id = _canonical_id(video.get("id"))
  source_path = require_user_storage_path(video.get("storage_path"), user_id, "storage_path")
  if purpose not in {"thumbnail", "playback", "thumbnail_backfill"}:
    raise ValueError("Unsupported generated-media purpose.")
  job_id = worker_id = attempt_count = None
  if purpose == "thumbnail_backfill":
    if analysis_lease is not None:
      raise ValueError("Thumbnail backfill cannot use an analysis lease.")
  else:
    if (not isinstance(analysis_lease, dict)
        or analysis_lease.keys() != {"p_job_id", "p_worker_id", "p_attempt_count"}):
      raise ValueError("A claimed analysis attempt is required for generated media.")
    job_id = _canonical_id(analysis_lease["p_job_id"])
    worker_id, attempt_count = analysis_lease["p_worker_id"], analysis_lease["p_attempt_count"]
    if (not isinstance(worker_id, str) or not worker_id or worker_id.strip() != worker_id
        or type(attempt_count) is not int or attempt_count < 1):
      raise ValueError("A claimed analysis attempt is required for generated media.")
  size_bytes = local_path.stat().st_size
  if size_bytes <= 0:
    raise ValueError("Generated media must contain bytes.")
  attempt_id = str(uuid4())
  if purpose == "playback":
    storage_path = build_playback_storage_path(user_id, video_id, attempt_id)
    content_type = "video/mp4"
  else:
    storage_path = build_thumbnail_storage_path(user_id, video_id, attempt_id)
    content_type = "image/jpeg"
  fields = {
    "attempt_id": attempt_id, "user_id": user_id, "video_id": video_id, "purpose": purpose,
    "bucket": storage.bucket, "storage_path": storage_path, "source_path": source_path,
    "content_type": content_type, "size_bytes": size_bytes,
    "job_id": job_id, "worker_id": worker_id, "attempt_count": attempt_count,
  }
  parameters = {"p_" + key: value for key, value in fields.items()}
  expected = {**fields, "state": "dispatching"}
  settings = get_settings()
  admission = {**parameters, "p_max_user_bytes": settings.max_user_reserved_bytes,
               "p_max_global_bytes": settings.object_storage_limit_bytes}
  response = storage.client.rpc("admit_private_media_generated_write", admission).execute()
  _require_receipt(response.data, expected)
  # A fresh RPC response alone does not prove the write transaction committed.
  persisted = (storage.client.table("private_media_generated_writes")
               .select(",".join(expected)).eq("attempt_id", attempt_id).limit(2).execute())
  _require_receipt(persisted.data, expected)
  storage.create_file(storage_path, local_path, content_type,
                      cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS)
  observed = storage.client.rpc("observe_private_media_generated_write_success", parameters).execute()
  if observed.data is not True:
    raise RuntimeError("Generated-media upload success was not acknowledged.")
  return storage_path
