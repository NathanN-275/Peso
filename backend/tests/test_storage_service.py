from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

fake_fastapi = ModuleType("fastapi")


class FakeHTTPException(Exception):
  def __init__(self, *, status_code: int, detail: str) -> None:
    super().__init__(detail)
    self.status_code = status_code
    self.detail = detail


fake_fastapi.HTTPException = FakeHTTPException
fake_fastapi.status = SimpleNamespace(
  HTTP_400_BAD_REQUEST=400,
  HTTP_404_NOT_FOUND=404,
  HTTP_413_CONTENT_TOO_LARGE=413,
  HTTP_502_BAD_GATEWAY=502,
)
sys.modules.setdefault("fastapi", fake_fastapi)

fake_httpx = ModuleType("httpx")
fake_httpx.Client = object
fake_httpx.Limits = object
sys.modules.setdefault("httpx", fake_httpx)

fake_supabase = ModuleType("supabase")
fake_supabase.Client = object
fake_supabase.create_client = lambda *_args, **_kwargs: object()
sys.modules.setdefault("supabase", fake_supabase)

from fastapi import HTTPException

from app.services.storage_service import StorageService


class StorageServiceTest(unittest.TestCase):
  def _service(self, object_info: dict[str, object]) -> StorageService:
    service = object.__new__(StorageService)
    service.get_object_info = MagicMock(return_value=object_info)
    service.create_signed_url = MagicMock(return_value="https://storage.example.test/signed")
    service.remove_tempfile = StorageService.remove_tempfile.__get__(service, StorageService)
    service.max_video_upload_bytes = 50 * 1024 * 1024
    service.download_signed_url_ttl_seconds = 120
    service.download_timeout_seconds = 60
    return service

  def test_validate_video_object_accepts_browser_recorded_webm_with_codec_mime(self) -> None:
    object_info = {
      "metadata": {
        "mimetype": "video/webm;codecs=vp9",
        "size": "1024",
      }
    }
    service = self._service(object_info)

    result = service.validate_video_object("user/uploads/recording.webm")

    self.assertEqual(result, object_info)

  def test_validate_video_object_rejects_invalid_mime_type(self) -> None:
    service = self._service({"metadata": {"mimetype": "text/plain", "size": "1024"}})

    with self.assertRaises(HTTPException) as raised:
      service.validate_video_object("user/uploads/not-video.mp4")

    self.assertEqual(raised.exception.status_code, 400)

  def test_validate_video_object_rejects_oversized_video(self) -> None:
    service = self._service({"metadata": {"mimetype": "video/mp4", "size": str(51 * 1024 * 1024)}})

    with self.assertRaises(HTTPException) as raised:
      service.validate_video_object("user/uploads/large.mp4")

    self.assertEqual(raised.exception.status_code, 413)

  def test_download_to_tempfile_streams_signed_url(self) -> None:
    object_info = {
      "metadata": {
        "mimetype": "video/mp4",
        "size": "4",
      }
    }
    service = self._service(object_info)
    storage_client = MagicMock()
    service.client = storage_client

    class FakeResponse:
      def raise_for_status(self) -> None:
        return None

      def iter_bytes(self):
        yield b"ab"
        yield b"cd"

    class FakeStream:
      def __enter__(self):
        return FakeResponse()

      def __exit__(self, *_args):
        return False

    http_client = MagicMock()
    http_client.stream.return_value = FakeStream()

    with patch("app.services.storage_service.get_pooled_http_client", return_value=http_client):
      temp_path = service.download_to_tempfile("user/uploads/recording.mp4")

    try:
      self.assertEqual(Path(temp_path).read_bytes(), b"abcd")
      http_client.stream.assert_called_once_with(
        "GET",
        "https://storage.example.test/signed",
        timeout=60,
        follow_redirects=True,
      )
      storage_client.storage.from_.return_value.download.assert_not_called()
    finally:
      service.remove_tempfile(temp_path)


if __name__ == "__main__":
  unittest.main()
