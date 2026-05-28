from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import get_settings
from .supabase_client import get_supabase_admin_client


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
ALLOWED_VIDEO_MIME_TYPES = {
  "video/mp4",
  "video/quicktime",
  "video/x-m4v",
  "video/m4v",
}
STORAGE_DELETE_BATCH_SIZE = 1000


def _metadata_value(object_info: dict[str, Any], *keys: str) -> Any:
  metadata = object_info.get("metadata")

  for key in keys:
    if key in object_info:
      return object_info[key]

    if isinstance(metadata, dict) and key in metadata:
      return metadata[key]

  return None


def _parse_size_bytes(value: Any) -> int | None:
  if isinstance(value, int):
    return value

  if isinstance(value, str) and value.isdigit():
    return int(value)

  return None


def object_size_bytes(object_info: dict[str, Any]) -> int:
  size_bytes = _parse_size_bytes(
    _metadata_value(object_info, "size", "contentLength", "content_length")
  )
  return size_bytes or 0


def object_updated_at(object_info: dict[str, Any]) -> datetime | None:
  value = object_info.get("updated_at") or object_info.get("created_at")

  if not isinstance(value, str):
    return None

  normalized_value = value.replace("Z", "+00:00")

  try:
    return datetime.fromisoformat(normalized_value)
  except ValueError:
    return None


class StorageService:
  def __init__(self) -> None:
    settings = get_settings()
    self.bucket = settings.video_bucket
    self.max_video_upload_bytes = settings.max_video_upload_bytes
    self.client = get_supabase_admin_client()

  def get_object_info(self, storage_path: str) -> dict[str, Any]:
    try:
      response = self.client.storage.from_(self.bucket).info(storage_path)
    except Exception as error:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Uploaded video file was not found in storage.",
      ) from error

    if isinstance(response, list):
      if not response:
        raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail="Uploaded video file was not found in storage.",
        )
      return response[0]

    if isinstance(response, dict):
      return response

    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Unable to read uploaded video metadata.",
    )

  def validate_video_object(self, storage_path: str) -> dict[str, Any]:
    extension = Path(storage_path).suffix.lower()

    if extension not in ALLOWED_VIDEO_EXTENSIONS:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported video file type. Upload an MP4, MOV, or M4V file.",
      )

    object_info = self.get_object_info(storage_path)
    mime_type = _metadata_value(object_info, "mimetype", "mimeType", "contentType", "content_type")

    if not isinstance(mime_type, str) or mime_type.lower() not in ALLOWED_VIDEO_MIME_TYPES:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported video MIME type. Upload an MP4, MOV, or M4V video.",
      )

    size_bytes = _parse_size_bytes(
      _metadata_value(object_info, "size", "contentLength", "content_length")
    )

    if size_bytes is None:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to verify uploaded video size.",
      )

    if size_bytes > self.max_video_upload_bytes:
      raise HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail="Uploaded video exceeds the configured analysis limit.",
      )

    return object_info

  def download_to_tempfile(self, storage_path: str) -> Path:
    self.validate_video_object(storage_path)
    file_bytes = self.client.storage.from_(self.bucket).download(storage_path)
    suffix = Path(storage_path).suffix or ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
      temp_file.write(file_bytes)
      return Path(temp_file.name)

  def remove_tempfile(self, path: Path) -> None:
    try:
      os.remove(path)
    except FileNotFoundError:
      return

  def delete_storage_path(self, storage_path: str) -> None:
    self.client.storage.from_(self.bucket).remove([storage_path])

  def delete_storage_paths(self, storage_paths: list[str]) -> None:
    for index in range(0, len(storage_paths), STORAGE_DELETE_BATCH_SIZE):
      batch = storage_paths[index:index + STORAGE_DELETE_BATCH_SIZE]

      if batch:
        self.client.storage.from_(self.bucket).remove(batch)

  def delete_storage_prefix(self, prefix: str) -> None:
    folder, _, name_prefix = prefix.rstrip("/").rpartition("/")
    try:
      objects = self.client.storage.from_(self.bucket).list(folder)
    except Exception:
      return

    paths = [
      f"{folder}/{item['name']}" if folder else item["name"]
      for item in objects
      if isinstance(item, dict)
      and item.get("name")
      and str(item["name"]).startswith(name_prefix)
    ]

    if paths:
      self.delete_storage_paths(paths)

  def list_objects_recursive(self, prefix: str = "") -> list[dict[str, Any]]:
    bucket = self.client.storage.from_(self.bucket)
    objects: list[dict[str, Any]] = []

    def walk(folder: str) -> None:
      offset = 0

      while True:
        items = bucket.list(folder or None, {"limit": 1000, "offset": offset}) or []

        if not items:
          return

        for item in items:
          name = item.get("name") if isinstance(item, dict) else None

          if not name:
            continue

          storage_path = f"{folder}/{name}" if folder else name

          if item.get("id") is None and object_size_bytes(item) == 0:
            walk(storage_path)
            continue

          normalized_item = dict(item)
          normalized_item["path"] = storage_path
          objects.append(normalized_item)

        if len(items) < 1000:
          return

        offset += len(items)

    walk(prefix.strip("/"))
    return objects

  def storage_path_exists(self, storage_path: str) -> bool:
    try:
      return bool(self.client.storage.from_(self.bucket).exists(storage_path))
    except Exception:
      return False

  def upload_file(self, storage_path: str, local_path: Path, content_type: str) -> None:
    self.client.storage.from_(self.bucket).upload(
      storage_path,
      local_path,
      {
        "content-type": content_type,
        "cache-control": "3600",
        "upsert": "true",
      },
    )

  def create_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
    response = self.client.storage.from_(self.bucket).create_signed_url(
      storage_path,
      expires_in,
    )
    signed_url = response.get("signedUrl") or response.get("signedURL")

    if not signed_url:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to create signed storage URL.",
      )

    return signed_url
