from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

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

    with patch("app.services.storage_service.httpx.stream", return_value=FakeStream()) as stream:
      temp_path = service.download_to_tempfile("user/uploads/recording.mp4")

    try:
      self.assertEqual(Path(temp_path).read_bytes(), b"abcd")
      stream.assert_called_once_with(
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
