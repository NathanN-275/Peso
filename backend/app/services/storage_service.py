from __future__ import annotations

import os
import tempfile
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
