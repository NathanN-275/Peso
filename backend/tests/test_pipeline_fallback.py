from __future__ import annotations

import unittest
import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.analysis.pose_fallback import analysis_needs_pose_fallback
from app.analysis.pose_estimator import PoseEstimatorConfig
from app.analysis.tracking_core import Detection, DetectionFrame, NormalizedPoint


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
          "startTime": 0.5,
          "bottomTimestampMs": 1200,
          "endTime": 2.0,
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
        "selected_side": "left",
        "pose_validation": {
          "selected_side": "left",
        },
        "quality_flags": [],
        "quality_score": 0.8,
      },
    }

  def _repository(self) -> MagicMock:
    repository = MagicMock()
    repository.get_video.return_value = {
      "id": "video-1",
      "user_id": "33333333-3333-3333-3333-333333333333",
      "storage_path": "33333333-3333-3333-3333-333333333333/uploads/video-1.mov",
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
    fake_httpx = SimpleNamespace(Client=MagicMock(), Limits=MagicMock())
    fake_supabase = SimpleNamespace(Client=object, create_client=MagicMock())
    with patch.dict(sys.modules, {"fastapi": fake_fastapi, "httpx": fake_httpx, "supabase": fake_supabase}):
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

  def test_front_squat_variations_use_front_tracking_analyzer(self) -> None:
    pipeline = self._import_pipeline()

    for exercise_type in ["squat", "front squat", "zercher squat", "box squat", "goblet squat"]:
      with self.subTest(exercise_type=exercise_type):
        analyzer = MagicMock()
        analyzer.analyze.return_value = {
          "video_id": "video-1",
          "exercise": exercise_type,
          "view": "front",
          "analysisMode": "front_squat_tracking_v1",
          "rep_count": 0,
          "reps": [],
        }

        with patch("app.analysis.pipeline.FrontSquatAnalyzer", return_value=analyzer):
          result = pipeline._analyze_squat_result(
            video_id="video-1",
            video={
              "id": "video-1",
              "exercise_type": exercise_type,
              "view_type": "front",
            },
            estimation=self._estimation(),
          )

        self.assertEqual(result["analysisMode"], "front_squat_tracking_v1")
        analyzer.analyze.assert_called_once()
        self.assertEqual(analyzer.analyze.call_args.kwargs["exercise_type"], exercise_type)

  def test_front_visible_collar_gate_fails_closed_without_strong_identity_evidence(self) -> None:
    pipeline = self._import_pipeline()
    tracking = {
      "barbellPath": {
        "available": True,
        "target": "near_plate_collar_center",
        "coverage": 0.8,
        "points": [{"time": 0.0, "x": 0.5, "y": 0.3}],
      },
      "diagnostics": {
        "available": True,
        "coverage": 0.8,
        "initialization_confirmed": True,
        "collar_geometry_valid": False,
        "collar_candidate_count": 8,
        "final_bar_confidence": 0.9,
      },
    }

    gated = pipeline._gate_front_visible_collar_tracking(tracking)

    self.assertFalse(gated["barbellPath"]["available"])
    self.assertEqual(gated["barbellPath"]["target"], "visible_collar")
    self.assertEqual(gated["barbellPath"]["points"], [])

  def test_front_visible_collar_gate_publishes_confirmed_path(self) -> None:
    pipeline = self._import_pipeline()
    tracking = {
      "barbellPath": {
        "available": True,
        "coverage": 0.8,
        "points": [{"time": 0.0, "x": 0.5, "y": 0.3}],
      },
      "diagnostics": {
        "available": True,
        "coverage": 0.8,
        "initialization_confirmed": True,
        "collar_geometry_valid": True,
        "collar_candidate_count": 8,
        "final_bar_confidence": 0.9,
      },
    }

    gated = pipeline._gate_front_visible_collar_tracking(tracking)

    self.assertTrue(gated["barbellPath"]["available"])
    self.assertEqual(gated["barbellPath"]["target"], "visible_collar")
    self.assertTrue(gated["diagnostics"]["front_visible_collar_confirmed"])

  def test_pin_selected_side_is_passed_to_squat_analysis(self) -> None:
    pipeline = self._import_pipeline()
    estimation = self._estimation()
    estimation["tracking_assistance"] = {
      "actualMode": "pin_assisted",
      "selectedSide": "right",
    }
    analyzer = MagicMock()
    analyzer.analyze.return_value = {"reps": [], "diagnostics": {}}

    with patch("app.analysis.pipeline.SquatAnalyzer", return_value=analyzer):
      pipeline._analyze_squat_result(
        video_id="video-1",
        video={
          "id": "video-1",
          "exercise_type": "squat",
          "view_type": "side",
        },
        estimation=estimation,
      )

    self.assertEqual(
      analyzer.analyze.call_args.kwargs["selected_side_override"],
      "right",
    )

  def test_pipeline_passes_repaired_pose_stream_to_squat_analyzer(self) -> None:
    pipeline = self._import_pipeline()

    def point(x: float, y: float, visibility: float = 0.95) -> dict:
      return {"x": x, "y": y, "z": 0.0, "visibility": visibility}

    def pose_frame(timestamp_ms: int, knee: dict | None = None) -> dict:
      return {
        "timestamp_ms": timestamp_ms,
        "source_frame_index": timestamp_ms // 50,
        "landmarks": {
          "left_shoulder": point(0.40, 0.25),
          "left_hip": point(0.45, 0.55),
          "left_knee": knee or point(0.52, 0.72),
          "left_ankle": point(0.50, 0.92),
          "right_shoulder": point(0.45, 0.25, 0.35),
          "right_hip": point(0.50, 0.55, 0.35),
          "right_knee": point(0.57, 0.72, 0.35),
          "right_ankle": point(0.55, 0.92, 0.35),
        },
      }

    estimation = self._estimation()
    estimation["frames"] = [
      pose_frame(0),
      pose_frame(50, point(0.84, 0.18, 0.05)),
      pose_frame(100),
    ]
    repaired_estimation = pipeline._apply_pose_repair(estimation)
    analyzer = MagicMock()
    analyzer.analyze.return_value = {"reps": [], "diagnostics": {}}

    with patch("app.analysis.pipeline.SquatAnalyzer", return_value=analyzer):
      pipeline._analyze_squat_result(
        video_id="video-1",
        video={"id": "video-1", "exercise_type": "squat", "view_type": "side"},
        estimation=repaired_estimation,
      )

    analyzed_frames = analyzer.analyze.call_args.kwargs["frames"]
    repaired_knee = analyzed_frames[1]["landmarks"]["left_knee"]
    self.assertEqual(repaired_knee["accepted_source"], "pose_repair_interpolated")
    self.assertIsNotNone(analyzer.analyze.call_args.kwargs["pose_validation_override"])
    self.assertTrue(analyzer.analyze.call_args.kwargs["pose_repair_diagnostics"]["enabled"])

  def test_candidate_yolo_detections_reach_pose_repair_before_analysis(self) -> None:
    pipeline = self._import_pipeline()

    def point(x: float, y: float, visibility: float = 0.95) -> dict:
      return {"x": x, "y": y, "z": 0.0, "visibility": visibility}

    def pose_frame(timestamp_ms: int) -> dict:
      return {
        "timestamp_ms": timestamp_ms,
        "source_frame_index": timestamp_ms // 50,
        "landmarks": {
          "left_shoulder": point(0.40, 0.25),
          "left_hip": point(0.45, 0.55),
          "left_knee": point(0.52, 0.72),
          "left_ankle": point(0.50, 0.92),
          "right_shoulder": point(0.45, 0.25, 0.35),
          "right_hip": point(0.50, 0.55, 0.35),
          "right_knee": point(0.57, 0.72, 0.35),
          "right_ankle": point(0.55, 0.92, 0.35),
        },
      }

    estimation = self._estimation()
    estimation["frames"] = [pose_frame(0), pose_frame(50), pose_frame(100)]
    yolo_detections = [DetectionFrame(
      source_frame_index=1,
      time=0.05,
      detections=(Detection(
        kind="rack_upright",
        confidence=0.95,
        center=NormalizedPoint(0.52, 0.72),
        bbox=(0.50, 0.70, 0.54, 0.74),
      ),),
    )]
    with patch.dict(os.environ, {"YOLO_TRACKING_MODE": "candidate"}, clear=True), patch(
      "app.analysis.pipeline.detect_tracking_objects",
      return_value=(yolo_detections, {"available": True, "detection_frame_count": 1}),
    ):
      prepared = pipeline._run_yolo_tracking_prepass(
        file_path="/tmp/source.mov",
        video={"exercise_type": "squat", "view_type": "side"},
        estimation=estimation,
      )
      repaired = pipeline._apply_pose_repair(prepared)

    knee = repaired["frames"][1]["landmarks"]["left_knee"]
    self.assertEqual(knee["accepted_source"], "pose_repair_interpolated")
    self.assertEqual(repaired["pose_repair"]["detector_occlusion_count"], 1)

  def test_shadow_yolo_diagnostics_do_not_change_pose_repair_input(self) -> None:
    pipeline = self._import_pipeline()
    estimation = self._estimation()
    point = lambda x, y, visibility=0.95: {"x": x, "y": y, "z": 0.0, "visibility": visibility}
    estimation["frames"] = [{
      "timestamp_ms": 0,
      "source_frame_index": 0,
      "landmarks": {
        "left_shoulder": point(0.40, 0.25),
        "left_hip": point(0.45, 0.55),
        "left_knee": point(0.52, 0.72),
        "left_ankle": point(0.50, 0.92),
        "right_shoulder": point(0.45, 0.25, 0.35),
        "right_hip": point(0.50, 0.55, 0.35),
        "right_knee": point(0.57, 0.72, 0.35),
        "right_ankle": point(0.55, 0.92, 0.35),
      },
    }]
    yolo_detections = [DetectionFrame(
      source_frame_index=0,
      time=0.0,
      detections=(Detection(
        kind="rack_upright",
        confidence=0.95,
        center=NormalizedPoint(0.5, 0.5),
        bbox=(0.0, 0.0, 1.0, 1.0),
      ),),
    )]
    with patch.dict(os.environ, {"YOLO_TRACKING_MODE": "shadow"}, clear=True), patch(
      "app.analysis.pipeline.detect_tracking_objects",
      return_value=(yolo_detections, {"available": True, "detection_frame_count": 1}),
    ):
      prepared = pipeline._run_yolo_tracking_prepass(
        file_path="/tmp/source.mov",
        video={"exercise_type": "squat", "view_type": "side"},
        estimation=estimation,
      )
      repaired = pipeline._apply_pose_repair(prepared)

    self.assertEqual(repaired["yolo_tracking"]["mode"], "shadow")
    self.assertEqual(repaired["pose_repair"]["detector_occlusion_count"], 0)

  def test_pressing_variation_uses_pressing_analyzer(self) -> None:
    pipeline = self._import_pipeline()
    analyzer = MagicMock()
    analyzer.analyze.return_value = {
      "video_id": "video-1",
      "exercise": "bench press",
      "view": "side",
      "rep_count": 0,
      "reps": [],
    }

    with patch("app.analysis.pipeline.PressingAnalyzer", return_value=analyzer):
      result = pipeline._analyze_squat_result(
        video_id="video-1",
        video={
          "id": "video-1",
          "exercise_type": "bench press",
          "view_type": "side",
        },
        estimation=self._estimation(),
      )

    self.assertFalse(result.get("analysis_limited", False))
    analyzer.analyze.assert_called_once()

  def test_unsupported_variation_remains_limited(self) -> None:
    pipeline = self._import_pipeline()

    result = pipeline._analyze_squat_result(
      video_id="video-1",
      video={
        "id": "video-1",
        "exercise_type": "deadlift",
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
    reported_stages: list[str] = []

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", return_value=estimator) as estimator_factory,
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._uncertain_result()),
    ):
      pipeline.analyze_video("video-1", progress_callback=reported_stages.append)

    estimator_factory.assert_called_once()
    saved_result = repository.save_analysis_result.call_args.args[2]
    self.assertTrue(saved_result["fallback_recommended"])
    self.assertEqual(saved_result["fallback_model"], "rtmpose")
    self.assertEqual(saved_result["fallback_reason"], "uncertain_depth")
    self.assertFalse(saved_result["fallback_attempted"])
    self.assertFalse(saved_result["fallback_triggered"])
    self.assertEqual(saved_result["fallback_unavailable_reason"], "fallback_disabled")
    self.assertEqual(saved_result["diagnostics"]["fallback_unavailable_reason"], "fallback_disabled")
    self.assertEqual(
      reported_stages,
      ["downloading", "pose", "barbell_tracking", "saving"],
    )

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
    self.assertEqual(tracker.track.call_args.kwargs["selected_side"], "left")
    self.assertEqual(
      tracker.track.call_args.kwargs["rep_windows"],
      [{"rep_index": 1, "start": 0.5, "bottom": 1.2, "end": 2.0}],
    )

  def test_analyze_saves_stage_timings_and_completes_before_asset_finalization(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    estimator = MagicMock()
    estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    estimator.run.return_value = self._estimation()
    call_order: list[str] = []

    def save_analysis_result(*_args) -> None:
      call_order.append("save_analysis_result")

    def update_video(_video_id: str, payload: dict) -> None:
      if payload.get("status"):
        call_order.append(f"status:{payload['status']}")

    def finalize_assets(**_kwargs) -> None:
      call_order.append("finalize_storage_assets")

    repository.save_analysis_result.side_effect = save_analysis_result
    repository.update_video.side_effect = update_video

    with (
      patch("app.analysis.pipeline.VideoRepository", return_value=repository),
      patch("app.analysis.pipeline.StorageService", return_value=storage),
      patch("app.analysis.pipeline.get_settings", return_value=SimpleNamespace(model_version="test-model")),
      patch("app.analysis.pipeline.PoseEstimator", return_value=estimator),
      patch("app.analysis.pipeline._attach_barbell_tracking"),
      patch("app.analysis.pipeline._refresh_pressing_result_from_barbell", side_effect=lambda result, **_kwargs: result),
      patch("app.analysis.pipeline._finalize_storage_assets", side_effect=finalize_assets),
      patch("app.analysis.pipeline._analyze_squat_result", return_value=self._depth_result(status="hit_depth", delta_px=12.0)),
    ):
      pipeline.analyze_video("video-1")

    saved_result = repository.save_analysis_result.call_args.args[2]
    timings = saved_result["analysis_stage_timings_ms"]
    self.assertIn("download_source", timings)
    self.assertIn("pose_estimation", timings)
    self.assertIn("pin_assistance", timings)
    self.assertIn("exercise_metrics", timings)
    self.assertIn("barbell_tracking", timings)
    self.assertIn("analysis_payload_ready", timings)
    self.assertEqual(saved_result["diagnostics"]["analysis_stage_timings_ms"], timings)
    self.assertEqual(saved_result["video_metadata"]["analysis_stage_timings_ms"], timings)
    self.assertLess(call_order.index("save_analysis_result"), call_order.index("status:completed"))
    self.assertLess(call_order.index("status:completed"), call_order.index("finalize_storage_assets"))

  def test_analyze_skips_barbell_path_for_unsupported_non_side_video(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    repository.get_video.return_value["view_type"] = "front"
    repository.get_video.return_value["exercise_type"] = "deadlift"
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

  def test_analyze_attaches_pressing_bar_center_for_front_view(self) -> None:
    pipeline = self._import_pipeline()
    repository = self._repository()
    repository.get_video.return_value["exercise_type"] = "bench press"
    repository.get_video.return_value["view_type"] = "front"
    storage = MagicMock()
    storage.download_to_tempfile.return_value = "/tmp/video.mov"
    estimation = self._estimation()
    estimation["frames"] = [
      {
        "source_frame_index": index,
        "timestamp_ms": index * 100,
        "landmarks": {
          "left_wrist": {"x": 0.45, "y": y, "z": 0.0, "visibility": 0.9},
          "right_wrist": {"x": 0.55, "y": y, "z": 0.0, "visibility": 0.9},
          "left_shoulder": {"x": 0.42, "y": 0.35, "z": 0.0, "visibility": 0.9},
          "right_shoulder": {"x": 0.58, "y": 0.35, "z": 0.0, "visibility": 0.9},
          "left_elbow": {"x": 0.43, "y": (0.35 + y) / 2, "z": 0.0, "visibility": 0.9},
          "right_elbow": {"x": 0.57, "y": (0.35 + y) / 2, "z": 0.0, "visibility": 0.9},
          "left_hip": {"x": 0.44, "y": 0.7, "z": 0.0, "visibility": 0.9},
          "right_hip": {"x": 0.56, "y": 0.7, "z": 0.0, "visibility": 0.9},
        },
      }
      for index, y in enumerate([0.34, 0.57, 0.33])
    ]
    estimator = MagicMock()
    estimator.config = PoseEstimatorConfig(pose_backend="hybrid", pose_fallback_enabled=True)
    estimator.run.return_value = estimation
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
    self.assertEqual(saved_result["barbellPath"]["target"], "bar_center")
    self.assertEqual(saved_result["barbellPath"]["source"], "pose_wrist_proxy")
    self.assertEqual(saved_result["rep_count"], 1)
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
