from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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
  HTTP_500_INTERNAL_SERVER_ERROR=500,
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

from app.services.storage_service import (
  StorageService,
  _has_expected_video_signature,
  _validate_video_stream,
)


class StorageServiceTest(unittest.TestCase):
  def _service(self, object_info: dict[str, object]) -> StorageService:
    service = object.__new__(StorageService)
    service.get_object_info = MagicMock(return_value=object_info)
    service.create_signed_url = MagicMock(return_value="https://storage.example.test/signed")
    service.remove_tempfile = StorageService.remove_tempfile.__get__(service, StorageService)
    service.max_video_upload_bytes = 50 * 1024 * 1024
    service.download_signed_url_ttl_seconds = 120
    service.download_timeout_seconds = 60
    service.ffprobe_timeout_seconds = 30
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

  def test_video_signature_accepts_webm_and_ios_compatible_containers(self) -> None:
    self.assertTrue(_has_expected_video_signature("user/uploads/recording.webm", b"\x1a\x45\xdf\xa3\x93B\x82\x84webm"))
    self.assertTrue(_has_expected_video_signature("user/uploads/recording.mov", b"\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00"))

  def test_video_stream_validation_uses_devnull_without_ffprobe_nostdin_option(self) -> None:
    with (
      patch("app.services.storage_service.shutil.which", return_value="/usr/bin/ffprobe"),
      patch(
        "app.services.storage_service.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
      ) as run,
    ):
      _validate_video_stream(Path("/tmp/recording.mov"), 30)

    command = run.call_args.args[0]
    self.assertNotIn("-nostdin", command)
    self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
    self.assertEqual(command[command.index("-protocol_whitelist") + 1], "file,pipe")

  @unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg and ffprobe are required for media validation",
  )
  def test_video_stream_validation_accepts_generated_mov_fixture(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      fixture = Path(temp_dir) / "regression.MOV"
      subprocess.run(
        [
          shutil.which("ffmpeg"),
          "-v",
          "error",
          "-f",
          "lavfi",
          "-i",
          "color=c=black:s=16x16:d=0.1",
          "-c:v",
          "mpeg4",
          "-an",
          str(fixture),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
      )

      self.assertGreater(fixture.stat().st_size, 0)
      _validate_video_stream(fixture, 30)

  def test_video_stream_validation_reports_backend_failures(self) -> None:
    with patch("app.services.storage_service.shutil.which", return_value=None):
      with self.assertRaises(HTTPException) as missing:
        _validate_video_stream(Path("/tmp/recording.mov"), 30)

    self.assertEqual(missing.exception.status_code, 500)

    for failure in (
      OSError("unable to start ffprobe"),
      subprocess.TimeoutExpired(["ffprobe"], 30),
    ):
      with self.subTest(failure=type(failure).__name__):
        with (
          patch("app.services.storage_service.shutil.which", return_value="/usr/bin/ffprobe"),
          patch("app.services.storage_service.subprocess.run", side_effect=failure),
        ):
          with self.assertRaises(HTTPException) as raised:
            _validate_video_stream(Path("/tmp/recording.mov"), 30)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("temporarily unavailable", raised.exception.detail)

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
        yield b"\x00\x00\x00\x18ftypisom"
        yield b"\x00\x00\x00\x00"

    class FakeStream:
      def __enter__(self):
        return FakeResponse()

      def __exit__(self, *_args):
        return False

    http_client = MagicMock()
    http_client.stream.return_value = FakeStream()

    with (
      patch("app.services.storage_service.get_pooled_http_client", return_value=http_client),
      patch(
        "app.services.storage_service.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
      ),
    ):
      temp_path = service.download_to_tempfile("user/uploads/recording.mp4")

    try:
      self.assertEqual(Path(temp_path).read_bytes(), b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
      http_client.stream.assert_called_once_with(
        "GET",
        "https://storage.example.test/signed",
        timeout=60,
        follow_redirects=True,
      )
      storage_client.storage.from_.return_value.download.assert_not_called()
    finally:
      service.remove_tempfile(temp_path)

  def test_download_to_tempfile_rejects_non_video_bytes_with_video_metadata(self) -> None:
    object_info = {
      "metadata": {
        "mimetype": "video/mp4",
        "size": "20",
      }
    }
    service = self._service(object_info)

    class FakeResponse:
      def raise_for_status(self) -> None:
        return None

      def iter_bytes(self):
        yield b"<?php echo 'not a video';"

    class FakeStream:
      def __enter__(self):
        return FakeResponse()

      def __exit__(self, *_args):
        return False

    http_client = MagicMock()
    http_client.stream.return_value = FakeStream()

    with patch("app.services.storage_service.get_pooled_http_client", return_value=http_client):
      with self.assertRaises(HTTPException) as raised:
        service.download_to_tempfile("user/uploads/not-a-video.mp4")

    self.assertEqual(raised.exception.status_code, 400)
    self.assertIn("contents do not match", raised.exception.detail)

  def test_download_to_tempfile_rejects_a_fake_mp4_header_without_a_video_stream(self) -> None:
    object_info = {
      "metadata": {
        "mimetype": "video/mp4",
        "size": "18",
      }
    }
    service = self._service(object_info)

    class FakeResponse:
      def raise_for_status(self) -> None:
        return None

      def iter_bytes(self):
        yield b"AAAAftypnot-a-video"

    class FakeStream:
      def __enter__(self):
        return FakeResponse()

      def __exit__(self, *_args):
        return False

    http_client = MagicMock()
    http_client.stream.return_value = FakeStream()

    with (
      patch("app.services.storage_service.get_pooled_http_client", return_value=http_client),
      patch(
        "app.services.storage_service.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="", stderr="Invalid data found"),
      ),
    ):
      with self.assertRaises(HTTPException) as raised:
        service.download_to_tempfile("user/uploads/fake.mp4")

    self.assertEqual(raised.exception.status_code, 400)
    self.assertIn("valid video stream", raised.exception.detail)


if __name__ == "__main__":
  unittest.main()
