from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import get_settings
from .supabase_client import get_supabase_admin_client


class StorageService:
  def __init__(self) -> None:
    settings = get_settings()
    self.bucket = settings.video_bucket
    self.client = get_supabase_admin_client()

  def download_to_tempfile(self, storage_path: str) -> Path:
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
