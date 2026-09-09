"""Offline MediaPipe Tasks integration shared by analysis and quality preflight."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any


MODEL_DIRECTORY = Path(__file__).resolve().parent / "models"
MODEL_SHA256 = {
  "lite": "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
  "full": "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1",
  "heavy": "64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b",
}
MODEL_VARIANTS = ("lite", "full", "heavy")


def verified_model_path(complexity: int) -> Path:
  if complexity not in (0, 1, 2):
    raise ValueError("Pose model complexity must be 0, 1, or 2.")
  variant = MODEL_VARIANTS[complexity]
  path = MODEL_DIRECTORY / f"pose_landmarker_{variant}.task"
  if not path.is_file():
    raise RuntimeError("Pose models are missing; run scripts/fetch_pose_models.py before starting the backend.")
  with path.open('rb') as model:
    checksum = hashlib.file_digest(model, 'sha256').hexdigest()
  if checksum != MODEL_SHA256[variant]:
    raise RuntimeError(f"Pose model checksum mismatch: {variant}")
  return path


class PoseLandmarkerSession:
  """One CPU landmarker per video; IMAGE mode handles unordered preflight seeks."""

  def __init__(self, *, complexity: int, video: bool, detection_confidence: float,
               tracking_confidence: float = 0.5) -> None:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    self._mp = mp
    self._video = video
    self._last_timestamp = -1
    self._landmarker = vision.PoseLandmarker.create_from_options(
      vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(
          model_asset_path=str(verified_model_path(complexity)),
          delegate=python.BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=detection_confidence,
        # The legacy landmark-stage threshold maps to Tasks' presence threshold.
        min_pose_presence_confidence=tracking_confidence,
        min_tracking_confidence=tracking_confidence,
        output_segmentation_masks=False,
      )
    )

  def process_rgb(self, frame: Any, timestamp_ms: int = 0) -> Any | None:
    import numpy as np

    image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame))
    if self._video:
      # Codecs may repeat or regress timestamps. Preserve source timestamps in
      # public results while supplying Tasks with a strictly increasing clock.
      timestamp = max(int(timestamp_ms), self._last_timestamp + 1, 0)
      result = self._landmarker.detect_for_video(image, timestamp)
      self._last_timestamp = timestamp
    else:
      result = self._landmarker.detect(image)
    if not result.pose_landmarks:
      return None
    landmarks = result.pose_landmarks[0]
    if len(landmarks) != 33:
      raise RuntimeError("Pose Landmarker returned an invalid landmark count.")
    return SimpleNamespace(landmark=landmarks)

  def close(self) -> None:
    self._landmarker.close()

  def __enter__(self) -> PoseLandmarkerSession:
    return self

  def __exit__(self, *_args: Any) -> None:
    self.close()
