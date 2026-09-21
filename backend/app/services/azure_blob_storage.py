from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import get_settings


class AzureBlobConfigurationError(RuntimeError):
  pass


def is_azure_source_path(storage_path: str) -> bool:
  parts = storage_path.split("/")
  return len(parts) >= 3 and parts[1] == "source"


class AzureBlobStorageService:
  """Private source-video access using Entra credentials, never account keys."""

  def __init__(self) -> None:
    settings = get_settings()
    if not settings.azure_blob_account_url:
      raise AzureBlobConfigurationError("Azure Blob Storage is not configured.")

    try:
      from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
      from azure.storage.blob import BlobServiceClient
    except ImportError as error:
      raise AzureBlobConfigurationError("Azure Blob Storage dependencies are unavailable.") from error

    credential_options: dict[str, Any] = {}
    if settings.azure_managed_identity_client_id:
      credential_options["managed_identity_client_id"] = settings.azure_managed_identity_client_id

    self.account_url = settings.azure_blob_account_url
    self.account_name = self.account_url.removeprefix("https://").split(".", 1)[0]
    self.container_name = settings.azure_blob_source_container
    self.credential = (
      ManagedIdentityCredential(client_id=settings.azure_managed_identity_client_id)
      if settings.backend_env in {"production", "prod"}
      else DefaultAzureCredential(**credential_options)
    )
    self.service = BlobServiceClient(account_url=self.account_url, credential=self.credential)
    self.container = self.service.get_container_client(self.container_name)

  def create_write_sas(self, blob_path: str, *, expires_at: datetime) -> str:
    try:
      from azure.storage.blob import BlobSasPermissions, generate_blob_sas

      now = datetime.now(timezone.utc)
      delegation_key = self.service.get_user_delegation_key(
        key_start_time=now - timedelta(minutes=5),
        key_expiry_time=expires_at,
      )
      token = generate_blob_sas(
        account_name=self.account_name,
        container_name=self.container_name,
        blob_name=blob_path,
        user_delegation_key=delegation_key,
        # Single Put Blob may create, but cannot overwrite, read, list or delete.
        # Keeping `w` absent prevents mutation after metadata verification.
        permission=BlobSasPermissions(create=True),
        start=now - timedelta(minutes=1),
        expiry=expires_at,
        protocol="https",
      )
    except Exception as error:
      raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to reserve private upload storage. Try again shortly.",
      ) from error

    return f"{self.account_url}/{self.container_name}/{blob_path}?{token}"

  def create_read_sas(self, blob_path: str, *, expires_in: int) -> str:
    try:
      from azure.storage.blob import BlobSasPermissions, generate_blob_sas

      now = datetime.now(timezone.utc)
      expires_at = now + timedelta(seconds=expires_in)
      delegation_key = self.service.get_user_delegation_key(
        key_start_time=now - timedelta(minutes=5),
        key_expiry_time=expires_at,
      )
      token = generate_blob_sas(
        account_name=self.account_name,
        container_name=self.container_name,
        blob_name=blob_path,
        user_delegation_key=delegation_key,
        permission=BlobSasPermissions(read=True),
        start=now - timedelta(minutes=1),
        expiry=expires_at,
        protocol="https",
      )
    except Exception as error:
      raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to create a private media URL. Try again shortly.",
      ) from error

    return f"{self.account_url}/{self.container_name}/{blob_path}?{token}"

  def get_object_info(self, blob_path: str) -> dict[str, Any]:
    try:
      properties = self.container.get_blob_client(blob_path).get_blob_properties()
    except Exception as error:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Uploaded video file was not found in storage.",
      ) from error

    content_type = getattr(getattr(properties, "content_settings", None), "content_type", None)
    return {
      "size": int(getattr(properties, "size", 0) or 0),
      "contentType": content_type,
      "etag": str(getattr(properties, "etag", "") or ""),
    }

  def download_to_path(self, blob_path: str, destination: Path, *, max_bytes: int) -> int:
    downloaded_bytes = 0
    try:
      stream = self.container.get_blob_client(blob_path).download_blob(
        max_concurrency=1, timeout=60, connection_timeout=10, read_timeout=60,
      )
      with destination.open("wb") as target:
        for chunk in stream.chunks():
          downloaded_bytes += len(chunk)
          if downloaded_bytes > max_bytes:
            raise HTTPException(
              status_code=status.HTTP_413_CONTENT_TOO_LARGE,
              detail="Downloaded video exceeds the configured analysis limit.",
            )
          target.write(chunk)
    except HTTPException:
      raise
    except Exception as error:
      raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to download uploaded video from storage.",
      ) from error
    return downloaded_bytes

  def delete(self, blob_path: str) -> None:
    from azure.core.exceptions import ResourceNotFoundError

    try:
      self.container.delete_blob(blob_path, delete_snapshots="include")
    except ResourceNotFoundError:
      return

  def list_objects(self, prefix: str = "") -> list[dict[str, Any]]:
    return [
      {
        "path": blob.name,
        "name": blob.name.rsplit("/", 1)[-1],
        "metadata": {"size": blob.size},
        "created_at": blob.creation_time.isoformat() if blob.creation_time else None,
        "updated_at": blob.last_modified.isoformat() if blob.last_modified else None,
      }
      for blob in self.container.list_blobs(name_starts_with=prefix)
    ]


@lru_cache(maxsize=1)
def get_azure_blob_storage() -> AzureBlobStorageService:
  return AzureBlobStorageService()
