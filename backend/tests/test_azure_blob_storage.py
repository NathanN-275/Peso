from __future__ import annotations

import base64
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.storage.blob import UserDelegationKey

from app.services.azure_blob_storage import AzureBlobStorageService


class AzureBlobStorageTest(unittest.TestCase):
  def storage(self):
    service = object.__new__(AzureBlobStorageService)
    service.account_name = "pesotest"
    service.account_url = "https://pesotest.blob.core.windows.net"
    service.container_name = "source-videos"
    service.service = MagicMock()
    service.container = MagicMock()
    key = UserDelegationKey()
    key.signed_oid = "11111111-1111-1111-1111-111111111111"
    key.signed_tid = "22222222-2222-2222-2222-222222222222"
    key.signed_start = "2026-09-03T00:00:00Z"
    key.signed_expiry = "2026-09-04T00:00:00Z"
    key.signed_service = "b"
    key.signed_version = "2023-11-03"
    key.value = base64.b64encode(b"offline-test-key-not-a-cloud-credential").decode()
    service.service.get_user_delegation_key.return_value = key
    return service

  def test_upload_sas_is_exact_blob_https_create_only_without_overwrite(self):
    storage = self.storage()
    url = storage.create_write_sas("owner/source/video.mp4", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    self.assertEqual(parsed.path, "/source-videos/owner/source/video.mp4")
    self.assertEqual(query["sp"], ["c"])
    self.assertEqual(query["spr"], ["https"])
    self.assertEqual(query["sr"], ["b"])
    self.assertNotIn("w", query["sp"][0])
    self.assertIn("skoid", query)

  def test_playback_sas_has_only_read_permission(self):
    url = self.storage().create_read_sas("owner/source/video.mp4", expires_in=300)
    query = parse_qs(urlparse(url).query)
    self.assertEqual(query["sp"], ["r"])
    self.assertEqual(query["spr"], ["https"])

  def test_cleanup_is_idempotent_but_does_not_hide_delete_failures(self):
    storage = self.storage()
    storage.container.delete_blob.side_effect = ResourceNotFoundError("missing")
    storage.delete("owner/source/video.mp4")
    storage.container.delete_blob.side_effect = HttpResponseError("denied")
    with self.assertRaises(HttpResponseError):
      storage.delete("owner/source/video.mp4")
