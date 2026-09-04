from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routes.budget_admission import disable_budget_admission
from app.routes.upload_reservations import (
  CreateUploadReservationRequest,
  complete_upload_reservation,
  create_upload_reservation,
)
from app.services.config import Settings
from app.services.media_metadata import (
  MediaValidationError,
  VideoMetadata,
  enforce_video_limits,
  probe_video_metadata,
)
from app.services.security_logging import redact_sensitive_text


USER_ID = "33333333-3333-3333-3333-333333333333"
RESERVATION_ID = UUID("11111111-1111-1111-1111-111111111111")
VIDEO_ID = "22222222-2222-2222-2222-222222222222"
SETTINGS = Settings(
  backend_env="test", supabase_url="https://example.supabase.co",
  supabase_service_role_key="test", supabase_jwt_secret="test",
  upload_reservations_enabled=True,
)
VALID_METADATA = VideoMetadata(1000, 1920, 1080, 60, 60, "h264", "mov,mp4,m4a,3gp,3g2,mj2")


class MediaMetadataTest(unittest.TestCase):
  def enforce(self, metadata: VideoMetadata) -> None:
    enforce_video_limits(metadata, max_duration_ms=300000, max_width=1920, max_height=1080, max_fps=60)

  def test_beta_limits_accept_landscape_and_portrait(self) -> None:
    self.enforce(VALID_METADATA)
    self.enforce(replace(VALID_METADATA, width=1080, height=1920))

  def test_limits_reject_long_small_high_resolution_and_high_fps_media(self) -> None:
    for metadata, code in [
      (replace(VALID_METADATA, duration_ms=300001), "duration_limit"),
      (replace(VALID_METADATA, width=3840, height=2160), "dimension_limit"),
      (replace(VALID_METADATA, fps=120), "frame_rate_limit"),
      (replace(VALID_METADATA, frame_count=18001), "frame_count_limit"),
    ]:
      with self.subTest(code=code), self.assertRaises(MediaValidationError) as error:
        self.enforce(metadata)
      self.assertEqual(error.exception.code, code)

  def test_probe_counts_actual_frames_with_network_protocols_disabled(self) -> None:
    payload = {
      "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                   "avg_frame_rate": "60000/1001", "nb_read_frames": "60"}],
      "format": {"duration": "1.001", "format_name": "mov,mp4"},
    }
    with patch("app.services.media_metadata.shutil.which", return_value="/usr/bin/ffprobe"), patch(
      "app.services.media_metadata.subprocess.run",
      return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    ) as run:
      metadata = probe_video_metadata(Path("/tmp/test.mp4"), timeout_seconds=30)
    self.assertEqual(metadata.frame_count, 60)
    self.assertEqual(metadata.duration_ms, 1001)
    self.assertIn("-count_frames", run.call_args.args[0])
    self.assertIn("file,pipe", run.call_args.args[0])

  def test_probe_rejects_missing_or_malformed_metadata(self) -> None:
    for output in ("not-json", "{}", '{"streams":[],"format":{}}'):
      with self.subTest(output=output), patch("app.services.media_metadata.shutil.which", return_value="ffprobe"), patch(
        "app.services.media_metadata.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=output),
      ), self.assertRaises(MediaValidationError):
        probe_video_metadata(Path("/tmp/test.mp4"), timeout_seconds=30)

  @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required.")
  def test_real_long_but_small_video_is_rejected_from_actual_metadata(self) -> None:
    with TemporaryDirectory() as directory:
      video = Path(directory) / "long-small.mp4"
      subprocess.run(
        [shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
         "color=c=black:s=16x16:r=1:d=301", "-c:v", "mpeg4", "-an", str(video)],
        stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30,
      )
      self.assertLess(video.stat().st_size, 1024 * 1024)
      metadata = probe_video_metadata(video, timeout_seconds=30)
      self.assertGreater(metadata.duration_ms, 300000)
      with self.assertRaises(MediaValidationError) as error:
        self.enforce(metadata)
      self.assertEqual(error.exception.code, "duration_limit")


class UploadReservationRoutesTest(unittest.TestCase):
  def request(self, **changes):
    return CreateUploadReservationRequest(**{
      "file_name": "lift.mp4", "content_type": "video/mp4", "size_bytes": 100,
      "exercise_type": "Bench Press", "view_type": "Side", **changes,
    })

  def reservation(self, **changes):
    return {
      "id": str(RESERVATION_ID), "user_id": USER_ID,
      "blob_path": f"{USER_ID}/source/{RESERVATION_ID}.mp4", "state": "issued",
      "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
      "requested_bytes": 100, "content_type": "video/mp4", **changes,
    }

  def test_budget_shutdown_denies_before_reserving_or_signing(self) -> None:
    with patch("app.routes.upload_reservations.get_settings", return_value=replace(SETTINGS, upload_reservations_enabled=False)), patch(
      "app.routes.upload_reservations.UploadReservationRepository",
    ) as repository, patch("app.routes.upload_reservations.get_azure_blob_storage") as storage, self.assertRaises(HTTPException) as error:
      create_upload_reservation(self.request(), USER_ID)
    self.assertEqual(error.exception.status_code, 503)
    repository.assert_not_called()
    storage.assert_not_called()

  def test_capacity_is_reserved_before_a_sas_is_issued(self) -> None:
    events = []
    repository, storage = MagicMock(), MagicMock()
    repository.reserve.side_effect = lambda *_args: events.append("reserve") or {}
    storage.create_write_sas.side_effect = lambda *_args, **_kwargs: events.append("sign") or "https://example.invalid/upload"
    with patch("app.routes.upload_reservations.get_settings", return_value=SETTINGS), patch(
      "app.routes.upload_reservations.UploadReservationRepository", return_value=repository,
    ), patch("app.routes.upload_reservations.get_azure_blob_storage", return_value=storage):
      response = create_upload_reservation(self.request(), USER_ID)
    self.assertEqual(events, ["reserve", "sign"])
    self.assertTrue(response.blob_path.startswith(f"{USER_ID}/source/"))
    self.assertEqual(response.upload_headers["If-None-Match"], "*")
    self.assertEqual(repository.reserve.call_args.args[0]["requested_bytes"], 100)

  def test_expired_reservation_cannot_be_completed(self) -> None:
    repository, storage = MagicMock(), MagicMock()
    repository.require_owned.return_value = self.reservation(expires_at="2000-01-01T00:00:00+00:00")
    with patch("app.routes.upload_reservations.get_settings", return_value=SETTINGS), patch(
      "app.routes.upload_reservations.UploadReservationRepository", return_value=repository,
    ), patch("app.routes.upload_reservations.get_azure_blob_storage", return_value=storage), self.assertRaises(HTTPException) as error:
      complete_upload_reservation(RESERVATION_ID, USER_ID)
    self.assertEqual(error.exception.status_code, 410)
    repository.verify_and_create_video.assert_not_called()
    storage.delete.assert_called_once()

  def test_completion_rejects_actual_bytes_exceeding_reservation(self) -> None:
    repository, storage = MagicMock(), MagicMock()
    repository.require_owned.return_value = self.reservation()
    storage.get_object_info.return_value = {"size": 101, "contentType": "video/mp4"}
    with patch("app.routes.upload_reservations.get_settings", return_value=SETTINGS), patch(
      "app.routes.upload_reservations.UploadReservationRepository", return_value=repository,
    ), patch("app.routes.upload_reservations.get_azure_blob_storage", return_value=storage), self.assertRaises(HTTPException) as error:
      complete_upload_reservation(RESERVATION_ID, USER_ID)
    self.assertEqual(error.exception.status_code, 422)
    repository.reject.assert_called_once_with(str(RESERVATION_ID), USER_ID, "byte_limit")
    repository.verify_and_create_video.assert_not_called()

  def test_completion_uses_probed_duration_not_client_hint(self) -> None:
    repository, storage = MagicMock(), MagicMock()
    repository.require_owned.return_value = self.reservation(client_duration_ms=1)
    repository.verify_and_create_video.return_value = {"video_id": VIDEO_ID}
    data = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 88
    storage.get_object_info.return_value = {"size": len(data), "contentType": "video/mp4"}
    def download(_blob_path, destination, **_kwargs):
      destination.write_bytes(data)
      return len(data)
    storage.download_to_path.side_effect = download
    with patch("app.routes.upload_reservations.get_settings", return_value=SETTINGS), patch(
      "app.routes.upload_reservations.UploadReservationRepository", return_value=repository,
    ), patch("app.routes.upload_reservations.get_azure_blob_storage", return_value=storage), patch(
      "app.routes.upload_reservations.probe_video_metadata", return_value=VALID_METADATA,
    ):
      response = complete_upload_reservation(RESERVATION_ID, USER_ID)
    self.assertEqual(response.state, "verified")
    self.assertEqual(repository.verify_and_create_video.call_args.kwargs["metadata"]["duration_ms"], 1000)

  def test_budget_webhook_rejects_wrong_secret_and_persists_disable(self) -> None:
    settings = replace(SETTINGS, budget_shutdown_token="test-budget-token")
    client = MagicMock()
    with patch("app.routes.budget_admission.get_settings", return_value=settings), patch(
      "app.routes.budget_admission.get_supabase_admin_client", return_value=client,
    ):
      with self.assertRaises(HTTPException):
        disable_budget_admission("wrong")
      client.rpc.assert_not_called()
      self.assertEqual(disable_budget_admission("test-budget-token"), {"uploads_enabled": False})
    client.rpc.assert_called_once_with("disable_video_upload_admission", {})

  def test_logs_redact_signed_urls_and_bearer_tokens(self) -> None:
    value = redact_sensitive_text("https://blob.example/video?sig=secret&se=123 Bearer token-secret")
    self.assertNotIn("sig=secret", value)
    self.assertNotIn("token-secret", value)
