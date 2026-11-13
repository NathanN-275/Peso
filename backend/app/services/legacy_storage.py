from __future__ import annotations

from .config import get_settings


def is_azure_source_path(storage_path: str) -> bool:
  parts = storage_path.split("/")
  return len(parts) >= 3 and parts[1] == "source"


def get_azure_blob_storage():
  if get_settings().runtime_profile == "web-mvp":
    raise RuntimeError("Azure storage is unavailable in the web-mvp runtime.")
  try:
    from .azure_blob_storage import get_azure_blob_storage as get_legacy_storage
  except ImportError as error:
    raise RuntimeError("Azure storage is unavailable in this runtime image.") from error
  return get_legacy_storage()
