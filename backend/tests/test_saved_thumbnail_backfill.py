from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.saved_thumbnail_backfill import (
  backfill_saved_video_thumbnails,
  list_saved_thumbnail_backfill_candidates,
  video_needs_saved_thumbnail_backfill,
)


VIDEO_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "33333333-3333-3333-3333-333333333333"
SOURCE_PATH = f"{USER_ID}/uploads/{VIDEO_ID}.mov"
THUMBNAIL_PATH = f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg"


class SavedThumbnailBackfillTest(unittest.TestCase):
  def _video(self, **overrides: object) -> dict[str, object]:
    video: dict[str, object] = {
      "id": VIDEO_ID,
      "user_id": USER_ID,
      "storage_path": SOURCE_PATH,
      "save_state": "saved",
      "is_saved": True,
      "thumbnail_path": None,
      "discarded_at": None,
    }
    video.update(overrides)
    return video

  def test_candidate_filter_keeps_only_saved_videos_without_current_thumbnails(self) -> None:
    self.assertTrue(video_needs_saved_thumbnail_backfill(self._video()))
    self.assertTrue(video_needs_saved_thumbnail_backfill(self._video(save_state="pending", is_saved=True)))
    self.assertFalse(video_needs_saved_thumbnail_backfill(self._video(save_state="pending", is_saved=False)))
    self.assertTrue(video_needs_saved_thumbnail_backfill(self._video(thumbnail_path=f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v2.jpg")))
    self.assertFalse(video_needs_saved_thumbnail_backfill(self._video(thumbnail_path=THUMBNAIL_PATH)))
    self.assertTrue(video_needs_saved_thumbnail_backfill(self._video(thumbnail_path=THUMBNAIL_PATH), force=True))
    self.assertFalse(video_needs_saved_thumbnail_backfill(self._video(discarded_at="2026-05-25T12:00:00+00:00")))

  def test_lists_saved_thumbnail_candidates_from_repository(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[
        self._video(),
        self._video(id="22222222-2222-2222-2222-222222222222", thumbnail_path=THUMBNAIL_PATH),
        self._video(id="44444444-4444-4444-4444-444444444444", thumbnail_path=f"{USER_ID}/thumbnails/44444444-4444-4444-4444-444444444444-thumb-v2.jpg"),
        self._video(id="33333333-3333-3333-3333-333333333333", save_state="pending", is_saved=False),
      ]
    )

    candidates = list_saved_thumbnail_backfill_candidates(repository)

    self.assertEqual(
      [candidate["id"] for candidate in candidates],
      [VIDEO_ID, "44444444-4444-4444-4444-444444444444"],
    )

  def test_force_lists_saved_videos_even_when_thumbnail_exists(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[
        self._video(thumbnail_path=THUMBNAIL_PATH),
        self._video(id="33333333-3333-3333-3333-333333333333", save_state="pending", is_saved=False),
      ]
    )

    candidates = list_saved_thumbnail_backfill_candidates(repository, force=True)

    self.assertEqual([candidate["id"] for candidate in candidates], [VIDEO_ID])

  def test_dry_run_logs_candidates_without_downloading_or_updating(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[self._video()]
    )
    storage = MagicMock()

    result = backfill_saved_video_thumbnails(
      repository=repository,
      storage=storage,
      confirm=False,
    )

    self.assertTrue(result.dry_run)
    self.assertEqual(result.candidate_count, 1)
    self.assertEqual(result.generated_count, 0)
    storage.download_to_tempfile.assert_not_called()
    storage.upload_file.assert_not_called()
    storage.delete_storage_path.assert_not_called()
    repository.update_video.assert_not_called()

  def test_confirm_generates_one_thumbnail_and_updates_path(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[self._video()]
    )
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/source.mov"

    with patch("app.services.saved_thumbnail_backfill.create_video_thumbnail") as create_thumbnail:
      result = backfill_saved_video_thumbnails(
        repository=repository,
        storage=storage,
        confirm=True,
      )

    self.assertFalse(result.dry_run)
    self.assertEqual(result.candidate_count, 1)
    self.assertEqual(result.generated_count, 1)
    create_thumbnail.assert_called_once()
    storage.download_to_tempfile.assert_called_once_with(SOURCE_PATH)
    storage.upload_file.assert_called_once()
    self.assertEqual(storage.upload_file.call_args.args[0], THUMBNAIL_PATH)
    self.assertEqual(storage.upload_file.call_args.args[2], "image/jpeg")
    repository.update_video.assert_called_once_with(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    storage.delete_storage_path.assert_not_called()

  def test_confirm_preserves_saved_video_when_generation_fails(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[self._video()]
    )
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/source.mov"

    with patch(
      "app.services.saved_thumbnail_backfill.create_video_thumbnail",
      side_effect=RuntimeError("thumbnail failed"),
    ):
      result = backfill_saved_video_thumbnails(
        repository=repository,
        storage=storage,
        confirm=True,
      )

    self.assertEqual(result.failed_count, 1)
    storage.upload_file.assert_not_called()
    repository.update_video.assert_not_called()
    storage.delete_storage_path.assert_not_called()

  def test_confirm_deletes_uploaded_thumbnail_when_metadata_update_fails(self) -> None:
    repository = MagicMock()
    repository.client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
      data=[self._video()]
    )
    repository.update_video.side_effect = RuntimeError("missing thumbnail_path column")
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/source.mov"

    with patch("app.services.saved_thumbnail_backfill.create_video_thumbnail"):
      result = backfill_saved_video_thumbnails(
        repository=repository,
        storage=storage,
        confirm=True,
      )

    self.assertEqual(result.failed_count, 1)
    storage.upload_file.assert_called_once()
    repository.update_video.assert_called_once_with(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    storage.delete_storage_path.assert_called_once_with(THUMBNAIL_PATH)


if __name__ == "__main__":
  unittest.main()
