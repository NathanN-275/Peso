from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from datetime import datetime, timezone
import weakref
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, status
from pydantic import ValidationError

from app.routes.saved_lift_exports import CreateSavedLiftExportRequest, create_saved_lift_export
from app.services.analyzed_video_exports import AnalyzedVideoArtifact
from app.services.config import Settings
from app.services.saved_lift_exports import SavedLiftExportService
from app.services.saved_lift_export_repository import SavedLiftExportRepository


USER_ID = "33333333-3333-3333-3333-333333333333"
VIDEO_ID_1 = "11111111-1111-1111-1111-111111111111"
VIDEO_ID_2 = "22222222-2222-2222-2222-222222222222"
JOB_ID = "55555555-5555-5555-5555-555555555555"
ATTEMPT_ID = "77777777-7777-7777-7777-777777777777"


def settings(**overrides) -> Settings:
  values = {
    "backend_env": "test",
    "supabase_url": "https://example.supabase.co",
    "supabase_service_role_key": "service-role",
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
    videos.get_analysis_result.side_effect = analysis
    jobs = MagicMock()
    jobs.mark_completed.return_value={"id":JOB_ID,"user_id":USER_ID,"status":"completed","archive_path":f"{USER_ID}/{JOB_ID}.zip"}
    video_storage = MagicMock()
    archive_storage = MagicMock()
    service = SavedLiftExportService(
      videos=videos,
      jobs=jobs,
      video_storage=video_storage,
      archive_storage=archive_storage,
      settings=settings(**({"max_saved_lift_export_bytes": max_bytes} if max_bytes else {})),
    )
    video_storage.bucket = "videos"
    archive_storage.bucket = "saved-lift-exports"
    def plan(_storage, job):
      available = {row["id"]: row for row in videos.get_owned_videos.return_value}
      return dict(user_id=USER_ID, archive_job_id=JOB_ID, archive_attempt_count=1,
        archive_started_at="2026-10-29T00:00:00+00:00", video_ids=job["video_ids"],
        member_snapshots=[dict(video_id=vid,source_path=available[vid]["playback_path"],
          analysis_id=analysis(vid)["id"],analysis_model_version="test-model",analysis_snapshot_hash="a"*64,
          variant="clean",entry_name=f'{index:02d}-{available[vid]["exercise_type"]}-{vid}.mp4')
          for index,vid in enumerate(job["video_ids"],start=1)])
    def write(**fields):
      path=f"{USER_ID}/{JOB_ID}-{fields['attempt_id']}.zip"
      archive_storage.create_file(path,fields["output_path"],"application/zip",cache_control="31536000")
      jobs.require_owned.return_value={**jobs.require_owned.return_value,"status":"completed","archive_path":path}
      return path
    plan_patch=patch("app.services.saved_lift_exports.plan_archive",side_effect=plan)
    write_patch=patch("app.services.saved_lift_exports.write_archive",side_effect=write)
    nonce_patch=patch("app.services.saved_lift_exports.uuid4",return_value=ATTEMPT_ID)
    plan_patch.start();self.addCleanup(plan_patch.stop)
    service._test_archive_write=write_patch.start();self.addCleanup(write_patch.stop)
    nonce_patch.start();self.addCleanup(nonce_patch.stop)
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
    videos.get_latest_analysis_results.assert_called_once_with(
      [VIDEO_ID_1, VIDEO_ID_2], include_result_json=False,
    )
    videos.get_analysis_result.assert_not_called()
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
    jobs.mark_processing.return_value = {"id": JOB_ID,"user_id":USER_ID,"status":"processing"}
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

    def upload(_path: str, local_path: Path, _content_type: str, **_options) -> None:
      with zipfile.ZipFile(local_path) as archive:
        archived_names.extend(archive.namelist())

    video_storage.download_to_tempfile.side_effect = download
    video_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
    archive_storage.create_file.side_effect = upload
    archive_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)

    with patch(
      "app.services.saved_lift_exports.ensure_analyzed_video_artifact",
      side_effect=lambda **kwargs: AnalyzedVideoArtifact(
        storage_path=kwargs["video"]["playback_path"],
        variant="clean",
      ),
    ) as ensure_artifact:
      service.process_job(JOB_ID, USER_ID)

    self.assertEqual(ensure_artifact.call_count, 2)
    self.assertEqual(videos.get_analysis_result.call_args_list, [call(VIDEO_ID_1), call(VIDEO_ID_2)])
    jobs.mark_processing.assert_called_once_with(JOB_ID, USER_ID)
    self.assertEqual(len(archived_names), 2)
    self.assertEqual(len(set(archived_names)), 2)
    self.assertTrue(archived_names[0].startswith("01-squat-"))
    self.assertTrue(archived_names[1].startswith("02-deadlift-"))
    archive_storage.create_file.assert_called_once()
    service._test_archive_write.assert_called_once()
    jobs.mark_failed.assert_not_called()
    self.assertTrue(all(not path.exists() for path in source_files))

  def test_fifty_lift_archive_releases_each_analysis_before_loading_the_next(self) -> None:
    service, videos, jobs, video_storage, archive_storage = self._service()
    selected = [str(UUID(int=index)) for index in range(1, 51)]
    videos.get_owned_videos.return_value = [video(video_id) for video_id in selected]
    videos.video_is_saved.return_value = True
    videos.get_latest_analysis_results.return_value = {
      video_id: {key: value for key, value in analysis(video_id).items() if key != "result_json"}
      for video_id in selected
    }
    jobs.mark_processing.return_value = {"id": JOB_ID, "user_id": USER_ID, "status": "processing"}
    jobs.require_owned.return_value = {"id": JOB_ID, "user_id": USER_ID, "video_ids": selected}
    payload_references = []
    events = []
    archived_names = []

    class Payload(dict):
      pass

    def load_analysis(video_id):
      self.assertTrue(all(reference() is None for reference in payload_references))
      result = analysis(video_id)
      result["result_json"] = Payload(result["result_json"])
      payload_references.append(weakref.ref(result["result_json"]))
      events.append(("analysis", video_id))
      return result

    def render(**kwargs):
      events.append(("render", kwargs["video"]["id"]))
      return AnalyzedVideoArtifact(storage_path=kwargs["video"]["playback_path"], variant="clean")

    def download(path):
      self.assertTrue(all(reference() is None for reference in payload_references))
      events.append(("download", Path(path).stem))
      with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as artifact:
        artifact.write(b"synthetic clip")
        return Path(artifact.name)

    def upload(_path, local_path, _content_type, **_options):
      with zipfile.ZipFile(local_path) as archive:
        archived_names.extend(archive.namelist())

    videos.get_analysis_result.side_effect = load_analysis
    video_storage.download_to_tempfile.side_effect = download
    video_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
    archive_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
    archive_storage.create_file.side_effect = upload
    with patch("app.services.saved_lift_exports.ensure_analyzed_video_artifact", new=render):
      service.process_job(JOB_ID, USER_ID)

    self.assertEqual(events, [(phase, video_id) for video_id in selected for phase in ("analysis", "render", "download")])
    self.assertEqual(len(archived_names), 50)
    self.assertEqual(len(set(archived_names)), 50)
    self.assertTrue(all(reference() is None for reference in payload_references))
    videos.get_latest_analysis_results.assert_called_once_with(selected, include_result_json=False)
    service._test_archive_write.assert_called_once()
    jobs.mark_failed.assert_not_called()

  def test_unavailable_or_mismatched_member_analysis_stops_before_storage(self) -> None:
    for result in (None, {**analysis(VIDEO_ID_2)}, {**analysis(VIDEO_ID_1), "result_json": None}):
      with self.subTest(result=result):
        service, videos, jobs, video_storage, archive_storage = self._service()
        videos.get_owned_videos.return_value = [video(VIDEO_ID_1)]
        videos.video_is_saved.return_value = True
        videos.get_latest_analysis_results.return_value = {VIDEO_ID_1: {"id": "metadata-only"}}
        videos.get_analysis_result.side_effect = None
        videos.get_analysis_result.return_value = result
        jobs.mark_processing.return_value = {"id": JOB_ID, "user_id": USER_ID, "status": "processing"}
        jobs.require_owned.return_value = {"id": JOB_ID, "user_id": USER_ID, "video_ids": [VIDEO_ID_1]}
        archive_storage.remove_tempfile.side_effect = lambda path: Path(path).unlink(missing_ok=True)
        with patch("app.services.saved_lift_exports.ensure_analyzed_video_artifact") as render:
          service.process_job(JOB_ID, USER_ID)
        render.assert_not_called()
        video_storage.download_to_tempfile.assert_not_called()
        archive_storage.create_file.assert_not_called()
        jobs.mark_completed.assert_not_called()
        jobs.mark_failed.assert_called_once_with(JOB_ID, USER_ID, "lift_unavailable")

  def test_denied_or_wrong_owner_processing_never_loads_or_writes_media(self) -> None:
    for receipt in (None, {"id": JOB_ID, "user_id": VIDEO_ID_2, "status": "processing"}):
      with self.subTest(receipt=receipt):
        service, videos, jobs, video_storage, archive_storage = self._service()
        jobs.mark_processing.return_value = receipt
        service.process_job(JOB_ID, USER_ID)
        jobs.mark_processing.assert_called_once_with(JOB_ID, USER_ID)
        jobs.require_owned.assert_not_called()
        videos.get_owned_videos.assert_not_called()
        video_storage.download_to_tempfile.assert_not_called()
        archive_storage.create_file.assert_not_called()
        if receipt is None:
          jobs.mark_failed.assert_not_called()
        else:
          jobs.mark_failed.assert_called_once_with(JOB_ID, USER_ID, "generation_failed")

  def test_process_job_records_oversized_bundle_as_failed(self) -> None:
    service, videos, jobs, video_storage, archive_storage = self._service(max_bytes=16)
    videos.get_owned_videos.return_value = [video(VIDEO_ID_1)]
    videos.video_is_saved.return_value = True
    videos.get_latest_analysis_results.return_value = {VIDEO_ID_1: analysis(VIDEO_ID_1)}
    jobs.mark_processing.return_value = {"id": JOB_ID,"user_id":USER_ID,"status":"processing"}
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

    archive_storage.create_file.assert_not_called()
    jobs.mark_completed.assert_not_called()
    jobs.mark_failed.assert_called_once_with(JOB_ID, USER_ID, "archive_too_large")


  def test_exhausted_database_lock_errors_retire_job_instead_of_stranding_processing(self) -> None:
    service,_,jobs,_,archive_storage=self._service()
    for code in ("55P03","40P01","40001"):
      with self.subTest(code=code):
        error=RuntimeError("synthetic database contention");error.code=code
        jobs.mark_processing.side_effect=error
        service.process_job(JOB_ID,USER_ID)
    self.assertEqual(jobs.mark_failed.call_count,3)
    jobs.mark_failed.assert_called_with(JOB_ID,USER_ID,"capacity_unavailable")
    archive_storage.create_file.assert_not_called()

  def _publication_service(self):
    service,videos,jobs,video_storage,archive_storage=self._service()
    videos.get_owned_videos.return_value=[video(VIDEO_ID_1)]
    videos.video_is_saved.return_value=True
    videos.get_latest_analysis_results.return_value={VIDEO_ID_1:analysis(VIDEO_ID_1)}
    jobs.mark_processing.return_value={"id":JOB_ID,"user_id":USER_ID,"status":"processing"}
    jobs.require_owned.return_value={"id":JOB_ID,"user_id":USER_ID,"video_ids":[VIDEO_ID_1],"status":"processing"}
    source=tempfile.NamedTemporaryFile(delete=False,suffix=".mp4");source.write(b"fixture");source.close()
    video_storage.download_to_tempfile.return_value=Path(source.name)
    video_storage.remove_tempfile.side_effect=lambda path:Path(path).unlink(missing_ok=True)
    archive_storage.remove_tempfile.side_effect=lambda path:Path(path).unlink(missing_ok=True)
    return service,jobs,archive_storage





  def test_uncertain_archive_write_preserves_bytes_and_never_compensates(self):
    service,jobs,storage=self._publication_service()
    service._test_archive_write.side_effect=HTTPException(503,"synthetic uncertain dispatch")
    with patch("app.services.saved_lift_exports.ensure_analyzed_video_artifact",return_value=AnalyzedVideoArtifact(
        storage_path=f"{USER_ID}/playback/{VIDEO_ID_1}.mp4",variant="clean")):
      service.process_job(JOB_ID,USER_ID)
    jobs.mark_failed.assert_called_once_with(JOB_ID,USER_ID,"generation_failed")
    storage.delete_storage_path.assert_not_called()
    jobs.mark_completed.assert_not_called()

  def test_lost_publication_response_reconciles_exact_committed_nonce_without_deletion(self):
    service,jobs,storage=self._publication_service()
    def lost(**fields):
      jobs.require_owned.return_value={**jobs.require_owned.return_value,"status":"completed",
        "archive_path":f"{USER_ID}/{JOB_ID}-{fields['attempt_id']}.zip"}
      raise TimeoutError("synthetic lost publication response")
    service._test_archive_write.side_effect=lost
    with patch("app.services.saved_lift_exports.ensure_analyzed_video_artifact",return_value=AnalyzedVideoArtifact(
        storage_path=f"{USER_ID}/playback/{VIDEO_ID_1}.mp4",variant="clean")):
      service.process_job(JOB_ID,USER_ID)
    jobs.mark_failed.assert_not_called();storage.delete_storage_path.assert_not_called()

  def test_wrong_nonce_publication_does_not_confirm_uncertain_attempt(self):
    service,jobs,storage=self._publication_service()
    def lost(**_fields):
      jobs.require_owned.return_value={**jobs.require_owned.return_value,"status":"completed",
        "archive_path":f"{USER_ID}/{JOB_ID}.zip"}
      raise TimeoutError("synthetic wrong publication")
    service._test_archive_write.side_effect=lost
    with patch("app.services.saved_lift_exports.ensure_analyzed_video_artifact",return_value=AnalyzedVideoArtifact(
        storage_path=f"{USER_ID}/playback/{VIDEO_ID_1}.mp4",variant="clean")):
      service.process_job(JOB_ID,USER_ID)
    jobs.mark_failed.assert_called_once_with(JOB_ID,USER_ID,"generation_failed")
    storage.delete_storage_path.assert_not_called()

  def test_archive_metadata_errors_do_not_clear_publication_or_sign_a_url(self):
    service,_,jobs,_,storage=self._service()
    jobs.require_owned.return_value={"id":JOB_ID,"user_id":USER_ID,"status":"completed",
      "archive_path":f"{USER_ID}/{JOB_ID}-{ATTEMPT_ID}.zip","created_at":"2026-10-29T00:00:00+00:00",
      "expires_at":"2099-01-01T00:00:00+00:00"}
    for error in (RuntimeError("NoSuchKey"),RuntimeError("Forbidden")):
      storage.get_object_info.side_effect=error
      with self.subTest(error=error),patch("app.services.saved_lift_exports.read_published_archive",return_value={
          "storage_path":jobs.require_owned.return_value["archive_path"],"size_bytes":10}),self.assertRaises(HTTPException):
        service.job_projection(JOB_ID,USER_ID)
    jobs.mark_failed.assert_not_called();jobs.mark_expired.assert_not_called()
    storage.delete_storage_path.assert_not_called();storage.create_signed_url.assert_not_called()

  def test_completed_archive_only_signs_provider_url_in_legacy_mode(self) -> None:
    service, _, jobs, _, storage = self._service()
    path = f"{USER_ID}/{JOB_ID}-{ATTEMPT_ID}.zip"
    jobs.require_owned.return_value = {
      "id": JOB_ID, "user_id": USER_ID, "status": "completed", "archive_path": path,
      "created_at": "2026-10-29T00:00:00+00:00", "expires_at": "2099-01-01T00:00:00+00:00",
    }
    storage.create_signed_url.return_value = "https://example.supabase.co/synthetic-signed-archive"
    publication = {"storage_path": path, "size_bytes": 10}
    with patch("app.services.saved_lift_exports.read_published_archive", return_value=publication), \
        patch("app.services.saved_lift_exports.require_cached_export_object") as verify:
      service.settings = settings(private_media_enabled=True)
      private = service.job_projection(JOB_ID, USER_ID)
      self.assertEqual(private["status"], "completed")
      self.assertIsNone(private["download_url"])
      self.assertIsNone(private["download_expires_in"])
      self.assertNotIn(path, str(private))
      storage.create_signed_url.assert_not_called()

      service.settings = settings(private_media_enabled=False)
      legacy = service.job_projection(JOB_ID, USER_ID)
      self.assertEqual(legacy["download_url"], storage.create_signed_url.return_value)
      self.assertEqual(legacy["download_expires_in"], 300)
      storage.create_signed_url.assert_called_once_with(path, expires_in=300)
      self.assertEqual(verify.call_args_list, [call(storage, publication), call(storage, publication)])

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


class SavedLiftExportRepositoryTest(unittest.TestCase):
  def repository(self, rows):
    repo=SavedLiftExportRepository.__new__(SavedLiftExportRepository)
    repo.client=MagicMock()
    query=repo.client.table.return_value
    query.update.return_value=query;query.eq.return_value=query;query.in_.return_value=query
    query.execute.return_value.data=rows
    return repo,query

  def test_transient_sql_abort_retried_before_terminal_failure(self):
    repo,query=self.repository([])
    for code in ("55P03","40P01","40001"):
      with self.subTest(code=code):
        error=RuntimeError("synthetic aborted transaction");error.code=code
        response=MagicMock();response.data=[{"id":JOB_ID,"user_id":USER_ID,"status":"processing"}]
        query.execute.reset_mock();query.execute.side_effect=[error,response]
        with patch("app.services.saved_lift_export_repository.time.sleep") as sleep:
          self.assertEqual(repo.mark_processing(JOB_ID, USER_ID),response.data[0])
        self.assertEqual(query.execute.call_count,2);sleep.assert_called_once_with(0.1)

  def test_exhausted_sql_abort_retries_are_bounded(self):
    repo,query=self.repository([])
    error=RuntimeError("synthetic aborted transaction");error.code="55P03"
    query.execute.side_effect=error
    with patch("app.services.saved_lift_export_repository.time.sleep") as sleep,self.assertRaises(RuntimeError):
      repo.mark_processing(JOB_ID, USER_ID)
    self.assertEqual(query.execute.call_count,3);self.assertEqual(sleep.call_count,2)

  def test_transport_uncertainty_is_never_blindly_retried(self):
    repo,query=self.repository([]);query.execute.side_effect=RuntimeError("lost response")
    with patch("app.services.saved_lift_export_repository.time.sleep") as sleep,self.assertRaises(RuntimeError): repo.mark_processing(JOB_ID, USER_ID)
    self.assertEqual(query.execute.call_count,1);sleep.assert_not_called()

  def test_malformed_or_mismatched_transition_response_rejected(self):
    for rows in (True,{},[{"id":JOB_ID,"status":"completed"}],[{"id":VIDEO_ID_1,"status":"processing"}],
                 [{"id":"00000000-0000-0000-0000-000000000000","status":"processing"}],
                 [{"id":JOB_ID,"user_id":USER_ID,"status":"processing"}]*2):
      with self.subTest(rows=rows):
        repo,_=self.repository(rows)
        with self.assertRaises(RuntimeError):repo.mark_processing(JOB_ID, USER_ID)

  def test_completion_only_matches_processing_and_returns_none_after_revocation(self):
    repo,query=self.repository([])
    self.assertIsNone(repo.mark_completed(JOB_ID, USER_ID,archive_path=f"{USER_ID}/{JOB_ID}.zip",completed_at="2026-10-27T00:00:00Z",expires_at="2026-10-27T01:00:00Z"))
    query.in_.assert_called_once_with("status",["processing"])

  def test_worker_failure_only_matches_unpublished_active_jobs(self):
    repo,query=self.repository([])
    self.assertIsNone(repo.mark_failed(JOB_ID, USER_ID,"generation_failed"))
    query.in_.assert_called_once_with("status",["queued","processing"])

  def test_archive_missing_only_matches_completed_jobs(self):
    repo,query=self.repository([])
    self.assertIsNone(repo.mark_failed(JOB_ID, USER_ID,"archive_missing"))
    query.in_.assert_called_once_with("status",["completed"])

  def test_expiry_never_matches_already_expired(self):
    repo,query=self.repository([])
    self.assertIsNone(repo.mark_expired(JOB_ID, USER_ID))
    query.in_.assert_called_once_with("status",["queued","processing","completed","failed"])

  def test_successful_transition_returns_persisted_row(self):
    row={"id":JOB_ID,"user_id":USER_ID,"status":"failed"}
    repo,_=self.repository([row])
    self.assertEqual(repo.mark_failed(JOB_ID, USER_ID,"generation_failed"),row)

  def test_all_job_mutations_filter_by_owner_before_execution(self):
    transitions = (
      lambda repo: repo.mark_processing(JOB_ID, USER_ID),
      lambda repo: repo.mark_completed(JOB_ID, USER_ID, archive_path=f"{USER_ID}/{JOB_ID}.zip",
                                       completed_at="2026-10-29T00:00:00Z", expires_at="2026-10-30T00:00:00Z"),
      lambda repo: repo.mark_failed(JOB_ID, USER_ID, "generation_failed"),
      lambda repo: repo.mark_failed(JOB_ID, USER_ID, "archive_missing"),
      lambda repo: repo.mark_expired(JOB_ID, USER_ID),
    )
    for transition in transitions:
      with self.subTest(transition=transition):
        repo, query = self.repository([])
        self.assertIsNone(transition(repo))
        filters = query.eq.call_args_list
        self.assertIn(call("id", JOB_ID), filters)
        self.assertIn(call("user_id", USER_ID), filters)
        query.execute.assert_called_once()

  def test_wrong_or_missing_owner_receipts_are_rejected_for_every_transition(self):
    for owner in (None, VIDEO_ID_2):
      for target in ("processing", "completed", "failed", "expired"):
        with self.subTest(owner=owner, target=target):
          row = {"id": JOB_ID, "user_id": owner, "status": target,
                 "archive_path": f"{USER_ID}/{JOB_ID}.zip"}
          repo, _ = self.repository([row])
          with self.assertRaises(RuntimeError):
            if target == "processing":
              repo.mark_processing(JOB_ID, USER_ID)
            elif target == "completed":
              repo.mark_completed(JOB_ID, USER_ID, archive_path=row["archive_path"],
                                  completed_at="2026-10-29T00:00:00Z", expires_at="2026-10-30T00:00:00Z")
            elif target == "failed":
              repo.mark_failed(JOB_ID, USER_ID, "generation_failed")
            else:
              repo.mark_expired(JOB_ID, USER_ID)


if __name__ == "__main__":
  unittest.main()
