from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.analysis.versioning import annotate_analysis_freshness, analysis_is_current
from app.routes.videos import (
  RegisterVideoRequest,
  SaveVideoRequest,
  DeleteSavedLiftsRequest,
  delete_account,
  delete_saved_lifts,
  discard_video,
  get_analysis_activity,
  get_video_capabilities,
  get_storage_usage,
  get_video_playback_url,
  get_saved_video_overview,
  list_saved_videos,
  list_saved_videos_page,
  mark_upload_failed,
  queue_analysis,
  register_video,
  run_quality_preflight,
  save_video,
)
from app.analysis.side_squat.quality_preflight import (
  QUALITY_PREFLIGHT_MODEL_VERSION,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
)
from app.services.config import DEFAULT_MODEL_VERSION, get_settings
from app.services.video_work_limits import reset_video_work_limits_for_tests


VIDEO_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_USER_ID = "44444444-4444-4444-4444-444444444444"


class VideoRoutesTest(unittest.TestCase):
  def setUp(self) -> None:
    self.env_patcher = patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=False,
    )
    self.env_patcher.start()
    get_settings.cache_clear()
    reset_video_work_limits_for_tests()

  def tearDown(self) -> None:
    self.env_patcher.stop()
    get_settings.cache_clear()
    reset_video_work_limits_for_tests()

  def test_queue_analysis_queues_uploaded_owned_video(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    jobs = MagicMock()
    jobs.enqueue.return_value = {
      "id": "55555555-5555-5555-5555-555555555555",
      "status": "queued",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, USER_ID)

    storage.validate_video_object.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    jobs.enqueue.assert_called_once_with(str(VIDEO_ID), allow_completed=False)
    self.assertEqual(response.status, "queued")
    self.assertEqual(str(response.job_id), "55555555-5555-5555-5555-555555555555")
    self.assertEqual(response.stage, "queued")

  def test_batch_delete_permanently_removes_each_owned_saved_lift(self) -> None:
    second_video_id = UUID("22222222-2222-2222-2222-222222222222")
    repository = MagicMock()
    repository.get_owned_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "user_id": USER_ID,
        "save_state": "saved",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      },
      {
        "id": str(second_video_id),
        "user_id": USER_ID,
        "save_state": "saved",
        "storage_path": f"{USER_ID}/uploads/{second_video_id}.mov",
      },
    ]
    repository.video_is_saved.return_value = True
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = delete_saved_lifts(
        DeleteSavedLiftsRequest(lift_ids=[VIDEO_ID, second_video_id, VIDEO_ID]),
        USER_ID,
      )

    self.assertEqual(response.deleted_count, 2)
    self.assertEqual(
      [call.args[0] for call in repository.delete_video_with_analysis.call_args_list],
      [str(VIDEO_ID), str(second_video_id)],
    )

  def test_batch_delete_rejects_selection_containing_unowned_lift_before_mutation(self) -> None:
    second_video_id = UUID("22222222-2222-2222-2222-222222222222")
    repository = MagicMock()
    repository.get_owned_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "user_id": USER_ID,
        "save_state": "saved",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      }
    ]

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService") as storage,
      self.assertRaises(HTTPException) as raised,
    ):
      delete_saved_lifts(
        DeleteSavedLiftsRequest(lift_ids=[VIDEO_ID, second_video_id]),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 404)
    repository.delete_video_with_analysis.assert_not_called()
    storage.assert_not_called()

  def test_storage_usage_endpoint_returns_quota_report_without_mutation(self) -> None:
    quota_service = MagicMock()
    quota_service.get_usage.return_value.to_dict.return_value = {
      "storage_limit_bytes": 1024,
      "database_limit_bytes": 512,
      "monthly_egress_limit_bytes": 5120,
      "current_storage_bytes": 100,
      "upload_size_bytes": 50,
      "playback_allowance_bytes": 50,
      "thumbnail_allowance_bytes": 1,
      "projected_peak_bytes": 201,
      "warning_threshold_bytes": 819,
      "block_threshold_bytes": 972,
      "status": "ok",
      "blocked": False,
      "message": "Storage capacity is available for this upload.",
    }

    settings = MagicMock(expose_storage_quota_details=False)

    with (
      patch("app.routes.videos.StorageQuotaService", return_value=quota_service),
      patch("app.routes.videos.get_settings", return_value=settings),
    ):
      response = get_storage_usage(50, USER_ID)

    quota_service.get_usage.assert_called_once_with(50)
    self.assertEqual(response.projected_peak_bytes, 0)
    self.assertEqual(response.current_storage_bytes, 0)
    self.assertEqual(response.storage_limit_bytes, 0)
    self.assertEqual(response.upload_size_bytes, 50)
    self.assertFalse(response.blocked)

  def test_register_video_creates_server_owned_uploaded_row(self) -> None:
    repository = MagicMock()
    repository.count_user_in_progress_videos.return_value = 0
    repository.count_recent_user_uploads.return_value = 0
    repository.create_uploaded_video.return_value = {
      "id": str(VIDEO_ID),
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
    }
    storage = MagicMock()
    storage.validate_video_object.return_value = {"metadata": {"size": "2048", "mimetype": "video/mp4"}}
    storage.storage_object_size_bytes.return_value = 2048
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=300000,
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      patch("app.routes.videos.uuid4", return_value=VIDEO_ID),
    ):
      response = register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="Bench Press",
          view_type="Front",
          duration_ms=1200,
        ),
        USER_ID,
      )

    storage.validate_video_object.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mp4")
    fields = repository.create_uploaded_video.call_args.args[0]
    self.assertEqual(fields["user_id"], USER_ID)
    self.assertEqual(fields["status"], "uploaded")
    self.assertEqual(fields["save_state"], "pending")
    self.assertEqual(fields["uploaded_size_bytes"], 2048)
    self.assertEqual(fields["original_size_bytes"], 2048)
    self.assertFalse(fields["quality_preflight_required"])
    self.assertEqual(response.video_id, VIDEO_ID)
    self.assertEqual(response.uploaded_size_bytes, 2048)

  def test_register_video_requires_preflight_only_for_new_side_view_squats(self) -> None:
    repository = MagicMock()
    repository.count_user_in_progress_videos.return_value = 0
    repository.count_recent_user_uploads.return_value = 0
    repository.create_uploaded_video.return_value = {
      "id": str(VIDEO_ID),
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
    }
    storage = MagicMock()
    storage.validate_video_object.return_value = {"metadata": {"size": "2048", "mimetype": "video/mp4"}}
    storage.storage_object_size_bytes.return_value = 2048
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=300000,
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      patch("app.routes.videos.uuid4", return_value=VIDEO_ID),
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          exercise_type="Goblet Squat",
          view_type="Side",
        ),
        USER_ID,
      )

    fields = repository.create_uploaded_video.call_args.args[0]
    self.assertTrue(fields["quality_preflight_required"])

  def test_register_video_rejects_server_owned_client_fields(self) -> None:
    for field, value in {
      "id": str(VIDEO_ID),
      "status": "completed",
      "save_state": "saved",
      "expires_at": "2099-01-01T00:00:00+00:00",
      "original_size_bytes": 1024,
      "uploaded_size_bytes": 1024,
      "was_compressed": True,
      "playback_path": f"{USER_ID}/playback/{VIDEO_ID}.mp4",
      "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
    }.items():
      with self.subTest(field=field):
        with self.assertRaises(ValidationError):
          RegisterVideoRequest(
            storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
            source_type="camera_roll",
            exercise_type="squat",
            view_type="side",
            **{field: value},
          )

  def test_register_video_rejects_cross_user_storage_path(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{OTHER_USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
        ),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 403)
    storage.validate_video_object.assert_not_called()
    repository.create_uploaded_video.assert_not_called()

  def test_register_video_rejects_malformed_storage_path_before_storage_lookup(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/../{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
        ),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 403)
    storage.validate_video_object.assert_not_called()
    repository.create_uploaded_video.assert_not_called()

  def test_register_video_rejects_oversized_duration_before_storage_lookup(self) -> None:
    repository = MagicMock()
    storage = MagicMock()
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=1000,
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      self.assertRaises(HTTPException) as raised,
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
          duration_ms=1001,
        ),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 413)
    storage.validate_video_object.assert_not_called()
    repository.create_uploaded_video.assert_not_called()

  def test_register_video_rejects_malformed_tracking_setup(self) -> None:
    repository = MagicMock()
    repository.count_user_in_progress_videos.return_value = 0
    repository.count_recent_user_uploads.return_value = 0
    storage = MagicMock()
    storage.validate_video_object.return_value = {"metadata": {"size": "2048", "mimetype": "video/mp4"}}
    storage.storage_object_size_bytes.return_value = 2048
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=300000,
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      patch("app.routes.videos.validate_tracking_setup", return_value=(None, "invalid anchors")),
      self.assertRaises(HTTPException) as raised,
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
          tracking_setup={"version": 1, "anchors": {"barbell": {"x": 2, "y": -1}}},
        ),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 400)
    repository.create_uploaded_video.assert_not_called()

  def test_register_video_treats_zero_duration_as_unknown_for_tracking_bounds(self) -> None:
    repository = MagicMock()
    repository.count_user_in_progress_videos.return_value = 0
    repository.count_recent_user_uploads.return_value = 0
    repository.create_uploaded_video.return_value = {
      "id": str(VIDEO_ID),
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
    }
    storage = MagicMock()
    storage.validate_video_object.return_value = {"metadata": {"size": "2048", "mimetype": "video/mp4"}}
    storage.storage_object_size_bytes.return_value = 2048
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=300000,
    )
    tracking_setup = {
      "version": 1,
      "reference_time_ms": 5000,
      "barbell_target": "near_side_collar",
      "anchors": {
        "barbell": {"x": 0.5, "y": 0.4},
      },
    }

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      patch("app.routes.videos.uuid4", return_value=VIDEO_ID),
    ):
      response = register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
          duration_ms=0,
          tracking_setup=tracking_setup,
        ),
        USER_ID,
      )

    fields = repository.create_uploaded_video.call_args.args[0]
    self.assertEqual(fields["duration_ms"], 0)
    self.assertEqual(fields["tracking_setup"]["reference_time_ms"], 5000)
    self.assertEqual(response.video_id, VIDEO_ID)

  def test_register_video_rate_limits_active_user_work(self) -> None:
    repository = MagicMock()
    repository.count_user_in_progress_videos.return_value = 3
    storage = MagicMock()
    settings = MagicMock(
      saved_video_storage_ttl_hours=24,
      max_user_in_progress_videos=3,
      max_user_uploads_per_hour=20,
      max_video_duration_ms=300000,
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.get_settings", return_value=settings),
      self.assertRaises(HTTPException) as raised,
    ):
      register_video(
        RegisterVideoRequest(
          storage_path=f"{USER_ID}/uploads/{VIDEO_ID}.mp4",
          source_type="camera_roll",
          exercise_type="squat",
          view_type="side",
        ),
        USER_ID,
      )

    self.assertEqual(raised.exception.status_code, 429)
    storage.validate_video_object.assert_not_called()

  def test_video_capabilities_reports_pin_tracking_support(self) -> None:
    repository = MagicMock()
    repository.supports_tracking_setup.return_value = True
    repository.supports_quality_preflight.return_value = True

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = get_video_capabilities(USER_ID)

    repository.supports_tracking_setup.assert_called_once_with()
    self.assertTrue(response.pin_assisted_tracking)
    self.assertEqual(response.tracking_setup_versions, [1, 2])
    self.assertTrue(response.side_squat_quality_preflight)
    self.assertEqual(response.quality_preflight_versions, [QUALITY_PREFLIGHT_THRESHOLD_VERSION])
    self.assertIsNone(response.reason)

  def test_video_capabilities_reports_missing_tracking_migration(self) -> None:
    repository = MagicMock()
    repository.supports_tracking_setup.return_value = False
    repository.supports_quality_preflight.return_value = True

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = get_video_capabilities(USER_ID)

    self.assertFalse(response.pin_assisted_tracking)
    self.assertEqual(response.tracking_setup_versions, [])
    self.assertEqual(response.reason, "tracking_setup_migration_missing")

  def test_video_capabilities_reports_missing_preflight_migration(self) -> None:
    repository = MagicMock()
    repository.supports_tracking_setup.return_value = True
    repository.supports_quality_preflight.return_value = False

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = get_video_capabilities(USER_ID)

    self.assertTrue(response.pin_assisted_tracking)
    self.assertFalse(response.side_squat_quality_preflight)
    self.assertEqual(response.quality_preflight_versions, [])
    self.assertEqual(response.reason, "quality_preflight_migration_missing")

  def test_quality_preflight_persists_evidence_and_removes_tempfile(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "exercise_type": "squat",
      "view_type": "side",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "quality_preflight": None,
    }
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/preflight.mov"
    preflight = {
      "status": "warning",
      "overallConfidence": 0.78,
      "checks": {},
      "userMessages": ["Use more light."],
      "recordingTips": ["Use more light."],
      "modelVersion": QUALITY_PREFLIGHT_MODEL_VERSION,
      "thresholdVersion": QUALITY_PREFLIGHT_THRESHOLD_VERSION,
      "thresholds": {},
      "sampledFrameMetadata": {"frames": []},
      "processingDurationMs": 12,
    }
    evaluator = MagicMock()
    evaluator.evaluate_file.return_value = preflight

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.SideSquatQualityPreflight", return_value=evaluator),
    ):
      response = run_quality_preflight(VIDEO_ID, USER_ID)

    storage.download_to_tempfile.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    evaluator.evaluate_file.assert_called_once_with("/tmp/preflight.mov", exercise_type="squat")
    repository.update_video.assert_called_once_with(str(VIDEO_ID), {"quality_preflight": preflight})
    storage.remove_tempfile.assert_called_once_with("/tmp/preflight.mov")
    self.assertEqual(response.status, "warning")

  def test_queue_analysis_requires_current_preflight_for_flagged_submission(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "quality_preflight_required": True,
      "quality_preflight": None,
    }

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService") as storage,
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 409)
    storage.assert_not_called()
    repository.count_user_in_progress_videos.assert_not_called()

  def test_queue_analysis_allows_blocked_preflight_as_advisory(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "quality_preflight_required": True,
      "quality_preflight": {
        "status": "blocked",
        "modelVersion": QUALITY_PREFLIGHT_MODEL_VERSION,
        "thresholdVersion": QUALITY_PREFLIGHT_THRESHOLD_VERSION,
      },
    }

    repository.count_user_in_progress_videos.return_value = 0
    jobs = MagicMock()
    jobs.enqueue.return_value = {
      "id": "55555555-5555-5555-5555-555555555555",
      "status": "queued",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(response.status, "queued")
    jobs.enqueue.assert_called_once_with(str(VIDEO_ID), allow_completed=False)

  def test_queue_analysis_allows_warning_preflight(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "quality_preflight_required": True,
      "quality_preflight": {
        "status": "warning",
        "modelVersion": QUALITY_PREFLIGHT_MODEL_VERSION,
        "thresholdVersion": QUALITY_PREFLIGHT_THRESHOLD_VERSION,
      },
    }
    repository.count_user_in_progress_videos.return_value = 0
    jobs = MagicMock()
    jobs.enqueue.return_value = {
      "id": "55555555-5555-5555-5555-555555555555",
      "status": "queued",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(response.status, "queued")
    jobs.enqueue.assert_called_once_with(str(VIDEO_ID), allow_completed=False)

  def test_video_capabilities_returns_service_unavailable_for_database_errors(self) -> None:
    repository = MagicMock()
    repository.supports_tracking_setup.side_effect = RuntimeError("database unavailable")

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      self.assertRaises(HTTPException) as raised,
    ):
      get_video_capabilities(USER_ID)

    self.assertEqual(raised.exception.status_code, 503)

  def test_queue_analysis_returns_idempotent_in_progress_status(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "processing",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    jobs = MagicMock()
    jobs.enqueue.return_value = {
      "id": "55555555-5555-5555-5555-555555555555",
      "status": "processing",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, USER_ID)

    storage.validate_video_object.assert_not_called()
    repository.count_user_in_progress_videos.assert_not_called()
    jobs.enqueue.assert_called_once_with(str(VIDEO_ID), allow_completed=False)
    self.assertEqual(response.status, "processing")

  def test_queue_analysis_fails_closed_when_durable_queue_is_unavailable(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    repository.count_user_in_progress_videos.return_value = 0
    jobs = MagicMock()
    jobs.enqueue.side_effect = RuntimeError("analysis_jobs relation missing")

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=MagicMock()),
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 503)
    self.assertIn("durable analysis jobs migration", raised.exception.detail.lower())

  def test_analysis_activity_is_owner_scoped_and_maps_retry_to_queued(self) -> None:
    repository = MagicMock()
    repository.list_analysis_activity_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "user_id": USER_ID,
        "status": "queued",
        "save_state": "pending",
        "exercise_type": "squat",
        "view_type": "side",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
        "created_at": "2026-08-17T18:00:00+00:00",
        "updated_at": "2026-08-17T18:01:00+00:00",
        "expires_at": "2026-08-18T18:00:00+00:00",
      }
    ]
    repository.count_user_in_progress_videos.return_value = 1
    jobs = MagicMock()
    jobs.latest_for_videos.return_value = {
      str(VIDEO_ID): {
        "id": "55555555-5555-5555-5555-555555555555",
        "video_id": str(VIDEO_ID),
        "status": "retry_wait",
        "stage": "queued",
        "stage_started_at": "2026-08-17T18:01:01+00:00",
        "stage_timestamps": {
          "queued": "2026-08-17T18:01:01+00:00",
        },
        "last_heartbeat_at": "2026-08-17T18:01:00+00:00",
        "failure_class": "transient_infrastructure",
        "created_at": "2026-08-17T18:00:01+00:00",
        "updated_at": "2026-08-17T18:01:01+00:00",
      }
    }
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/activity-thumb"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = get_analysis_activity(USER_ID)

    repository.list_analysis_activity_videos.assert_called_once_with(USER_ID)
    repository.count_user_in_progress_videos.assert_called_once_with(USER_ID)
    jobs.latest_for_videos.assert_called_once_with([str(VIDEO_ID)])
    self.assertEqual(response.active_count, 1)
    self.assertEqual(response.active_limit, 3)
    self.assertEqual(len(response.items), 1)
    self.assertEqual(response.items[0].status, "queued")
    self.assertEqual(response.items[0].stage, "queued")
    self.assertEqual(
      response.items[0].stage_timestamps["queued"],
      "2026-08-17T18:01:01+00:00",
    )
    self.assertEqual(response.items[0].failure_class, "transient_infrastructure")
    self.assertEqual(response.items[0].thumbnail_url, "https://example.test/activity-thumb")

  def test_analysis_activity_returns_service_unavailable_when_queue_schema_is_missing(self) -> None:
    repository = MagicMock()
    repository.list_analysis_activity_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "user_id": USER_ID,
        "status": "queued",
        "save_state": "pending",
        "exercise_type": "squat",
        "view_type": "side",
        "created_at": "2026-08-17T18:00:00+00:00",
        "updated_at": "2026-08-17T18:01:00+00:00",
      }
    ]
    jobs = MagicMock()
    jobs.latest_for_videos.side_effect = RuntimeError("column analysis_jobs.stage does not exist")

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=MagicMock()),
      self.assertRaises(HTTPException) as raised,
    ):
      get_analysis_activity(USER_ID)

    self.assertEqual(raised.exception.status_code, 503)
    self.assertEqual(
      raised.exception.detail,
      "Analysis activity is temporarily unavailable. The queue schema is not ready.",
    )

  def test_queue_analysis_rejects_unqueueable_status(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "discarded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    storage.validate_video_object.assert_not_called()
    self.assertEqual(raised.exception.status_code, 409)

  def test_queue_analysis_rejects_when_user_analysis_limit_is_saturated(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    repository.count_user_in_progress_videos.return_value = 3
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 429)
    storage.validate_video_object.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    repository.count_user_in_progress_videos.assert_called_once_with(USER_ID)

  def test_queue_analysis_accepts_work_while_worker_is_busy(self) -> None:
    second_video_id = UUID("22222222-2222-2222-2222-222222222222")
    first_repository = MagicMock()
    first_repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    first_repository.count_user_in_progress_videos.return_value = 0
    second_repository = MagicMock()
    second_repository.require_owned_video.return_value = {
      "id": str(second_video_id),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{second_video_id}.mov",
    }
    second_repository.count_user_in_progress_videos.return_value = 0
    jobs = MagicMock()
    jobs.enqueue.side_effect = [
      {"id": "55555555-5555-5555-5555-555555555555", "status": "queued"},
      {"id": "66666666-6666-6666-6666-666666666666", "status": "queued"},
    ]
    storage = MagicMock()

    with (
      patch.dict(os.environ, {"MAX_GLOBAL_VIDEO_WORKERS": "1"}, clear=False),
      patch("app.routes.videos.VideoRepository", side_effect=[first_repository, second_repository]),
      patch("app.routes.videos.AnalysisJobRepository", return_value=jobs),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      get_settings.cache_clear()
      first_response = queue_analysis(VIDEO_ID, USER_ID)
      second_response = queue_analysis(second_video_id, USER_ID)

    self.assertEqual(first_response.status, "queued")
    self.assertEqual(second_response.status, "queued")
    self.assertEqual(jobs.enqueue.call_count, 2)

  def test_queue_analysis_rejects_cross_user_storage_path_before_validation(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{OTHER_USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 403)
    storage.validate_video_object.assert_not_called()

  def test_queue_analysis_propagates_ownership_errors(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.side_effect = HTTPException(
      status_code=403,
      detail="Video does not belong to this user.",
    )

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      self.assertRaises(HTTPException) as raised,
    ):
      queue_analysis(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 403)

  def test_list_saved_videos_does_not_sign_full_video_urls(self) -> None:
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg",
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      }
    ]
    repository.get_analysis_result.return_value = None
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/signed-thumbnail"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = list_saved_videos(USER_ID)

    storage.create_signed_url.assert_called_once_with(
      f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg",
      expires_in=300,
    )
    self.assertIsNone(response[0].video_url)
    self.assertEqual(response[0].thumbnail_url, "https://example.test/signed-thumbnail")
    self.assertIsNone(response[0].storage_path)

  def test_list_saved_videos_returns_small_analysis_summary_only(self) -> None:
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "performed_reps": 7,
        "load_value": 102.5,
        "load_unit": "kg",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "thumbnail_path": None,
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      }
    ]
    repository.get_analysis_result.return_value = {
      "id": str(VIDEO_ID),
      "model_version": "test-model",
      "created_at": "2026-05-24T12:00:00+00:00",
      "result_json": {
        "summary_flags": ["inconsistent_depth"],
        "coach_feedback": ["Stay tight."],
        "poseFrames": [{"time": 0, "keypoints": []}],
        "reps": [{"rep_index": 1}],
        "rep_count": 1,
        "diagnostics": {},
      },
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.annotate_analysis_freshness", side_effect=lambda result, analysis: result),
    ):
      response = list_saved_videos(USER_ID)

    self.assertEqual(response[0].analysis.summary, ["inconsistent_depth"])
    self.assertEqual(response[0].analysis.coaching_feedback, ["Stay tight."])
    self.assertEqual(response[0].analysis.result_json["summary_flags"], ["inconsistent_depth"])
    self.assertNotIn("poseFrames", response[0].analysis.result_json)
    self.assertEqual(response[0].analysis.rep_data[0]["rep_index"], 1)
    self.assertEqual(response[0].analysis.result_json["rep_count"], 1)
    self.assertEqual(response[0].performed_reps, 7)
    self.assertEqual(response[0].load_value, 102.5)
    self.assertEqual(response[0].load_unit, "kg")

  def test_list_saved_videos_batch_loads_analysis_results(self) -> None:
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "thumbnail_path": None,
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      }
    ]
    repository.get_latest_analysis_results.return_value = {
      str(VIDEO_ID): {
        "id": str(VIDEO_ID),
        "video_id": str(VIDEO_ID),
        "model_version": "test-model",
        "created_at": "2026-05-24T12:00:00+00:00",
        "result_json": {
          "summary_flags": [],
          "coach_feedback": [],
          "reps": [{"rep_index": 1}],
          "rep_count": 1,
        },
      }
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.annotate_analysis_freshness", side_effect=lambda result, analysis: result),
    ):
      response = list_saved_videos(USER_ID)

    repository.get_latest_analysis_results.assert_called_once_with([str(VIDEO_ID)])
    repository.get_analysis_result.assert_not_called()
    self.assertEqual(response[0].analysis.result_json["rep_count"], 1)

  def test_list_saved_videos_page_returns_opaque_next_cursor(self) -> None:
    second_video_id = "22222222-2222-2222-2222-222222222222"
    repository = MagicMock()
    repository.list_saved_videos_page.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "thumbnail_path": None,
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      },
      {
        "id": second_video_id,
        "exercise_type": "back_squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/uploads/{second_video_id}.mov",
        "thumbnail_path": None,
        "save_state": "saved",
        "saved_at": "2026-05-23T12:00:00+00:00",
        "created_at": "2026-05-23T12:00:00+00:00",
      },
    ]
    repository.get_latest_analysis_results.return_value = {}
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      first_page = list_saved_videos_page("back_squat", 1, None, USER_ID)
      next_cursor = first_page.next_cursor
      self.assertIsNotNone(next_cursor)

      repository.list_saved_videos_page.return_value = []
      second_page = list_saved_videos_page("back_squat", 1, next_cursor, USER_ID)

    self.assertEqual(len(first_page.items), 1)
    self.assertIsNone(second_page.next_cursor)
    self.assertEqual(
      repository.list_saved_videos_page.call_args_list[0].kwargs,
      {"exercise_type": "back_squat", "offset": 0, "limit": 2},
    )
    self.assertEqual(
      repository.list_saved_videos_page.call_args_list[1].kwargs,
      {"exercise_type": "back_squat", "offset": 1, "limit": 2},
    )

  def test_list_saved_videos_page_rejects_malformed_cursor(self) -> None:
    repository = MagicMock()
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      list_saved_videos_page(None, 20, "not-a-valid-cursor", USER_ID)

    self.assertEqual(raised.exception.status_code, 400)
    repository.list_saved_videos_page.assert_not_called()

  def test_saved_overview_uses_batched_analysis_and_preview_signing_only(self) -> None:
    second_video_id = "22222222-2222-2222-2222-222222222222"
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "performed_reps": 7,
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      },
      {
        "id": second_video_id,
        "exercise_type": "bench press",
        "view_type": "front",
        "storage_path": f"{USER_ID}/uploads/{second_video_id}.mov",
        "thumbnail_path": None,
        "save_state": "saved",
        "saved_at": "2026-05-23T12:00:00+00:00",
        "created_at": "2026-05-23T12:00:00+00:00",
      },
    ]
    repository.get_latest_analysis_results.return_value = {
      str(VIDEO_ID): {
        "id": str(VIDEO_ID),
        "video_id": str(VIDEO_ID),
        "model_version": "test-model",
        "created_at": "2026-05-24T12:00:00+00:00",
        "result_json": {"rep_count": 3, "reps": []},
      },
      second_video_id: {
        "id": second_video_id,
        "video_id": second_video_id,
        "model_version": "test-model",
        "created_at": "2026-05-23T12:00:00+00:00",
        "result_json": {"reps": [{"rep_index": 1}, {"rep_index": 2}]},
      },
    }
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/thumb"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      patch("app.routes.videos.annotate_analysis_freshness", side_effect=lambda result, analysis: result),
    ):
      response = get_saved_video_overview(USER_ID)

    repository.get_latest_analysis_results.assert_called_once_with([str(VIDEO_ID), second_video_id])
    repository.get_analysis_result.assert_not_called()
    storage.create_signed_url.assert_called_once_with(f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg", expires_in=300)
    self.assertEqual(response.stats.total_saved, 2)
    self.assertEqual(response.stats.exercise_count, 2)
    self.assertEqual(response.stats.total_reps, 9)
    self.assertEqual(response.groups[0].exercise_type, "back_squat")
    self.assertEqual(response.groups[0].count, 1)

  def test_list_saved_videos_rejects_cross_user_thumbnail_before_signing(self) -> None:
    repository = MagicMock()
    repository.list_saved_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "exercise_type": "back_squat",
        "view_type": "side",
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "thumbnail_path": f"{OTHER_USER_ID}/thumbnails/{VIDEO_ID}.jpg",
        "save_state": "saved",
        "saved_at": "2026-05-24T12:00:00+00:00",
        "created_at": "2026-05-24T12:00:00+00:00",
      }
    ]
    repository.get_analysis_result.return_value = None
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      list_saved_videos(USER_ID)

    self.assertEqual(raised.exception.status_code, 403)
    storage.create_signed_url.assert_not_called()

  def test_delete_account_removes_storage_profile_and_auth_user(self) -> None:
    repository = MagicMock()
    repository.list_user_videos.return_value = [
      {
        "id": str(VIDEO_ID),
        "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "original_storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
        "playback_path": f"{USER_ID}/playback/{VIDEO_ID}.mp4",
        "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg",
      }
    ]
    video_storage = MagicMock()
    video_storage.list_storage_prefix.return_value = [f"{USER_ID}/exports/{VIDEO_ID}-export.mp4"]
    avatar_storage = MagicMock()
    archive_storage = MagicMock()
    admin_client = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", side_effect=[video_storage, avatar_storage, archive_storage]),
      patch("app.routes.videos.get_supabase_admin_client", return_value=admin_client),
    ):
      response = delete_account(USER_ID)

    video_storage.delete_storage_paths.assert_called_once()
    deleted_paths = video_storage.delete_storage_paths.call_args.args[0]
    self.assertIn(f"{USER_ID}/uploads/{VIDEO_ID}.mov", deleted_paths)
    self.assertIn(f"{USER_ID}/playback/{VIDEO_ID}.mp4", deleted_paths)
    self.assertIn(f"{USER_ID}/thumbnails/{VIDEO_ID}.jpg", deleted_paths)
    self.assertIn(f"{USER_ID}/exports/{VIDEO_ID}-export.mp4", deleted_paths)
    avatar_storage.delete_storage_prefix.assert_called_once_with(f"{USER_ID}/")
    archive_storage.delete_storage_prefix.assert_called_once_with(f"{USER_ID}/")
    admin_client.table.assert_called_once_with("profiles")
    admin_client.table.return_value.delete.return_value.eq.assert_called_once_with("id", USER_ID)
    admin_client.auth.admin.delete_user.assert_called_once_with(USER_ID)
    self.assertTrue(response.deleted)

  def test_playback_url_signs_video_only_on_demand(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
      "discarded_at": None,
    }
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/signed-video"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = get_video_playback_url(VIDEO_ID, USER_ID)

    storage.create_signed_url.assert_called_once_with(
      f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
      expires_in=300,
    )
    self.assertEqual(response.video_url, "https://example.test/signed-video")

  def test_playback_url_falls_back_to_original_when_playback_missing(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": None,
      "discarded_at": None,
    }
    storage = MagicMock()
    storage.create_signed_url.return_value = "https://example.test/signed-original"

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = get_video_playback_url(VIDEO_ID, USER_ID)

    storage.create_signed_url.assert_called_once_with(
      f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      expires_in=300,
    )
    self.assertEqual(response.video_url, "https://example.test/signed-original")

  def test_playback_url_falls_back_to_original_when_optimized_object_is_missing(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
      "discarded_at": None,
    }
    storage = MagicMock()
    storage.create_signed_url.side_effect = [
      RuntimeError("Object not found"),
      "https://example.test/signed-original",
    ]

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = get_video_playback_url(VIDEO_ID, USER_ID)

    self.assertEqual(
      storage.create_signed_url.call_args_list,
      [
        unittest.mock.call(
          f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
          expires_in=300,
        ),
        unittest.mock.call(
          f"{USER_ID}/uploads/{VIDEO_ID}.mov",
          expires_in=300,
        ),
      ],
    )
    self.assertEqual(response.video_url, "https://example.test/signed-original")

  def test_playback_url_reraises_optimized_error_when_original_signing_also_fails(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
      "discarded_at": None,
    }
    optimized_error = RuntimeError("Optimized object not found")
    storage = MagicMock()
    storage.create_signed_url.side_effect = [
      optimized_error,
      RuntimeError("Original object not found"),
    ]

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(RuntimeError) as raised,
    ):
      get_video_playback_url(VIDEO_ID, USER_ID)

    self.assertIs(raised.exception, optimized_error)
    self.assertEqual(
      storage.create_signed_url.call_args_list,
      [
        unittest.mock.call(
          f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
          expires_in=300,
        ),
        unittest.mock.call(
          f"{USER_ID}/uploads/{VIDEO_ID}.mov",
          expires_in=300,
        ),
      ],
    )

  def test_playback_url_rejects_cross_user_playback_path(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{OTHER_USER_ID}/playback/{VIDEO_ID}.mp4",
      "discarded_at": None,
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      get_video_playback_url(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 403)
    storage.create_signed_url.assert_not_called()

  def test_playback_url_rejects_cross_user_storage_path_fallback(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{OTHER_USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": None,
      "discarded_at": None,
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
      self.assertRaises(HTTPException) as raised,
    ):
      get_video_playback_url(VIDEO_ID, USER_ID)

    self.assertEqual(raised.exception.status_code, 403)
    storage.create_signed_url.assert_not_called()

  def test_save_video_only_updates_metadata(self) -> None:
    request = SaveVideoRequest(
      performed_reps=2,
      load_value=225.5,
      load_unit="lb",
    )
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "discarded_at": None,
    }
    repository.mark_saved.return_value = {
      "save_state": "saved",
      "performed_reps": 2,
      "load_value": 225.5,
      "load_unit": "lb",
    }

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = save_video(VIDEO_ID, request, USER_ID)

    repository.mark_saved.assert_called_once_with(
      str(VIDEO_ID),
      performed_reps=2,
      load_value=225.5,
      load_unit="lb",
    )
    self.assertEqual(response.save_state, "saved")
    self.assertEqual(response.performed_reps, 2)
    self.assertEqual(response.load_value, 225.5)
    self.assertEqual(response.load_unit, "lb")

  def test_save_video_accepts_zero_weight(self) -> None:
    request = SaveVideoRequest(
      performed_reps=1,
      load_value=0,
      load_unit="kg",
    )
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "discarded_at": None,
    }
    repository.mark_saved.return_value = {
      "save_state": "saved",
      "performed_reps": 1,
      "load_value": 0,
      "load_unit": "kg",
    }

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = save_video(VIDEO_ID, request, USER_ID)

    self.assertEqual(response.load_value, 0)

  def test_save_video_accepts_omitted_workout_details(self) -> None:
    request = SaveVideoRequest()
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "discarded_at": None,
    }
    repository.mark_saved.return_value = {
      "save_state": "saved",
      "performed_reps": None,
      "load_value": None,
      "load_unit": None,
    }

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = save_video(VIDEO_ID, request, USER_ID)

    repository.mark_saved.assert_called_once_with(
      str(VIDEO_ID),
      performed_reps=None,
      load_value=None,
      load_unit=None,
    )
    self.assertIsNone(response.performed_reps)
    self.assertIsNone(response.load_value)
    self.assertIsNone(response.load_unit)

  def test_save_video_request_validates_entered_workout_details(self) -> None:
    with self.assertRaises(ValidationError):
      SaveVideoRequest(performed_reps=0, load_value=225, load_unit="lb")
    with self.assertRaises(ValidationError):
      SaveVideoRequest(performed_reps=2, load_value=-1, load_unit="lb")
    with self.assertRaises(ValidationError):
      SaveVideoRequest(performed_reps=2, load_value=225, load_unit="stone")
    with self.assertRaises(ValidationError):
      SaveVideoRequest(performed_reps=2, load_value=225)
    with self.assertRaises(ValidationError):
      SaveVideoRequest(performed_reps=2, load_unit="lb")

  def test_discard_deletes_storage_and_marks_row_discarded(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4",
      "original_storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "thumbnail_path": f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg",
    }
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = discard_video(VIDEO_ID, USER_ID)

    storage.delete_storage_path.assert_any_call(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    storage.delete_storage_path.assert_any_call(f"{USER_ID}/playback/{VIDEO_ID}-h264-720p-v1.mp4")
    storage.delete_storage_path.assert_any_call(f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg")
    storage.list_storage_prefix.assert_called_once_with(f"{USER_ID}/exports/{VIDEO_ID}-")
    storage.delete_storage_prefix.assert_not_called()
    repository.mark_discarded.assert_called_once_with(str(VIDEO_ID))
    repository.delete_video_with_analysis.assert_not_called()
    self.assertTrue(response.discarded)

  def test_discard_skips_storage_paths_outside_user_folder(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"other-user/playback/{VIDEO_ID}.mp4",
      "thumbnail_path": f"other-user/thumbnails/{VIDEO_ID}.jpg",
    }
    storage = MagicMock()
    storage.list_storage_prefix.return_value = []

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = discard_video(VIDEO_ID, USER_ID)

    storage.delete_storage_path.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    repository.mark_discarded.assert_called_once_with(str(VIDEO_ID))
    self.assertTrue(response.discarded)

  def test_mark_upload_failed_deletes_owned_storage_and_marks_failed(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
      "playback_path": f"{OTHER_USER_ID}/playback/{VIDEO_ID}.mp4",
      "thumbnail_path": None,
    }
    repository.update_video.return_value = {"status": "failed"}
    storage = MagicMock()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = mark_upload_failed(VIDEO_ID, USER_ID)

    storage.delete_storage_path.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    update_fields = repository.update_video.call_args.args[1]
    self.assertEqual(update_fields["status"], "failed")
    self.assertEqual(update_fields["is_saved"], False)
    self.assertEqual(response.status, "failed")

  def test_old_model_result_is_marked_stale(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": "mediapipe-pose-v2-depth-score",
        "result_json": {
          "model_version": "mediapipe-pose-v2-depth-score",
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertEqual(annotated["expected_model_version"], DEFAULT_MODEL_VERSION)
    self.assertEqual(annotated["diagnostics"]["analysis_stale"], True)

  def test_current_model_missing_pose_payload_is_marked_incomplete(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "reps": [
            {
              "rep_index": 1,
              "depth_score": 0.4,
              "flags": ["insufficient_depth"],
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertTrue(annotated["analysis_incomplete"])
    self.assertTrue(annotated["diagnostics"]["analysis_incomplete"])

  def test_current_model_complete_pose_payload_is_current(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "pose_backend": "mediapipe",
          "landmark_model": "mediapipe_pose_33",
          "reps": [
            {
              "rep_index": 1,
              "depth_status": "hit_depth",
              "selected_side": "left",
              "selected_source": "mediapipe",
              "depth_evidence": {
                "hip_knee_delta": -0.02,
                "parallel_score": 1.0,
                "selected_side": "left",
                "selected_source": "mediapipe",
                "estimated_hip_crease_y": 0.61,
                "estimated_knee_top_y": 0.58,
                "depth_delta_px": 22.0,
                "depth_tolerance_px": 14.0,
                "depth_classification": "hit_depth",
                "depth_reason": "depth_met",
              },
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertTrue(analysis_is_current(analysis))
    self.assertFalse(annotated["analysis_stale"])
    self.assertFalse(annotated["analysis_incomplete"])

  def test_front_tracking_payload_does_not_require_side_view_depth_fields(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "pose_backend": "mediapipe",
          "landmark_model": "mediapipe_pose_33",
          "analysisMode": "front_squat_tracking_v1",
          "analysisCapabilities": {"depthAssessment": False},
          "reps": [
            {
              "rep_index": 1,
              "startTime": 0.5,
              "endTime": 2.0,
              "confidence": 0.9,
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertTrue(analysis_is_current(analysis))
    self.assertFalse(annotated["analysis_stale"])
    self.assertFalse(annotated["analysis_incomplete"])

  def test_current_model_missing_new_depth_debug_fields_is_marked_incomplete(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "pose_backend": "mediapipe",
          "landmark_model": "mediapipe_pose_33",
          "reps": [
            {
              "rep_index": 1,
              "depth_status": "hit_depth",
              "depth_evidence": {
                "hip_knee_delta": -0.02,
                "parallel_score": 1.0,
              },
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertTrue(annotated["analysis_incomplete"])


if __name__ == "__main__":
  unittest.main()
