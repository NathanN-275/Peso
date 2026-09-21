from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from app.analysis.pose_landmarker import PoseLandmarkerSession, verified_model_path
from app.analysis.pose_estimator import MediaPipePoseBackend, PoseEstimatorConfig


class PoseLandmarkerContractTest(unittest.TestCase):
  def session(self, video=True):
    session = PoseLandmarkerSession.__new__(PoseLandmarkerSession)
    session._mp = SimpleNamespace(Image=Mock(), ImageFormat=SimpleNamespace(SRGB=1))
    session._video = video
    session._last_timestamp = -1
    session._landmarker = Mock()
    points = [SimpleNamespace(x=0.1, y=0.2, z=0.3, visibility=0.9) for _ in range(33)]
    result = SimpleNamespace(pose_landmarks=[points])
    session._landmarker.detect_for_video.return_value = result
    session._landmarker.detect.return_value = result
    return session

  def test_video_clock_is_monotonic_without_changing_public_pose_shape(self):
    session = self.session()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    for timestamp in [10, 10, 3, 100]:
      self.assertEqual(len(session.process_rgb(frame, timestamp).landmark), 33)
    self.assertEqual([call.args[1] for call in session._landmarker.detect_for_video.call_args_list], [10, 11, 12, 100])

  def test_preflight_image_mode_allows_unordered_seek_results_and_closes(self):
    session = self.session(video=False)
    with session:
      for timestamp in [100, 0]:
        self.assertEqual(len(session.process_rgb(np.zeros((2, 2, 3)), timestamp).landmark), 33)
    session._landmarker.detect_for_video.assert_not_called()
    session._landmarker.close.assert_called_once()

  def test_missing_pose_and_invalid_landmark_count(self):
    session = self.session()
    session._landmarker.detect_for_video.return_value.pose_landmarks = []
    self.assertIsNone(session.process_rgb(np.zeros((2, 2, 3))))
    session._landmarker.detect_for_video.return_value.pose_landmarks = [[object()]]
    with self.assertRaisesRegex(RuntimeError, 'invalid landmark count'):
      session.process_rgb(np.zeros((2, 2, 3)))

  def test_backend_maps_configuration_and_named_landmarks(self):
    for complexity in [0, 1, 2]:
      session = self.session()
      with patch('app.analysis.pose_landmarker.PoseLandmarkerSession', return_value=session) as factory:
        backend = MediaPipePoseBackend(PoseEstimatorConfig(model_complexity=complexity,
          min_detection_confidence=0.6, min_tracking_confidence=0.7))
      factory.assert_called_once_with(complexity=complexity, video=True,
        detection_confidence=0.6, tracking_confidence=0.7)
      result = backend.process(np.zeros((2, 2, 3), dtype=np.uint8), 12)
      self.assertEqual(len(result), 33)
      self.assertEqual(result['left_hip'], {'x': 0.1, 'y': 0.2, 'z': 0.3, 'visibility': 0.9})
      backend.close()
      session._landmarker.close.assert_called_once()

  def test_model_missing_corrupt_or_unknown_fails_closed(self):
    with TemporaryDirectory() as directory, patch('app.analysis.pose_landmarker.MODEL_DIRECTORY', Path(directory)):
      with self.assertRaisesRegex(RuntimeError, 'missing'):
        verified_model_path(1)
      (Path(directory) / 'pose_landmarker_full.task').write_bytes(b'corrupt')
      with self.assertRaisesRegex(RuntimeError, 'checksum'):
        verified_model_path(1)
      with self.assertRaises(ValueError):
        verified_model_path(3)


if __name__ == '__main__':
  unittest.main()
