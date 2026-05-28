from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status

from app.routes.videos import _cleanup_storage_objects, cleanup_storage, list_saved_videos
from app.services.storage_service import StorageService


USER_ID = "33333333-3333-3333-3333-333333333333"
VIDEO_ID = "11111111-1111-1111-1111-111111111111"


class StorageCleanupTest(unittest.TestCase):
  def setUp(self) -> None:
    self.settings = MagicMock(export_storage_ttl_hours=6)
    self.settings_patcher = patch("app.routes.videos.get_settings", return_value=self.settings)
    self.settings_patcher.start()

  def tearDown(self) -> None:
    self.settings_patcher.stop()

  def _storage(self) -> MagicMock:
    storage = MagicMock()
    storage.get_object_info.side_effect = lambda path: {
      "name": path,
      "metadata": {"size": 10},
    }
    return storage

  def _repository(self) -> MagicMock:
    repository = MagicMock()
    repository.list_expired_pending_videos.return_value = []
    repository.list_expired_saved_videos_with_media.return_value = []
    repository.list_storage_reference_paths.return_value = set()
    return repository

  def test_cleanup_deletes_expired_pending_uploads_and_rows(self) -> None:
    repository = self._repository()
    repository.list_expired_pending_videos.return_value = [
      {
        "id": VIDEO_ID,
        "user_id": USER_ID,
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
      }
    ]
    storage = self._storage()
    storage.list_objects_recursive.return_value = []

    response = _cleanup_storage_objects(repository, storage)

    storage.delete_storage_paths.assert_called_once_with([
      f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
      f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
    ])
    storage.delete_storage_prefix.assert_called_once_with(f"{USER_ID}/exports/{VIDEO_ID}-")
    repository.delete_video_with_analysis.assert_called_once_with(VIDEO_ID)
    self.assertEqual(response.pending_deleted, 1)
    self.assertEqual(response.bytes_deleted, 20)

  def test_cleanup_prunes_expired_saved_media_without_deleting_analysis(self) -> None:
    repository = self._repository()
    repository.list_expired_saved_videos_with_media.return_value = [
      {
        "id": VIDEO_ID,
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
      }
    ]
    storage = self._storage()
    storage.list_objects_recursive.return_value = []

    response = _cleanup_storage_objects(repository, storage)

    storage.delete_storage_paths.assert_called_once_with([f"{USER_ID}/uploads/{VIDEO_ID}.mp4"])
    repository.update_video.assert_called_once()
    update_fields = repository.update_video.call_args.args[1]
    self.assertEqual(update_fields["storage_state"], "pruned")
    self.assertIn("storage_pruned_at", update_fields)
    repository.delete_video_with_analysis.assert_not_called()
    self.assertEqual(response.saved_media_pruned, 1)
    self.assertEqual(response.bytes_deleted, 10)

  def test_cleanup_deletes_expired_exports_and_unreferenced_objects(self) -> None:
    repository = self._repository()
    repository.list_storage_reference_paths.return_value = {f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg"}
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    storage = self._storage()
    storage.list_objects_recursive.return_value = [
      {
        "path": f"{USER_ID}/exports/{VIDEO_ID}-analysis.mp4",
        "updated_at": old_timestamp,
        "metadata": {"size": 30},
      },
      {
        "path": f"{USER_ID}/playback/orphan.mp4",
        "updated_at": old_timestamp,
        "metadata": {"size": 40},
      },
      {
        "path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
        "updated_at": old_timestamp,
        "metadata": {"size": 5},
      },
    ]

    response = _cleanup_storage_objects(repository, storage)

    storage.delete_storage_paths.assert_any_call([f"{USER_ID}/exports/{VIDEO_ID}-analysis.mp4"])
    storage.delete_storage_paths.assert_any_call([f"{USER_ID}/playback/orphan.mp4"])
    self.assertEqual(response.exports_deleted, 1)
    self.assertEqual(response.orphans_deleted, 1)
    self.assertEqual(response.bytes_deleted, 70)

  def test_cleanup_route_requires_configured_token(self) -> None:
    settings = MagicMock(storage_cleanup_token="")

    with (
      patch("app.routes.videos.get_settings", return_value=settings),
      self.assertRaises(HTTPException) as raised,
    ):
      cleanup_storage("token")

    self.assertEqual(raised.exception.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

  def test_cleanup_route_rejects_invalid_token(self) -> None:
    settings = MagicMock(storage_cleanup_token="expected")

    with (
      patch("app.routes.videos.get_settings", return_value=settings),
      self.assertRaises(HTTPException) as raised,
    ):
      cleanup_storage("wrong")

    self.assertEqual(raised.exception.status_code, status.HTTP_403_FORBIDDEN)

  def test_delete_storage_paths_batches_supabase_removes(self) -> None:
    service = StorageService.__new__(StorageService)
    bucket = MagicMock()
    client = MagicMock()
    client.storage.from_.return_value = bucket
    service.client = client
    service.bucket = "videos"
    paths = [f"path-{index}" for index in range(1001)]

    service.delete_storage_paths(paths)

    self.assertEqual(bucket.remove.call_count, 2)
    self.assertEqual(len(bucket.remove.call_args_list[0].args[0]), 1000)
    self.assertEqual(len(bucket.remove.call_args_list[1].args[0]), 1)


class SavedVideoListRetentionTest(unittest.TestCase):
  def test_saved_list_returns_thumbnail_but_no_video_url_for_pruned_media(self) -> None:
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": VIDEO_ID,
        "exercise_type": "squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
        "save_state": "saved",
        "storage_state": "pruned",
        "saved_at": "2026-05-27T00:00:00+00:00",
        "created_at": "2026-05-27T00:00:00+00:00",
      }
    ]
    repository.get_analysis_result.return_value = None
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/thumb.jpg"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = list_saved_videos(USER_ID)

    self.assertIsNone(response[0].video_url)
    self.assertEqual(response[0].thumbnail_url, "https://example.test/thumb.jpg")
    self.assertEqual(response[0].storage_state, "pruned")
    storage.create_signed_url.assert_called_once_with(f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg")


if __name__ == "__main__":
  unittest.main()
