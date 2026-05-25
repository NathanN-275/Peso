from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.analysis.pipeline import _finalize_storage_assets


VIDEO_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "33333333-3333-3333-3333-333333333333"
ORIGINAL_PATH = f"{USER_ID}/uploads/{VIDEO_ID}.mov"
THUMBNAIL_PATH = f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg"
PLAYBACK_PATH = f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4"


class VideoAssetFinalizationTest(unittest.TestCase):
  def _video(self) -> dict[str, str]:
    return {
      "id": VIDEO_ID,
      "user_id": USER_ID,
      "storage_path": ORIGINAL_PATH,
    }

  def test_skips_playback_and_original_delete_when_thumbnail_save_fails(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.analysis.pipeline.create_video_thumbnail", side_effect=RuntimeError("thumbnail failed")),
      patch("app.analysis.pipeline.compress_video_for_playback") as compress_video,
    ):
      _finalize_storage_assets(
        video=self._video(),
        video_id=VIDEO_ID,
        source_path=Path("/tmp/source.mov"),
        repository=repository,
        storage=storage,
      )

    compress_video.assert_not_called()
    storage.delete_storage_path.assert_not_called()
    repository.update_video.assert_not_called()

  def test_does_not_delete_original_when_playback_compression_fails(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.analysis.pipeline.create_video_thumbnail"),
      patch("app.analysis.pipeline.compress_video_for_playback", side_effect=RuntimeError("compression failed")),
    ):
      _finalize_storage_assets(
        video=self._video(),
        video_id=VIDEO_ID,
        source_path=Path("/tmp/source.mov"),
        repository=repository,
        storage=storage,
    )

    repository.update_video.assert_called_once_with(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    storage.delete_storage_path.assert_not_called()

  def test_deletes_original_after_thumbnail_and_playback_metadata_are_saved(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.analysis.pipeline.create_video_thumbnail"),
      patch("app.analysis.pipeline.compress_video_for_playback"),
    ):
      _finalize_storage_assets(
        video=self._video(),
        video_id=VIDEO_ID,
        source_path=Path("/tmp/source.mov"),
        repository=repository,
        storage=storage,
      )

    repository.update_video.assert_any_call(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    playback_update = repository.update_video.call_args_list[1].args
    self.assertEqual(playback_update[0], VIDEO_ID)
    self.assertEqual(playback_update[1]["playback_path"], PLAYBACK_PATH)
    self.assertEqual(playback_update[1]["original_storage_path"], ORIGINAL_PATH)
    storage.delete_storage_path.assert_called_once_with(ORIGINAL_PATH)

  def test_deletes_uploaded_playback_when_metadata_update_fails(self) -> None:
    repository = MagicMock()
    repository.update_video.side_effect = [
      {"thumbnail_path": THUMBNAIL_PATH},
      RuntimeError("missing playback_path column"),
    ]
    storage = MagicMock()

    with (
      patch("app.analysis.pipeline.create_video_thumbnail"),
      patch("app.analysis.pipeline.compress_video_for_playback"),
    ):
      _finalize_storage_assets(
        video=self._video(),
        video_id=VIDEO_ID,
        source_path=Path("/tmp/source.mov"),
        repository=repository,
        storage=storage,
      )

    storage.delete_storage_path.assert_called_once_with(PLAYBACK_PATH)


if __name__ == "__main__":
  unittest.main()
