from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


VIDEO_STORAGE_PATH_FIELDS = (
  "storage_path",
  "original_storage_path",
  "playback_path",
  "thumbnail_path",
)


def _path_parts(path: str) -> list[str]:
  return [part for part in path.strip("/").split("/") if part]


def storage_path_belongs_to_user(path: str | None, user_id: str | None) -> bool:
  if not path or not user_id:
    return False

  parts = _path_parts(path)
  return len(parts) >= 2 and parts[0] == user_id and ".." not in parts


def require_user_storage_path(path: str | None, user_id: str, label: str = "storage path") -> str:
  if storage_path_belongs_to_user(path, user_id):
    return str(path)

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
