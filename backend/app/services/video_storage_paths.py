from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

VIDEO_STORAGE_PATH_FIELDS = (
  "storage_path",
  "original_storage_path",
  "playback_path",
  "thumbnail_path",
)


def _path_parts(path: str) -> list[str]:
  return path.split("/")


def storage_path_validation_error(path: str | None, user_id: str | None) -> str | None:
  if not path:
    return "missing_path"

  if not user_id:
    return "missing_user_id"

  if path != path.strip() or path.startswith("/") or path.endswith("/"):
    return "invalid_path_boundary"

  if "\\" in path or "://" in path or any(ord(char) < 32 for char in path):
    return "invalid_path_characters"

  parts = _path_parts(path)
  if len(parts) < 2 or any(not part for part in parts):
    return "invalid_path_shape"

  if any(part in {".", ".."} for part in parts):
    return "path_traversal"

  if parts[0] != user_id:
    return "wrong_owner"

  return None


def storage_path_belongs_to_user(path: str | None, user_id: str | None) -> bool:
  return storage_path_validation_error(path, user_id) is None


def require_user_storage_path(path: str | None, user_id: str, label: str = "storage path") -> str:
  reason = storage_path_validation_error(path, user_id)
  if reason is None:
    return str(path)

  logger.warning(
    "Rejected storage path user_id=%s label=%s reason=%s path=%s",
    user_id,
    label,
    reason,
    path,
  )
  raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail=f"{label} is outside the current user folder.",
  )


def require_video_storage_paths_owned(video: dict[str, Any]) -> None:
  user_id = str(video.get("user_id") or "")

  for key in VIDEO_STORAGE_PATH_FIELDS:
    path = video.get(key)

    if path:
      require_user_storage_path(str(path), user_id, key)


def owned_video_storage_paths(video: dict[str, Any]) -> list[str]:
  user_id = str(video.get("user_id") or "")
  paths: list[str] = []

  for key in VIDEO_STORAGE_PATH_FIELDS:
    path = video.get(key)

    if isinstance(path, str) and storage_path_belongs_to_user(path, user_id):
      paths.append(path)

  return paths
