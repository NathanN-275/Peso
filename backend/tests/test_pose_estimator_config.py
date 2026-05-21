from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.analysis.pose_estimator import (
  PoseEstimator,
  PoseEstimatorConfig,
  empty_landmarks,
  landmarks_from_coco17,
  _scaled_dimensions,
  pose_config_from_env,
)


class PoseEstimatorConfigTest(unittest.TestCase):
  def test_defaults(self) -> None:
    with patch.dict(os.environ, {}, clear=True):
      config = pose_config_from_env()

    self.assertEqual(config.target_fps, 18.0)
    self.assertEqual(config.max_frame_dimension, 720)
    self.assertEqual(config.model_complexity, 2)
    self.assertEqual(config.min_detection_confidence, 0.6)
    self.assertEqual(config.min_tracking_confidence, 0.6)
    self.assertEqual(config.pose_backend, "hybrid")
    self.assertEqual(config.pose_fallback_enabled, True)
    self.assertEqual(config.pose_fallback_device, "auto")
    self.assertEqual(config.pose_fallback_det_frequency, 3)
    self.assertEqual(config.pose_fallback_mode, "balanced")

  def test_invalid_env_values_fall_back_to_defaults(self) -> None:
    with self.assertLogs("app.analysis.pose_estimator", level="WARNING"):
      with patch.dict(
        os.environ,
        {
          "POSE_TARGET_FPS": "fast",
          "POSE_MAX_FRAME_DIMENSION": "0",
          "POSE_MODEL_COMPLEXITY": "4",
          "POSE_MIN_DETECTION_CONFIDENCE": "2",
          "POSE_MIN_TRACKING_CONFIDENCE": "-0.1",
          "POSE_BACKEND": "slowpose",
          "POSE_FALLBACK_ENABLED": "maybe",
          "POSE_FALLBACK_DEVICE": "tpu",
          "POSE_FALLBACK_DET_FREQUENCY": "0",
          "POSE_FALLBACK_MODE": "turbo",
        },
        clear=True,
      ):
        config = pose_config_from_env()

    self.assertEqual(config, PoseEstimatorConfig())

  def test_custom_env_values(self) -> None:
    with patch.dict(
      os.environ,
      {
        "POSE_TARGET_FPS": "10",
        "POSE_MAX_FRAME_DIMENSION": "640",
        "POSE_MODEL_COMPLEXITY": "2",
        "POSE_MIN_DETECTION_CONFIDENCE": "0.7",
        "POSE_MIN_TRACKING_CONFIDENCE": "0.65",
        "POSE_BACKEND": "rtmpose",
        "POSE_FALLBACK_ENABLED": "true",
        "POSE_FALLBACK_DEVICE": "cpu",
        "POSE_FALLBACK_DET_FREQUENCY": "5",
        "POSE_FALLBACK_MODE": "performance",
        "POSE_DEBUG_LANDMARK_EXPORT_DIR": "/tmp/peso-landmarks",
      },
      clear=True,
    ):
      config = pose_config_from_env()

    self.assertEqual(config.target_fps, 10.0)
    self.assertEqual(config.max_frame_dimension, 640)
    self.assertEqual(config.model_complexity, 2)
    self.assertEqual(config.min_detection_confidence, 0.7)
    self.assertEqual(config.min_tracking_confidence, 0.65)
    self.assertEqual(config.pose_backend, "rtmpose")
    self.assertEqual(config.pose_fallback_enabled, True)
    self.assertEqual(config.pose_fallback_device, "cpu")
    self.assertEqual(config.pose_fallback_det_frequency, 5)
    self.assertEqual(config.pose_fallback_mode, "performance")
    self.assertEqual(config.debug_landmark_export_dir, "/tmp/peso-landmarks")

  def test_scaled_dimensions_preserve_aspect_ratio(self) -> None:
    self.assertEqual(_scaled_dimensions(1920, 1080, 720), (720, 405))
    self.assertEqual(_scaled_dimensions(480, 640, 720), (480, 640))

  def test_constructor_accepts_explicit_config_without_importing_mediapipe(self) -> None:
    estimator = PoseEstimator(
      config=PoseEstimatorConfig(
        target_fps=10.0,
        max_frame_dimension=640,
        model_complexity=0,
        min_detection_confidence=0.4,
        min_tracking_confidence=0.4,
        pose_backend="mediapipe",
      )
    )

    self.assertEqual(estimator.target_fps, 10.0)
    self.assertEqual(estimator.config.max_frame_dimension, 640)

  def test_empty_landmarks_preserves_mediapipe_shape(self) -> None:
    landmarks = empty_landmarks()

    self.assertEqual(len(landmarks), 33)
    self.assertIn("left_hip", landmarks)
    self.assertEqual(landmarks["left_heel"]["visibility"], 0.0)

  def test_rtmpose_coco17_maps_to_mediapipe_names(self) -> None:
    keypoints = [[index * 10.0, index * 5.0] for index in range(17)]
    scores = [0.1 + (index * 0.01) for index in range(17)]

    landmarks = landmarks_from_coco17(keypoints, scores, width=200, height=100)

    self.assertEqual(landmarks["left_shoulder"]["x"], 50 / 200)
    self.assertEqual(landmarks["left_shoulder"]["y"], 25 / 100)
    self.assertEqual(landmarks["left_hip"]["x"], 110 / 200)
    self.assertEqual(landmarks["left_knee"]["visibility"], scores[13])
    self.assertEqual(landmarks["left_heel"]["visibility"], 0.0)
    self.assertEqual(landmarks["left_foot_index"]["visibility"], 0.0)


if __name__ == "__main__":
  unittest.main()
