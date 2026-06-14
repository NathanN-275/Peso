from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from app.analysis.versioning import annotate_analysis_freshness, analysis_is_current
from app.routes.videos import (
  discard_video,
  get_storage_usage,
  get_video_playback_url,
  list_saved_videos,
  queue_analysis,
  save_video,
)
from app.services.config import DEFAULT_MODEL_VERSION, get_settings


VIDEO_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = "33333333-3333-3333-3333-333333333333"


class VideoRoutesTest(unittest.TestCase):
  def tearDown(self) -> None:
    get_settings.cache_clear()

  def test_queue_analysis_queues_uploaded_owned_video(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "uploaded",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    repository.queue_owned_video_if_status.return_value = {"status": "queued"}
    storage = MagicMock()
    background_tasks = BackgroundTasks()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, background_tasks, USER_ID)

    storage.validate_video_object.assert_called_once_with(f"{USER_ID}/uploads/{VIDEO_ID}.mov")
    repository.queue_owned_video_if_status.assert_called_once_with(
      str(VIDEO_ID),
      USER_ID,
      ("uploaded", "failed"),
    )
    self.assertEqual(response.status, "queued")
    self.assertEqual(len(background_tasks.tasks), 1)

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

    with patch("app.routes.videos.StorageQuotaService", return_value=quota_service):
      response = get_storage_usage(50, USER_ID)

    quota_service.get_usage.assert_called_once_with(50)
    self.assertEqual(response.projected_peak_bytes, 201)
    self.assertFalse(response.blocked)

  def test_queue_analysis_returns_idempotent_in_progress_status(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "status": "processing",
      "storage_path": f"{USER_ID}/uploads/{VIDEO_ID}.mov",
    }
    storage = MagicMock()
    background_tasks = BackgroundTasks()

    with (
      patch("app.routes.videos.VideoRepository", return_value=repository),
      patch("app.routes.videos.StorageService", return_value=storage),
    ):
      response = queue_analysis(VIDEO_ID, background_tasks, USER_ID)

    storage.validate_video_object.assert_not_called()
    repository.queue_owned_video_if_status.assert_not_called()
    self.assertEqual(response.status, "processing")
    self.assertEqual(len(background_tasks.tasks), 0)

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
      queue_analysis(VIDEO_ID, BackgroundTasks(), USER_ID)

    storage.validate_video_object.assert_not_called()
    repository.queue_owned_video_if_status.assert_not_called()
    self.assertEqual(raised.exception.status_code, 409)

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
      queue_analysis(VIDEO_ID, BackgroundTasks(), USER_ID)

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

    storage.create_signed_url.assert_called_once_with(f"{USER_ID}/thumbnails/{VIDEO_ID}-thumb-v3.jpg")
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
    self.assertEqual(response[0].analysis.rep_data, [])

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

  def test_save_video_only_updates_metadata(self) -> None:
    repository = MagicMock()
    repository.require_owned_video.return_value = {
      "id": str(VIDEO_ID),
      "user_id": USER_ID,
      "discarded_at": None,
    }
    repository.mark_saved.return_value = {"save_state": "saved"}

    with patch("app.routes.videos.VideoRepository", return_value=repository):
      response = save_video(VIDEO_ID, USER_ID)

    repository.mark_saved.assert_called_once_with(str(VIDEO_ID))
    self.assertEqual(response.save_state, "saved")

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

  def test_old_model_result_is_marked_stale(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
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

  def test_current_model_missing_new_depth_debug_fields_is_marked_incomplete(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
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
