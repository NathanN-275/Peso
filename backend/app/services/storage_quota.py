from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from .config import Settings, get_settings
from .storage_service import StorageService


StorageQuotaStatus = Literal["ok", "warning", "blocked"]


@dataclass(frozen=True)
class StorageQuotaReport:
  storage_limit_bytes: int
  database_limit_bytes: int
  monthly_egress_limit_bytes: int
  current_storage_bytes: int
  upload_size_bytes: int
  playback_allowance_bytes: int
  thumbnail_allowance_bytes: int
  projected_peak_bytes: int
  warning_threshold_bytes: int
  block_threshold_bytes: int
  status: StorageQuotaStatus
  blocked: bool
  message: str

  def to_dict(self) -> dict[str, object]:
    return asdict(self)


def calculate_storage_quota(
  *,
  current_storage_bytes: int,
  upload_size_bytes: int,
  settings: Settings,
) -> StorageQuotaReport:
  current_bytes = max(0, int(current_storage_bytes))
  upload_bytes = max(0, int(upload_size_bytes))
  playback_allowance_bytes = math.ceil(
    upload_bytes * settings.playback_storage_estimate_ratio
  )
  thumbnail_allowance_bytes = settings.thumbnail_storage_allowance_bytes
  projected_peak_bytes = (
    current_bytes
    + upload_bytes
    + playback_allowance_bytes
    + thumbnail_allowance_bytes
  )
  warning_threshold_bytes = math.floor(
    settings.object_storage_limit_bytes * settings.storage_warning_ratio
  )
  block_threshold_bytes = math.floor(
    settings.object_storage_limit_bytes * settings.storage_block_ratio
  )

  if projected_peak_bytes >= block_threshold_bytes:
    quota_status: StorageQuotaStatus = "blocked"
    message = (
      "This upload would use at least 95% of available storage. "
      "Delete saved videos you no longer need before uploading another video."
    )
  elif projected_peak_bytes >= warning_threshold_bytes:
    quota_status = "warning"
    message = (
      "This upload is projected to use at least 80% of available storage. "
      "Saved videos will not be deleted automatically."
    )
  else:
    quota_status = "ok"
    message = "Storage capacity is available for this upload."

  return StorageQuotaReport(
    storage_limit_bytes=settings.object_storage_limit_bytes,
    database_limit_bytes=settings.database_limit_bytes,
    monthly_egress_limit_bytes=settings.monthly_egress_limit_bytes,
    current_storage_bytes=current_bytes,
    upload_size_bytes=upload_bytes,
    playback_allowance_bytes=playback_allowance_bytes,
    thumbnail_allowance_bytes=thumbnail_allowance_bytes,
    projected_peak_bytes=projected_peak_bytes,
    warning_threshold_bytes=warning_threshold_bytes,
    block_threshold_bytes=block_threshold_bytes,
    status=quota_status,
    blocked=quota_status == "blocked",
    message=message,
  )


class StorageQuotaService:
  def __init__(
    self,
    storage: StorageService | None = None,
    settings: Settings | None = None,
  ) -> None:
    self.storage = storage or StorageService()
    self.settings = settings or get_settings()

  def get_usage(self, upload_size_bytes: int = 0) -> StorageQuotaReport:
    storage_objects = self.storage.list_storage_objects_recursive()
    current_storage_bytes = sum(
      StorageService.storage_object_size_bytes(object_info)
      for object_info in storage_objects
      if isinstance(object_info, dict)
    )
    return calculate_storage_quota(
      current_storage_bytes=current_storage_bytes,
      upload_size_bytes=upload_size_bytes,
      settings=self.settings,
    )
