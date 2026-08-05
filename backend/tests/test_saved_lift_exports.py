from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from pydantic import ValidationError

from app.routes.saved_lift_exports import CreateSavedLiftExportRequest, create_saved_lift_export
from app.services.analyzed_video_exports import AnalyzedVideoArtifact
from app.services.config import Settings
from app.services.saved_lift_exports import SavedLiftExportService


USER_ID = "33333333-3333-3333-3333-333333333333"
VIDEO_ID_1 = "11111111-1111-1111-1111-111111111111"
VIDEO_ID_2 = "22222222-2222-2222-2222-222222222222"
JOB_ID = "55555555-5555-5555-5555-555555555555"


def settings(**overrides) -> Settings:
  values = {
    "backend_env": "test",
    "supabase_url": "https://example.supabase.co",
    "supabase_service_role_key": "service-role",
    "supabase_jwt_secret": "secret",
    "cleanup_job_token": "cleanup-secret",
    "export_cache_ttl_hours": 6,
    "signed_url_ttl_seconds": 300,
    "max_saved_lift_export_bytes": 50 * 1024 * 1024,
  }
  values.update(overrides)
  return Settings(**values)


def video(video_id: str, exercise: str = "squat") -> dict:
  return {
    "id": video_id,
    "user_id": USER_ID,
    "exercise_type": exercise,
    "storage_path": f"{USER_ID}/uploads/{video_id}.mp4",
    "playback_path": f"{USER_ID}/playback/{video_id}.mp4",
    "save_state": "saved",
    "discarded_at": None,
    "storage_state": "available",
  }


def analysis(video_id: str) -> dict:
  return {
    "id": f"{video_id[:24]}aaaaaaaaaaaa",
    "video_id": video_id,
    "model_version": "test-model",
    "result_json": {"poseFrames": [], "barbellPath": {"available": False}},
    "created_at": "2026-08-05T12:00:00+00:00",
  }


class SavedLiftExportServiceTest(unittest.TestCase):
  def _service(self, *, max_bytes: int | None = None):
    videos = MagicMock()
    jobs = MagicMock()
    video_storage = MagicMock()
    archive_storage = MagicMock()
    service = SavedLiftExportService(
      videos=videos,
      jobs=jobs,
      video_storage=video_storage,
      archive_storage=archive_storage,
      settings=settings(**({"max_saved_lift_export_bytes": max_bytes} if max_bytes else {})),
    )
    return service, videos, jobs, video_storage, archive_storage

  def test_create_job_deduplicates_selection_and_revalidates_every_lift(self) -> None:
    service, videos, jobs, _, _ = self._service()
    videos.get_owned_videos.return_value = [video(VIDEO_ID_1), video(VIDEO_ID_2, "deadlift")]
    videos.video_is_saved.return_value = True
    videos.get_latest_analysis_results.return_value = {
      VIDEO_ID_1: analysis(VIDEO_ID_1),
      VIDEO_ID_2: analysis(VIDEO_ID_2),
    }
    jobs.create.return_value = {"id": JOB_ID}

    result = service.create_job(USER_ID, [VIDEO_ID_1, VIDEO_ID_1, VIDEO_ID_2])

    self.assertEqual(result["id"], JOB_ID)
    videos.get_owned_videos.assert_called_once_with([VIDEO_ID_1, VIDEO_ID_2], USER_ID)
    jobs.create.assert_called_once_with(USER_ID, [VIDEO_ID_1, VIDEO_ID_2])

  def test_create_job_hides_missing_or_cross_owner_lifts(self) -> None:
    service, videos, jobs, _, _ = self._service()
    videos.get_owned_videos.return_value = [video(VIDEO_ID_1)]

    with self.assertRaises(HTTPException) as raised:
      service.create_job(USER_ID, [VIDEO_ID_1, VIDEO_ID_2])

    self.assertEqual(raised.exception.status_code, status.HTTP_404_NOT_FOUND)
    jobs.create.assert_not_called()

  def test_process_job_writes_each_selected_lift_once_in_one_zip(self) -> None:
    service, videos, jobs, video_storage, archive_storage = self._service()
    selected = [VIDEO_ID_1, VIDEO_ID_2]
    videos.get_owned_videos.return_value = [video(VIDEO_ID_1), video(VIDEO_ID_2, "deadlift")]
    videos.video_is_saved.return_value = True
    videos.get_latest_analysis_results.return_value = {
      VIDEO_ID_1: analysis(VIDEO_ID_1),
      VIDEO_ID_2: analysis(VIDEO_ID_2),
    }
    jobs.mark_processing.return_value = {"id": JOB_ID}
    jobs.require_owned.return_value = {
      "id": JOB_ID,
      "user_id": USER_ID,
      "video_ids": selected,
    }
    archive_storage.storage_path_exists.return_value = True
    archived_names: list[str] = []
    source_files: list[Path] = []

    def download(path: str) -> Path:
      temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
      temp.write(path.encode("utf-8"))
      temp.close()
      source_files.append(Path(temp.name))
      return Path(temp.name)

    def upload(_path: str, local_path: Path, _content_type: str) -> None:
      with zipfile.ZipFile(local_path) as archive:
        archived_names.extend(archive.namelist())

    video_storage.download_to_tempfile.side_effect = download
    video_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
    archive_storage.upload_file.side_effect = upload
    archive_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)

    with patch(
      "app.services.saved_lift_exports.ensure_analyzed_video_artifact",
      side_effect=lambda **kwargs: AnalyzedVideoArtifact(
        storage_path=f"{USER_ID}/exports/{kwargs['video']['id']}.mp4",
        variant="pose",
      ),
    ) as ensure_artifact:
      service.process_job(JOB_ID, USER_ID)

    self.assertEqual(ensure_artifact.call_count, 2)
    self.assertEqual(len(archived_names), 2)
    self.assertEqual(len(set(archived_names)), 2)
    self.assertTrue(archived_names[0].startswith("01-squat-"))
    self.assertTrue(archived_names[1].startswith("02-deadlift-"))
    archive_storage.upload_file.assert_called_once()
    jobs.mark_completed.assert_called_once()
    jobs.mark_failed.assert_not_called()
    self.assertTrue(all(not path.exists() for path in source_files))

  def test_process_job_records_oversized_bundle_as_failed(self) -> None:
    service, videos, jobs, video_storage, archive_storage = self._service(max_bytes=16)
    videos.get_owned_videos.return_value = [video(VIDEO_ID_1)]
    videos.video_is_saved.return_value = True
    videos.get_latest_analysis_results.return_value = {VIDEO_ID_1: analysis(VIDEO_ID_1)}
    jobs.mark_processing.return_value = {"id": JOB_ID}
    jobs.require_owned.return_value = {
      "id": JOB_ID,
      "user_id": USER_ID,
      "video_ids": [VIDEO_ID_1],
    }
    source = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    source.write(b"x" * 128)
    source.close()
    video_storage.download_to_tempfile.return_value = Path(source.name)
    video_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
    archive_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)

    with patch(
      "app.services.saved_lift_exports.ensure_analyzed_video_artifact",
      return_value=AnalyzedVideoArtifact(
        storage_path=f"{USER_ID}/exports/{VIDEO_ID_1}.mp4",
        variant="pose",
      ),
    ):
      service.process_job(JOB_ID, USER_ID)

    archive_storage.upload_file.assert_not_called()
    jobs.mark_completed.assert_not_called()
    jobs.mark_failed.assert_called_once_with(JOB_ID, "archive_too_large")

  def test_create_route_queues_processing_and_returns_owner_scoped_projection(self) -> None:
    service = MagicMock()
    service.create_job.return_value = {"id": JOB_ID}
    service.job_projection.return_value = {
      "id": JOB_ID,
      "status": "queued",
      "lift_ids": [VIDEO_ID_1, VIDEO_ID_2],
      "lift_count": 2,
      "created_at": "2026-08-05T12:00:00+00:00",
      "completed_at": None,
      "expires_at": None,
      "download_url": None,
      "download_expires_in": None,
      "failure_code": None,
    }
    background_tasks = BackgroundTasks()

    with patch("app.routes.saved_lift_exports.SavedLiftExportService", return_value=service):
      response = create_saved_lift_export(
        CreateSavedLiftExportRequest(
          lift_ids=[UUID(VIDEO_ID_1), UUID(VIDEO_ID_2)],
        ),
        background_tasks,
        USER_ID,
      )

    service.create_job.assert_called_once_with(USER_ID, [VIDEO_ID_1, VIDEO_ID_2])
    service.job_projection.assert_called_once_with(JOB_ID, USER_ID)
    self.assertEqual(response.status, "queued")
    self.assertEqual(len(background_tasks.tasks), 1)

  def test_create_route_rejects_unknown_fields(self) -> None:
    with self.assertRaises(ValidationError):
      CreateSavedLiftExportRequest(lift_ids=[UUID(VIDEO_ID_1)], archive_path="other-user/export.zip")


if __name__ == "__main__":
  unittest.main()
