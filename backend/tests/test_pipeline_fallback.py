from __future__ import annotations

import unittest
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.analysis.pose_fallback import analysis_needs_pose_fallback
from app.analysis.pose_estimator import PoseEstimatorConfig


class PipelineFallbackTest(unittest.TestCase):
  def _estimation(self) -> dict:
    return {
      "frames": [{"timestamp_ms": 0, "landmarks": {}}],
      "fps": 12,
      "duration_ms": 1000,
      "frame_width": 640,
      "frame_height": 480,
      "frame_count": 12,
      "original_frame_width": 640,
      "original_frame_height": 480,
      "processed_frame_width": 640,
      "processed_frame_height": 480,
      "sampled_frame_count": 12,
      "pose_frame_count": 12,
      "target_fps": 12,
      "frame_step": 1,
      "pose_model_complexity": 2,
      "pose_backend": "mediapipe",
      "requested_pose_backend": "hybrid",
      "fallback_model": None,
      "fallback_frame_count": 0,
      "landmark_model": "mediapipe_pose_33",
      "processing_duration_ms": 20,
    }

  def _rtmpose_estimation(self) -> dict:
    estimation = self._estimation()
    estimation.update(
      {
        "pose_backend": "rtmpose",
        "fallback_model": "rtmpose",
        "fallback_frame_count": 12,
        "landmark_model": "rtmpose_coco17_mapped_to_mediapipe_33",
      }
    )
    return estimation

  def _uncertain_result(self) -> dict:
    return {
      "video_id": "video-1",
      "exercise": "squat",
      "view": "side",
      "rep_count": 1,
      "reps": [
        {
          "rep_index": 1,
          "depth_confidence": 0.2,
          "depth_status": "uncertain_depth",
          "depth_components": {},
          "flags": ["low_depth_confidence"],
        }
      ],
      "summary_flags": ["Depth confidence was limited"],
      "coach_feedback": [],
      "poseFrames": [],
      "diagnostics": {
        "depth_status_counts": {
          "uncertain_depth_count": 1,
        },
        "quality_flags": [],
      },
    }

  def _depth_result(self, *, status: str, delta_px: float, confidence: float = 0.9) -> dict:
    flags = ["insufficient_depth"] if status == "insufficient_depth" else []
    return {
      "video_id": "video-1",
      "exercise": "squat",
      "view": "side",
      "rep_count": 1,
      "reps": [
        {
          "rep_index": 1,
          "depth_score": 0.9 if status == "hit_depth" else 0.2,
          "depth_confidence": confidence,
          "depth_status": status,
          "depth_components": {
            "depth_delta_px": delta_px,
            "depth_tolerance_px": 8.0,
            "depth_classification": status,
            "depth_reason": "depth_met" if status == "hit_depth" else "hip_crease_above_knee_top",
          },
          "depth_evidence": {
            "depthDeltaPx": delta_px,
            "depthTolerancePx": 8.0,
            "depthClassification": status,
            "depthReason": "depth_met" if status == "hit_depth" else "hip_crease_above_knee_top",
          },
          "torso_angle_change": 0.0,
          "flags": flags,
        }
      ],
      "summary_flags": ["Insufficient depth"] if flags else [],
      "summaryFlags": ["Insufficient depth"] if flags else [],
      "coach_feedback": [],
      "coachingFeedback": [],
      "poseFrames": [],
      "diagnostics": {
        "depth_status_counts": {
          "hit_depth_count": 1 if status == "hit_depth" else 0,
          "insufficient_depth_count": 1 if status == "insufficient_depth" else 0,
          "uncertain_depth_count": 0,
        },
        "quality_flags": [],
        "quality_score": 0.8,
      },
    }

  def _repository(self) -> MagicMock:
    repository = MagicMock()
    repository.get_video.return_value = {
      "id": "video-1",
      "storage_path": "videos/video-1.mov",
      "exercise_type": "squat",
      "view_type": "side",
    }
    return repository

  def _import_pipeline(self):
    fake_fastapi = SimpleNamespace(
      HTTPException=Exception,
      status=SimpleNamespace(
        HTTP_400_BAD_REQUEST=400,
        HTTP_404_NOT_FOUND=404,
        HTTP_409_CONFLICT=409,
      ),
    )
    fake_supabase = SimpleNamespace(Client=object, create_client=MagicMock())
    with patch.dict(sys.modules, {"fastapi": fake_fastapi, "supabase": fake_supabase}):
      from app.analysis import pipeline

    sys.modules[pipeline.__name__] = pipeline
    return pipeline

  def test_squat_variations_use_squat_analyzer(self) -> None:
    pipeline = self._import_pipeline()

    for exercise_type in ["squat", "front squat", "zercher squat", "box squat", "goblet squat"]:
      with self.subTest(exercise_type=exercise_type):
        analyzer = MagicMock()
        analyzer.analyze.return_value = {
          "video_id": "video-1",
          "exercise": exercise_type,
          "view": "side",
          "rep_count": 0,
          "reps": [],
        }

        with patch("app.analysis.pipeline.SquatAnalyzer", return_value=analyzer):
          result = pipeline._analyze_squat_result(
            video_id="video-1",
            video={
              "id": "video-1",
              "exercise_type": exercise_type,
              "view_type": "side",
            },
            estimation=self._estimation(),
          )

        self.assertFalse(result.get("analysis_limited", False))
        analyzer.analyze.assert_called_once()
        self.assertEqual(analyzer.analyze.call_args.kwargs["exercise_type"], exercise_type)

  def test_non_squat_variation_remains_limited(self) -> None:
    pipeline = self._import_pipeline()

    result = pipeline._analyze_squat_result(
      video_id="video-1",
      video={
        "id": "video-1",
        "exercise_type": "bench press",
        "view_type": "side",
      },
      estimation=self._estimation(),
    )

    self.assertTrue(result["analysis_limited"])

  def test_clean_analysis_does_not_trigger_fallback(self) -> None:
    self.assertIsNone(
      analysis_needs_pose_fallback(
        {
          "diagnostics": {
            "quality_flags": [],
            "depth_status_counts": {
              "hit_depth_count": 3,
              "uncertain_depth_count": 0,
            },
            "pose_validation": {
              "rejected_landmark_count": 0,
              "occluded_landmark_count": 0,
            },
          },
          "reps": [
            {
              "depth_confidence": 0.8,
              "depth_components": {},
            }
          ],
        }
      )
    )

  def test_plate_occlusion_triggers_fallback(self) -> None:
    reason = analysis_needs_pose_fallback(
      {
        "diagnostics": {
          "quality_flags": ["plate_rack_occlusion_suspected"],
        },
        "reps": [],
      }
    )

    self.assertEqual(reason, "plate_rack_occlusion_suspected")

  def test_uncertain_depth_triggers_fallback(self) -> None:
    reason = analysis_needs_pose_fallback(
      {
        "diagnostics": {
          "depth_status_counts": {
            "uncertain_depth_count": 1,
          },
        },
        "reps": [],
      }
    )

    self.assertEqual(reason, "uncertain_depth")

  def test_low_bottom_confidence_triggers_fallback(self) -> None:
    reason = analysis_needs_pose_fallback(
      {
        "diagnostics": {},
        "reps": [
          {
            "depth_confidence": 0.2,
            "depth_components": {},
          }
        ],
      }
    )

    self.assertEqual(reason, "low_bottom_depth_confidence")

  def test_analyze_records_recommended_fallback_when_disabled(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    estimator = MagicMock()
    estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=False)
    estimator.run.return_value = self._estimation()

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", return_value=estimator) as estimator_factory,
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._uncertain_result()),
    ):
      pipeline.analyze_video("video-1")

    estimator_factory.assert_called_once()
    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["fallback_recommended"])
    self.assertEqual(saved_result["fallback_model"], "rtmpose")
    self.assertEqual(saved_result["fallback_reason"], "uncertain_depth")
    self.assertFalse(saved_result["fallback_attempted"])
    self.assertFalse(saved_result["fallback_triggered"])
    self.assertEqual(saved_result["fallback_unavailable_reason"], "fallback_disabled")
    self.assertEqual(saved_result["diagnostics"]["fallback_unavailable_reason"], "fallback_disabled")

  def test_analyze_records_missing_dependency_when_rtmpose_fallback_fails(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    mediapipe_estimator = MagicMock()
    mediapipe_estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    mediapipe_estimator.run.return_value = self._estimation()
    rtmpose_estimator = MagicMock()
    rtmpose_estimator.run.side_effect = RuntimeError("RTMPose fallback requires the optional rtmlib dependency.")

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", side_effect=[mediapipe_estimator, rtmpose_estimator]),
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._uncertain_result()),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["fallback_recommended"])
    self.assertEqual(saved_result["fallback_model"], "rtmpose")
    self.assertEqual(saved_result["fallback_reason"], "uncertain_depth")
    self.assertTrue(saved_result["fallback_attempted"])
    self.assertFalse(saved_result["fallback_triggered"])
    self.assertEqual(saved_result["fallback_unavailable_reason"], "fallback_dependency_missing")
    self.assertIn("rtmlib", saved_result["fallback_error"])

  def test_analyze_records_successful_rtmpose_fallback(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    mediapipe_estimator = MagicMock()
    mediapipe_estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    mediapipe_estimator.run.return_value = self._estimation()
    rtmpose_estimator = MagicMock()
    rtmpose_estimator.run.return_value = self._rtmpose_estimation()

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", side_effect=[mediapipe_estimator, rtmpose_estimator]),
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._uncertain_result()),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["fallback_recommended"])
    self.assertTrue(saved_result["fallback_attempted"])
    self.assertTrue(saved_result["fallback_triggered"])
    self.assertEqual(saved_result["fallback_model"], "rtmpose")
    self.assertEqual(saved_result["fallback_frame_count"], 12)
    self.assertEqual(saved_result["pose_backend"], "rtmpose")
    self.assertEqual(saved_result["landmark_model"], "rtmpose_coco17_mapped_to_mediapipe_33")

  def test_analyze_records_attempted_fallback_when_primary_result_is_retained(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    mediapipe_estimator = MagicMock()
    mediapipe_estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    mediapipe_estimator.run.return_value = self._estimation()
    rtmpose_estimator = MagicMock()
    rtmpose_estimator.run.return_value = self._rtmpose_estimation()
    fallback_result = self._uncertain_result()
    fallback_result["reps"][0]["depth_confidence"] = 0.0

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", side_effect=[mediapipe_estimator, rtmpose_estimator]),
      patch(
        "app.analysis.pipeline._analyze_squat_result",
        side_effect=[self._uncertain_result(), fallback_result],
      ),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["fallback_recommended"])
    self.assertTrue(saved_result["fallback_attempted"])
    self.assertFalse(saved_result["fallback_triggered"])
    self.assertEqual(saved_result["fallback_frame_count"], 12)
    self.assertEqual(saved_result["pose_backend"], "mediapipe")
    self.assertEqual(saved_result["diagnostics"]["fallback_selection"], "primary_retained")

  def test_analyze_attaches_barbell_path_for_side_squat(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    estimator = MagicMock()
    estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    estimator.run.return_value = self._estimation()
    tracker = MagicMock()
    tracker.track.return_value = {
      "barbellPath": {
        "available": True,
        "target": "near_plate_collar_center",
        "source": "opencv_circle_tracker",
        "coverage": 1.0,
        "points": [{"time": 0.0, "x": 0.5, "y": 0.25, "confidence": 0.9}],
      },
      "diagnostics": {
        "available": True,
        "target": "near_plate_collar_center",
        "source": "opencv_circle_tracker",
        "coverage": 1.0,
      },
    }

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", return_value=estimator),
      patch("app.analysis.pipeline.BarbellTracker", return_value=tracker),
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._depth_result(status="hit_depth", delta_px=12.0)),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["barbellPath"]["available"])
    self.assertEqual(saved_result["diagnostics"]["barbell_tracking"]["source"], "opencv_circle_tracker")
    tracker.track.assert_called_once()

  def test_analyze_skips_barbell_path_for_non_side_video(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    repository.get_video.return_value["view_type"] = "front"
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    estimator = MagicMock()
    estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    estimator.run.return_value = self._estimation()
    tracker = MagicMock()

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", return_value=estimator),
      patch("app.analysis.pipeline.BarbellTracker", return_value=tracker),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertNotIn("barbellPath", saved_result)
    tracker.track.assert_not_called()

  def test_model_disagreement_downgrades_depth_to_uncertain(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    mediapipe_estimator = MagicMock()
    mediapipe_estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    mediapipe_estimator.run.return_value = self._estimation()
    rtmpose_estimator = MagicMock()
    rtmpose_estimator.run.return_value = self._rtmpose_estimation()
    primary_result = self._depth_result(status="insufficient_depth", delta_px=-22.0)
    primary_result["diagnostics"]["quality_flags"] = ["excessive_landmark_jitter"]
    fallback_result = self._depth_result(status="hit_depth", delta_px=18.0)

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", side_effect=[mediapipe_estimator, rtmpose_estimator]),
      patch(
        "app.analysis.pipeline._analyze_squat_result",
        side_effect=[primary_result, fallback_result],
      ),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    rep = saved_result["reps"][0]
    self.assertEqual(rep["depth_status"], "uncertain_depth")
    self.assertEqual(rep["depth_reason"], "model_disagreement")
    self.assertIn("low_depth_confidence", rep["flags"])
    self.assertNotIn("insufficient_depth", rep["flags"])
    self.assertTrue(saved_result["diagnostics"]["pose_model_disagreement"])
    self.assertEqual(saved_result["diagnostics"]["depth_status_counts"]["uncertain_depth_count"], 1)


if __name__ == "__main__":
  unittest.main()
