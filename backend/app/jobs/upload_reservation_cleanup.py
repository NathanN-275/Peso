from __future__ import annotations

import logging

from ..services.azure_blob_storage import get_azure_blob_storage
from ..services.upload_reservations import UploadReservationRepository


logger = logging.getLogger(__name__)


def cleanup_upload_reservations() -> int:
  repository = UploadReservationRepository()
  storage = get_azure_blob_storage()
  deleted = 0
  for reservation in repository.expire_due(limit=1000):
    blob_path = str(reservation["blob_path"])
    # Only confirm after the SAS is expired, so a replay cannot recreate a blob
    # after its capacity has been released. Failed deletes are retried next run.
    storage.delete(blob_path)
    repository.mark_blob_deleted(blob_path, confirmed_after_expiry=True)
    deleted += 1
  repository.purge_cleaned_tombstones()
  logger.info("Reservation cleanup completed event=reservation_cleanup deleted_count=%s", deleted)
  return deleted


if __name__ == "__main__":
  from ..services.security_logging import configure_security_logging
  from ..services.storage_cleanup import StorageCleanupService

  configure_security_logging()
  cleanup_upload_reservations()
  report = StorageCleanupService().run()
  if report.errors:
    raise RuntimeError("Storage retention cleanup did not finish successfully.")
