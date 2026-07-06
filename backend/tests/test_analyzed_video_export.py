from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status

from app.routes.videos import AnalyzedVideoExportRequest, export_analyzed_video
from app.services.analyzed_video_renderer import _resolve_ffmpeg_binary, render_analyzed_video


VIDEO_ID = UUID("11111111-1111-1111-1111-111111111111")
ANALYSIS_ID = UUID("22222222-2222-2222-2222-222222222222")
USER_ID = "33333333-3333-3333-3333-333333333333"


class AnalyzedVideoExportRouteTest(unittest.TestCase):
  def _repository(self) -> MagicMock:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
      "save_state": "saved",
    }
    repository.get_analysis_result.return_value = {
      "id": str(ANALYSIS_ID),
      "model_version": "test-model",
        "result_json": {
          "video_id": str(VIDEO_ID),
          "poseFrames": [
            {
              "time": 0,
              "keypoints": [
                {"name": "left_shoulder", "x": 0.5, "y": 0.2, "confidence": 0.9},
              ],
            }
          ],
          "barbellPath": {
            "available": True,
            "points": [
              {"time": 0, "x": 0.4, "y": 0.3, "confidence": 0.9},
              {"time": 0.2, "x": 0.5, "y": 0.4, "confidence": 0.9},
            ],
          },
          "diagnostics": {},
        },
    }
    return repository

  def test_export_rejects_missing_or_unauthorized_video(self) -> None:
    repository = self._repository()
    repository.require_owned_video.side_effect = HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="Video not found.",
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService"),
      self.assertRaises(HTTPException) as raised,
    ):
      export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    self.assertEqual(raised.exception.status_code, status.HTTP_404_NOT_FOUND)

  def test_export_rejects_video_without_analysis(self) -> None:
    repository = self._repository()
    repository.get_analysis_result.return_value = None

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService"),
      self.assertRaises(HTTPException) as raised,
    ):
      export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    self.assertEqual(raised.exception.status_code, status.HTTP_404_NOT_FOUND)
    self.assertEqual(raised.exception.detail, "Analysis result not available for export.")

  def test_export_rejects_unsaved_video(self) -> None:
    repository = self._repository()
    repository.require_owned_video.return_value["save_state"] = "pending"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService"),
      self.assertRaises(HTTPException) as raised,
    ):
      export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    self.assertEqual(raised.exception.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(raised.exception.detail, "Only saved videos can be exported.")

  def test_export_rejects_pruned_source_video(self) -> None:
    repository = self._repository()
    repository.require_owned_video.return_value["storage_state"] = "pruned"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService"),
      self.assertRaises(HTTPException) as raised,
    ):
      export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    self.assertEqual(raised.exception.status_code, status.HTTP_409_CONFLICT)
    self.assertEqual(
      raised.exception.detail,
      "The source video has expired. Analysis is still available, but export is unavailable.",
    )

  def test_export_reuses_existing_rendered_object(self) -> None:
    repository = self._repository()
    storage = MagicMock()
    storage.storage_path_exists.return_value = True
    storage.create_signed_url.return_value = "https://example.test/signed-export"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.annotate_analysis_freshness", side_effect=lambda result, analysis: result),
      patch("app.routes.videos.render_analyzed_video") as renderer,
    ):
      response = export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    expected_path = f"{USER_ID}/exports/{VIDEO_ID}-{ANALYSIS_ID}-pose-h264-v1.mp4"
    renderer.assert_not_called()
    storage.download_to_tempfile.assert_not_called()
    storage.upload_file.assert_not_called()
    storage.create_signed_url.assert_called_once_with(expected_path)
    self.assertEqual(response.storage_path, expected_path)
    self.assertEqual(response.export_url, "https://example.test/signed-export")

  def test_export_recreates_rendered_object_after_cleanup(self) -> None:
    repository = self._repository()
    storage = MagicMock()
    storage.storage_path_exists.return_value = False
    storage.download_to_tempfile.return_value = Path("/tmp/source.mp4")
    storage.create_signed_url.return_value = "https://example.test/signed-export"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.annotate_analysis_freshness", side_effect=lambda result, analysis: result),
      patch("app.routes.videos.render_analyzed_video") as renderer,
    ):
      response = export_analyzed_video(VIDEO_ID, user_id=USER_ID)

    expected_path = f"{USER_ID}/exports/{VIDEO_ID}-{ANALYSIS_ID}-pose-h264-v1.mp4"
    renderer.assert_called_once()
    storage.upload_file.assert_called_once()
    storage.create_signed_url.assert_called_once_with(expected_path)
    self.assertEqual(response.storage_path, expected_path)
    self.assertEqual(response.variant, "pose")

  def test_export_clean_returns_playback_url_without_rendering(self) -> None:
    repository = self._repository()
    repository.require_owned_video.return_value["playback_path"] = f"{USER_ID}/playback/{VIDEO_ID}.mp4"
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/clean"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.render_analyzed_video") as renderer,
    ):
      response = export_analyzed_video(
        VIDEO_ID,
        AnalyzedVideoExportRequest(pose=False, barbell=False),
        user_id=USER_ID,
      )

    expected_path = f"{USER_ID}/playback/{VIDEO_ID}.mp4"
    renderer.assert_not_called()
    storage.storage_path_exists.assert_not_called()
    storage.download_to_tempfile.assert_not_called()
    storage.upload_file.assert_not_called()
    storage.create_signed_url.assert_called_once_with(expected_path)
    self.assertEqual(response.storage_path, expected_path)
    self.assertEqual(response.variant, "clean")

  def test_export_uses_barbell_variant_cache_path(self) -> None:
    repository = self._repository()
    storage = MagicMock()
    storage.storage_path_exists.return_value = True
    storage.create_signed_url.return_value = "https://example.test/barbell"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.render_analyzed_video") as renderer,
    ):
      response = export_analyzed_video(
        VIDEO_ID,
        AnalyzedVideoExportRequest(pose=False, barbell=True),
        user_id=USER_ID,
      )

    expected_path = f"{USER_ID}/exports/{VIDEO_ID}-{ANALYSIS_ID}-barbell-h264-v1.mp4"
    renderer.assert_not_called()
    storage.create_signed_url.assert_called_once_with(expected_path)
    self.assertEqual(response.storage_path, expected_path)
    self.assertEqual(response.variant, "barbell")

  def test_export_uses_pose_barbell_variant_cache_path(self) -> None:
    repository = self._repository()
    storage = MagicMock()
    storage.storage_path_exists.return_value = True
    storage.create_signed_url.return_value = "https://example.test/both"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.render_analyzed_video") as renderer,
    ):
      response = export_analyzed_video(
        VIDEO_ID,
        AnalyzedVideoExportRequest(pose=True, barbell=True),
        user_id=USER_ID,
      )

    expected_path = f"{USER_ID}/exports/{VIDEO_ID}-{ANALYSIS_ID}-pose-barbell-h264-v1.mp4"
    renderer.assert_not_called()
    storage.create_signed_url.assert_called_once_with(expected_path)
    self.assertEqual(response.storage_path, expected_path)
    self.assertEqual(response.variant, "pose-barbell")


class AnalyzedVideoRendererTest(unittest.TestCase):
  def test_renderer_reports_missing_ffmpeg_binary(self) -> None:
    with (
      patch.dict("os.environ", {"FFMPEG_BINARY": "/definitely/missing/ffmpeg"}),
      self.assertRaisesRegex(RuntimeError, "FFmpeg binary configured by FFMPEG_BINARY was not found."),
    ):
      _resolve_ffmpeg_binary()

  def test_renderer_creates_output_file_with_pose_overlay(self) -> None:
    import cv2
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      source_path = Path(temp_dir) / "source.mp4"
      output_path = Path(temp_dir) / "output.mp4"
      writer = cv2.VideoWriter(
        str(source_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (160, 120),
      )

      for _ in range(5):
        writer.write(np.zeros((120, 160, 3), dtype=np.uint8))

      writer.release()

      render_analyzed_video(
        source_path=source_path,
        output_path=output_path,
        result_json={
          "cameraView": "side",
          "poseFrames": [
            {
              "time": 0,
              "keypoints": [
                {"name": "left_shoulder", "x": 0.5, "y": 0.2, "confidence": 0.9},
                {"name": "left_hip", "x": 0.52, "y": 0.45, "confidence": 0.9},
                {"name": "left_knee", "x": 0.48, "y": 0.65, "confidence": 0.9},
                {"name": "left_ankle", "x": 0.5, "y": 0.9, "confidence": 0.9},
              ],
            }
          ],
          "diagnostics": {
            "pose_validation": {
              "selected_side": "left",
            },
          },
        },
      )

      self.assertTrue(output_path.exists())
      self.assertGreater(output_path.stat().st_size, 0)

      capture = cv2.VideoCapture(str(output_path))
      success, frame = capture.read()
      capture.release()

      self.assertTrue(success)
      self.assertGreater(int(frame.sum()), 0)

      with open(output_path, "rb") as output_file:
        output_bytes = output_file.read()

      self.assertIn(b"avc1", output_bytes)

  def test_renderer_creates_output_file_with_barbell_overlay(self) -> None:
    import cv2
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      source_path = Path(temp_dir) / "source.mp4"
      output_path = Path(temp_dir) / "output.mp4"
      writer = cv2.VideoWriter(
        str(source_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (160, 120),
      )

      for _ in range(5):
        writer.write(np.zeros((120, 160, 3), dtype=np.uint8))

      writer.release()

      render_analyzed_video(
        source_path=source_path,
        output_path=output_path,
        result_json={
          "barbellPath": {
            "available": True,
            "points": [
              {"time": 0, "x": 0.25, "y": 0.3, "confidence": 0.9},
              {"time": 0.2, "x": 0.35, "y": 0.4, "confidence": 0.9},
              {"time": 0.4, "x": 0.45, "y": 0.5, "confidence": 0.9},
            ],
          },
        },
        include_pose=False,
        include_barbell=True,
      )

      self.assertTrue(output_path.exists())
      self.assertGreater(output_path.stat().st_size, 0)

      capture = cv2.VideoCapture(str(output_path))
      success, frame = capture.read()
      capture.release()

      self.assertTrue(success)
      self.assertGreater(int(frame.sum()), 0)


if __name__ == "__main__":
  unittest.main()
