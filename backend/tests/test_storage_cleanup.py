from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException, status

from app.routes.videos import _authorize_cleanup
from app.services.config import Settings
from app.services.storage_cleanup import StorageCleanupService


NOW = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
USER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_USER_ID = "44444444-4444-4444-4444-444444444444"


def iso_hours_ago(hours: int) -> str:
  return (NOW - timedelta(hours=hours)).isoformat()


def settings(**overrides) -> Settings:
  defaults = {
    "backend_env": "test",
    "supabase_url": "https://example.supabase.co",
    "supabase_service_role_key": "service-role",
    "supabase_jwt_secret": "secret",
    "cleanup_job_token": "cleanup-secret",
    "export_cache_ttl_hours": 24,
    "orphan_storage_min_age_hours": 24,
    "stale_processing_hours": 6,
  }
  defaults.update(overrides)
  return Settings(**defaults)


def storage_object(path: str, size_bytes: int, hours_old: int) -> dict:
  return {
    "path": path,
    "name": path.rsplit("/", 1)[-1],
    "id": path,
    "created_at": iso_hours_ago(hours_old),
    "updated_at": iso_hours_ago(hours_old),
    "metadata": {
      "size": size_bytes,
    },
  }


def video(
  video_id: str,
  *,
  user_id: str = USER_ID,
  status_value: str = "completed",
  save_state: str = "pending",
  storage_path: str | None = None,
  thumbnail_path: str | None = None,
  updated_hours_ago: int = 30,
) -> dict:
  return {
    "id": video_id,
    "user_id": user_id,
    "status": status_value,
    "save_state": save_state,
    "storage_path": storage_path or f"{user_id}/{video_id}.mp4",
    "thumbnail_path": thumbnail_path,
    "created_at": iso_hours_ago(updated_hours_ago),
    "updated_at": iso_hours_ago(updated_hours_ago),
    "expires_at": iso_hours_ago(1),
  }


class FakeRepository:
  def __init__(
    self,
    *,
    expired_videos: list[dict] | None = None,
    stale_videos: list[dict] | None = None,
    referenced_videos: list[dict] | None = None,
  ) -> None:
    self.expired_videos = expired_videos or []
    self.stale_videos = stale_videos or []
    self.referenced_videos = referenced_videos or []
    self.deleted_video_ids: list[str] = []

  def list_expired_pending_videos(self) -> list[dict]:
    return self.expired_videos

  def list_stale_pending_in_progress_videos(self, cutoff_iso: str) -> list[dict]:
    self.stale_cutoff_iso = cutoff_iso
    return self.stale_videos

  def list_storage_referenced_videos(self) -> list[dict]:
    return self.referenced_videos

  def delete_video_with_analysis(self, video_id: str) -> None:
    self.deleted_video_ids.append(video_id)

  def mark_discarded(self, video_id: str) -> None:
    self.deleted_video_ids.append(video_id)


class FakeStorage:
  def __init__(self, storage_objects: list[dict] | None = None) -> None:
    self.storage_objects = storage_objects or []
    self.deleted_paths: list[str] = []

  def list_storage_objects_recursive(self) -> list[dict]:
    return self.storage_objects

  def delete_storage_path(self, storage_path: str) -> None:
    self.deleted_paths.append(storage_path)


class StorageCleanupServiceTest(unittest.TestCase):
  def test_expired_pending_video_cleanup_deletes_storage_exports_and_row(self) -> None:
    video_id = "11111111-1111-1111-1111-111111111111"
    source_path = f"{USER_ID}/{video_id}.mp4"
    thumbnail_path = f"{USER_ID}/{video_id}.jpg"
    export_path = f"{USER_ID}/exports/{video_id}-22222222-2222-2222-2222-222222222222-h264-v1.mp4"
    repository = FakeRepository(
      expired_videos=[
        video(video_id, storage_path=source_path, thumbnail_path=thumbnail_path),
      ],
      referenced_videos=[
        video(video_id, storage_path=source_path, thumbnail_path=thumbnail_path),
      ],
    )
    storage = FakeStorage(
      [
        storage_object(source_path, 100, 30),
        storage_object(thumbnail_path, 10, 30),
        storage_object(export_path, 50, 30),
      ]
    )

    report = StorageCleanupService(repository, storage, settings()).run(now=NOW)

    self.assertEqual(report.deleted_count, 1)
    self.assertEqual(report.expired_pending_videos, 1)
    self.assertEqual(report.stale_pending_videos, 0)
    self.assertEqual(report.storage_objects, 3)
    self.assertEqual(report.bytes_reclaimable, 160)
    self.assertEqual(repository.deleted_video_ids, [video_id])
    self.assertCountEqual(storage.deleted_paths, [source_path, thumbnail_path, export_path])

  def test_saved_video_is_never_deleted_even_if_returned_as_expired(self) -> None:
    video_id = "11111111-1111-1111-1111-111111111111"
    source_path = f"{USER_ID}/{video_id}.mp4"
    repository = FakeRepository(
      expired_videos=[
        video(video_id, save_state="saved", storage_path=source_path),
      ],
      referenced_videos=[
        video(video_id, save_state="saved", storage_path=source_path),
      ],
    )
    storage = FakeStorage([storage_object(source_path, 100, 30)])

    report = StorageCleanupService(repository, storage, settings()).run(now=NOW)

    self.assertEqual(report.deleted_count, 0)
    self.assertEqual(report.storage_objects, 0)
    self.assertEqual(repository.deleted_video_ids, [])
    self.assertEqual(storage.deleted_paths, [])

  def test_active_in_progress_video_is_skipped_but_stale_pending_video_is_deleted(self) -> None:
    active_id = "11111111-1111-1111-1111-111111111111"
    stale_id = "22222222-2222-2222-2222-222222222222"
    active_path = f"{USER_ID}/{active_id}.mp4"
    stale_path = f"{USER_ID}/{stale_id}.mp4"
    repository = FakeRepository(
      expired_videos=[
        video(active_id, status_value="queued", storage_path=active_path, updated_hours_ago=1),
      ],
      stale_videos=[
        video(stale_id, status_value="processing", storage_path=stale_path, updated_hours_ago=7),
      ],
      referenced_videos=[
        video(active_id, status_value="queued", storage_path=active_path, updated_hours_ago=1),
        video(stale_id, status_value="processing", storage_path=stale_path, updated_hours_ago=7),
      ],
    )
    storage = FakeStorage(
      [
        storage_object(active_path, 100, 1),
        storage_object(stale_path, 200, 7),
      ]
    )

    report = StorageCleanupService(repository, storage, settings()).run(now=NOW)

    self.assertEqual(report.deleted_count, 1)
    self.assertEqual(report.expired_pending_videos, 0)
    self.assertEqual(report.stale_pending_videos, 1)
    self.assertEqual(repository.deleted_video_ids, [stale_id])
    self.assertEqual(storage.deleted_paths, [stale_path])

  def test_old_exports_are_temporary_and_regenerated_on_demand(self) -> None:
    old_export = f"{USER_ID}/exports/11111111-1111-1111-1111-111111111111-analysis-h264-v1.mp4"
    fresh_export = f"{USER_ID}/exports/22222222-2222-2222-2222-222222222222-analysis-h264-v1.mp4"
    repository = FakeRepository()
    storage = FakeStorage(
      [
        storage_object(old_export, 100, 25),
        storage_object(fresh_export, 200, 1),
      ]
    )

    report = StorageCleanupService(repository, storage, settings()).run(now=NOW)

    self.assertEqual(report.deleted_count, 0)
    self.assertEqual(report.old_export_objects, 1)
    self.assertEqual(report.storage_objects, 1)
    self.assertEqual(report.bytes_reclaimable, 100)
    self.assertEqual(storage.deleted_paths, [old_export])

  def test_orphan_cleanup_deletes_only_unreferenced_old_app_uploads(self) -> None:
    referenced_path = f"{USER_ID}/referenced.mp4"
    orphan_path = f"{USER_ID}/orphan.mp4"
    fresh_orphan_path = f"{USER_ID}/fresh-orphan.mp4"
    non_app_path = "public/manual-upload.mp4"
    repository = FakeRepository(
      referenced_videos=[
        video("11111111-1111-1111-1111-111111111111", storage_path=referenced_path),
      ]
    )
    storage = FakeStorage(
      [
        storage_object(referenced_path, 100, 30),
        storage_object(orphan_path, 200, 30),
        storage_object(fresh_orphan_path, 300, 1),
        storage_object(non_app_path, 400, 30),
      ]
    )

    report = StorageCleanupService(repository, storage, settings()).run(now=NOW)

    self.assertEqual(report.orphan_objects, 1)
    self.assertEqual(report.storage_objects, 1)
    self.assertEqual(report.bytes_reclaimable, 200)
    self.assertEqual(storage.deleted_paths, [orphan_path])

  def test_dry_run_reports_reclaimable_storage_without_deleting(self) -> None:
    video_id = "11111111-1111-1111-1111-111111111111"
    source_path = f"{USER_ID}/{video_id}.mp4"
    repository = FakeRepository(
      expired_videos=[
        video(video_id, storage_path=source_path),
      ],
      referenced_videos=[
        video(video_id, storage_path=source_path),
      ],
    )
    storage = FakeStorage([storage_object(source_path, 100, 30)])

    report = StorageCleanupService(repository, storage, settings()).run(dry_run=True, now=NOW)

    self.assertTrue(report.dry_run)
    self.assertEqual(report.deleted_count, 0)
    self.assertEqual(report.expired_pending_videos, 1)
    self.assertEqual(report.storage_objects, 1)
    self.assertEqual(report.bytes_reclaimable, 100)
    self.assertEqual(repository.deleted_video_ids, [])
    self.assertEqual(storage.deleted_paths, [])


class CleanupRouteAuthorizationTest(unittest.TestCase):
  def test_cleanup_token_is_required_outside_development(self) -> None:
    with patch("app.routes.videos.get_settings", return_value=settings(backend_env="production")):
      with self.assertRaises(HTTPException) as raised:
        _authorize_cleanup(None)

    self.assertEqual(raised.exception.status_code, status.HTTP_401_UNAUTHORIZED)

  def test_cleanup_token_allows_production_cleanup(self) -> None:
    with patch("app.routes.videos.get_settings", return_value=settings(backend_env="production")):
      _authorize_cleanup("cleanup-secret")

  def test_cleanup_token_is_not_required_in_development(self) -> None:
    with patch("app.routes.videos.get_settings", return_value=settings(backend_env="development")):
      _authorize_cleanup(None)


if __name__ == "__main__":
  unittest.main()
