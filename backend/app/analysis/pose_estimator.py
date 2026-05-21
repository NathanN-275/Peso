from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


POSE_LANDMARK_NAMES = [
  "nose",
  "left_eye_inner",
  "left_eye",
  "left_eye_outer",
  "right_eye_inner",
  "right_eye",
  "right_eye_outer",
  "left_ear",
  "right_ear",
  "mouth_left",
  "mouth_right",
  "left_shoulder",
  "right_shoulder",
  "left_elbow",
  "right_elbow",
  "left_wrist",
  "right_wrist",
  "left_pinky",
  "right_pinky",
  "left_index",
  "right_index",
  "left_thumb",
  "right_thumb",
  "left_hip",
  "right_hip",
  "left_knee",
  "right_knee",
  "left_ankle",
  "right_ankle",
  "left_heel",
  "right_heel",
  "left_foot_index",
  "right_foot_index",
]

# Pose estimation samples frames and extracts MediaPipe landmarks.

logger = logging.getLogger(__name__)

COCO17_TO_MEDIAPIPE33 = {
  0: "nose",
  1: "left_eye",
  2: "right_eye",
  3: "left_ear",
  4: "right_ear",
  5: "left_shoulder",
  6: "right_shoulder",
  7: "left_elbow",
  8: "right_elbow",
  9: "left_wrist",
  10: "right_wrist",
  11: "left_hip",
  12: "right_hip",
  13: "left_knee",
  14: "right_knee",
  15: "left_ankle",
  16: "right_ankle",
}

SUPPORTED_POSE_BACKENDS = {"mediapipe", "rtmpose", "hybrid"}
SUPPORTED_FALLBACK_MODES = {"performance", "lightweight", "balanced"}


@dataclass(frozen=True)
class PoseEstimatorConfig:
  target_fps: float = 18.0
  max_frame_dimension: int = 720
  model_complexity: int = 2
  min_detection_confidence: float = 0.6
  min_tracking_confidence: float = 0.6
  pose_backend: str = "hybrid"
  pose_fallback_enabled: bool = True
  pose_fallback_device: str = "auto"
  pose_fallback_det_frequency: int = 3
  pose_fallback_mode: str = "balanced"
  debug_landmark_export_dir: str | None = None


def _float_from_env(name: str, default: float, *, minimum: float, maximum: float | None = None) -> float:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default

  try:
    value = float(raw_value)
  except ValueError:
    logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
    return default

  if value < minimum or (maximum is not None and value > maximum):
    logger.warning("Ignoring out-of-range %s=%r; using default %s.", name, raw_value, default)
    return default

  return value


def _int_from_env(name: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default

  try:
    value = int(raw_value)
  except ValueError:
    logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
    return default

  if value < minimum or (maximum is not None and value > maximum):
    logger.warning("Ignoring out-of-range %s=%r; using default %s.", name, raw_value, default)
    return default

  return value


def _bool_from_env(name: str, default: bool) -> bool:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  normalized = raw_value.strip().lower()
  if normalized in {"1", "true", "yes", "on"}:
    return True
  if normalized in {"0", "false", "no", "off"}:
    return False
  logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
  return default


def _choice_from_env(name: str, default: str, choices: set[str]) -> str:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  normalized = raw_value.strip().lower()
  if normalized not in choices:
    logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
    return default
  return normalized


def pose_config_from_env() -> PoseEstimatorConfig:
  return PoseEstimatorConfig(
    target_fps=_float_from_env("POSE_TARGET_FPS", 18.0, minimum=1.0, maximum=60.0),
    max_frame_dimension=_int_from_env("POSE_MAX_FRAME_DIMENSION", 720, minimum=128, maximum=4096),
    model_complexity=_int_from_env("POSE_MODEL_COMPLEXITY", 2, minimum=0, maximum=2),
    min_detection_confidence=_float_from_env(
      "POSE_MIN_DETECTION_CONFIDENCE",
      0.6,
      minimum=0.0,
      maximum=1.0,
    ),
    min_tracking_confidence=_float_from_env(
      "POSE_MIN_TRACKING_CONFIDENCE",
      0.6,
      minimum=0.0,
      maximum=1.0,
    ),
    pose_backend=_choice_from_env("POSE_BACKEND", "hybrid", SUPPORTED_POSE_BACKENDS),
    pose_fallback_enabled=_bool_from_env("POSE_FALLBACK_ENABLED", True),
    pose_fallback_device=_choice_from_env("POSE_FALLBACK_DEVICE", "auto", {"auto", "cpu", "mps", "cuda"}),
    pose_fallback_det_frequency=_int_from_env("POSE_FALLBACK_DET_FREQUENCY", 3, minimum=1, maximum=60),
    pose_fallback_mode=_choice_from_env("POSE_FALLBACK_MODE", "balanced", SUPPORTED_FALLBACK_MODES),
    debug_landmark_export_dir=(os.getenv("POSE_DEBUG_LANDMARK_EXPORT_DIR") or "").strip() or None,
  )


def _scaled_dimensions(width: int, height: int, max_dimension: int) -> tuple[int, int]:
  longest_side = max(width, height)

  if longest_side <= 0:
    return width, height
  if longest_side <= max_dimension:
    return width, height

  scale = max_dimension / longest_side
  return max(int(round(width * scale)), 1), max(int(round(height * scale)), 1)


def empty_landmarks() -> dict[str, dict[str, float]]:
  return {
    name: {
      "x": 0.0,
      "y": 0.0,
      "z": 0.0,
      "visibility": 0.0,
    }
    for name in POSE_LANDMARK_NAMES
  }


def landmarks_from_mediapipe(pose_landmarks: Any) -> dict[str, dict[str, float]]:
  return {
    name: {
      "x": float(landmark.x),
      "y": float(landmark.y),
      "z": float(getattr(landmark, "z", 0.0)),
      "visibility": float(getattr(landmark, "visibility", 0.0)),
    }
    for name, landmark in zip(POSE_LANDMARK_NAMES, pose_landmarks.landmark)
  }


def landmarks_from_coco17(
  keypoints: Any,
  scores: Any,
  *,
  width: int,
  height: int,
) -> dict[str, dict[str, float]]:
  landmarks = empty_landmarks()
  if width <= 0 or height <= 0:
    return landmarks

  for coco_index, landmark_name in COCO17_TO_MEDIAPIPE33.items():
    confidence = float(scores[coco_index])
    landmarks[landmark_name] = {
      "x": float(keypoints[coco_index][0]) / width,
      "y": float(keypoints[coco_index][1]) / height,
      "z": 0.0,
      "visibility": confidence,
    }

  return landmarks


def _person_center(keypoints: Any, scores: Any) -> tuple[float, float] | None:
  weighted_x = 0.0
  weighted_y = 0.0
  total = 0.0

  for index in range(len(keypoints)):
    confidence = float(scores[index])
    if confidence <= 0.1:
      continue
    weighted_x += float(keypoints[index][0]) * confidence
    weighted_y += float(keypoints[index][1]) * confidence
    total += confidence

  if total <= 0.1:
    return None

  return weighted_x / total, weighted_y / total


class MediaPipePoseBackend:
  landmark_model = "mediapipe_pose_33"

  def __init__(self, config: PoseEstimatorConfig) -> None:
    import mediapipe as mp

    self._pose = mp.solutions.pose.Pose(
      static_image_mode=False,
      model_complexity=config.model_complexity,
      smooth_landmarks=True,
      min_detection_confidence=config.min_detection_confidence,
      min_tracking_confidence=config.min_tracking_confidence,
    )

  def process(self, frame: Any, timestamp_ms: int) -> dict[str, dict[str, float]] | None:
    import cv2

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = self._pose.process(rgb_frame)
    if not results.pose_landmarks:
      return None
    return landmarks_from_mediapipe(results.pose_landmarks)

  def close(self) -> None:
    self._pose.close()


class RTMPoseBackend:
  landmark_model = "rtmpose_coco17_mapped_to_mediapipe_33"

  def __init__(self, config: PoseEstimatorConfig) -> None:
    try:
      from rtmlib import Body, PoseTracker
    except ImportError as error:
      raise RuntimeError(
        "RTMPose fallback requires the optional rtmlib dependency. "
        "Install rtmlib and enable POSE_FALLBACK_ENABLED=true to use it."
      ) from error

    device = None if config.pose_fallback_device == "auto" else config.pose_fallback_device
    self._tracker = PoseTracker(
      Body,
      mode=config.pose_fallback_mode,
      det_frequency=config.pose_fallback_det_frequency,
      backend="onnxruntime",
      device=device,
      to_openpose=False,
    )
    self._last_center: tuple[float, float] | None = None

  def _select_person(self, keypoints: Any, scores: Any) -> int:
    if len(keypoints) <= 1:
      return 0

    if self._last_center is None:
      best_index = 0
      best_confidence = -1.0
      for index in range(len(keypoints)):
        mean_confidence = float(scores[index].mean())
        if mean_confidence > best_confidence:
          best_confidence = mean_confidence
          best_index = index
      return best_index

    last_x, last_y = self._last_center
    best_index = 0
    best_distance = float("inf")

    for index in range(len(keypoints)):
      center = _person_center(keypoints[index], scores[index])
      if center is None:
        continue
      distance = ((center[0] - last_x) ** 2) + ((center[1] - last_y) ** 2)
      if distance < best_distance:
        best_distance = distance
        best_index = index

    return best_index

  def process(self, frame: Any, timestamp_ms: int) -> dict[str, dict[str, float]] | None:
    keypoints, scores = self._tracker(frame)
    if keypoints is None or len(keypoints) == 0:
      return None

    person_index = self._select_person(keypoints, scores)
    selected_keypoints = keypoints[person_index]
    selected_scores = scores[person_index]
    center = _person_center(selected_keypoints, selected_scores)
    if center is not None:
      self._last_center = center

    height, width = frame.shape[:2]
    return landmarks_from_coco17(
      selected_keypoints,
      selected_scores,
      width=width,
      height=height,
    )

  def close(self) -> None:
    return None


def _create_pose_backend(name: str, config: PoseEstimatorConfig) -> MediaPipePoseBackend | RTMPoseBackend:
  if name == "rtmpose":
    return RTMPoseBackend(config)
  if name == "mediapipe":
    return MediaPipePoseBackend(config)
  raise ValueError(f"Unsupported pose backend: {name}")


def _export_debug_landmarks(
  *,
  export_dir: str | None,
  file_path: str,
  backend_name: str,
  frames: list[dict[str, Any]],
) -> None:
  if not export_dir:
    return

  output_dir = Path(export_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  source_name = Path(file_path).stem or "video"
  output_path = output_dir / f"{source_name}_{backend_name}_landmarks.json"
  payload = {
    "source_video": file_path,
    "pose_backend": backend_name,
    "landmark_names": POSE_LANDMARK_NAMES,
    "landmark_model": (
      RTMPoseBackend.landmark_model if backend_name == "rtmpose" else MediaPipePoseBackend.landmark_model
    ),
    "frames": frames,
  }
  output_path.write_text(json.dumps(payload), encoding="utf-8")


class PoseEstimator:
  def __init__(
    self,
    target_fps: float | None = None,
    config: PoseEstimatorConfig | None = None,
  ) -> None:
    # Lower sampling keeps processing fast while preserving squat motion.
    env_config = config or pose_config_from_env()
    if target_fps is not None:
      env_config = PoseEstimatorConfig(
        target_fps=target_fps,
        max_frame_dimension=env_config.max_frame_dimension,
        model_complexity=env_config.model_complexity,
        min_detection_confidence=env_config.min_detection_confidence,
        min_tracking_confidence=env_config.min_tracking_confidence,
        pose_backend=env_config.pose_backend,
        pose_fallback_enabled=env_config.pose_fallback_enabled,
        pose_fallback_device=env_config.pose_fallback_device,
        pose_fallback_det_frequency=env_config.pose_fallback_det_frequency,
        pose_fallback_mode=env_config.pose_fallback_mode,
        debug_landmark_export_dir=env_config.debug_landmark_export_dir,
      )
    self.config = env_config
    self.target_fps = env_config.target_fps

  def run(self, file_path: str) -> dict[str, Any]:
    import cv2

    processing_started = time.perf_counter()
    # OpenCV streams the clip frame by frame for pose inference.
    capture = cv2.VideoCapture(file_path)

    if not capture.isOpened():
      raise RuntimeError("Unable to open uploaded video.")

    if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
      capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    processed_width, processed_height = _scaled_dimensions(
      frame_width,
      frame_height,
      self.config.max_frame_dimension,
    )
    duration_ms = int((frame_count / fps) * 1000) if fps > 0 else None
    frame_step = max(int(round(fps / self.target_fps)), 1) if fps > 0 else 1

    backend_name = "mediapipe" if self.config.pose_backend == "hybrid" else self.config.pose_backend
    if backend_name == "rtmpose" and not self.config.pose_fallback_enabled:
      logger.warning("POSE_FALLBACK_ENABLED is false; falling back to MediaPipe.")
      backend_name = "mediapipe"

    try:
      frames, sampled_frame_count = self._run_backend(
        capture=capture,
        cv2=cv2,
        fps=fps,
        frame_step=frame_step,
        processed_width=processed_width,
        processed_height=processed_height,
        backend_name=backend_name,
      )
    finally:
      capture.release()

    _export_debug_landmarks(
      export_dir=self.config.debug_landmark_export_dir,
      file_path=file_path,
      backend_name=backend_name,
      frames=frames,
    )

    processing_duration_ms = int((time.perf_counter() - processing_started) * 1000)

    return {
      "fps": round(fps, 2) if fps else None,
      "duration_ms": duration_ms,
      "frame_count": frame_count,
      "sampled_frame_count": sampled_frame_count,
      "pose_frame_count": len(frames),
      "frame_width": frame_width or None,
      "frame_height": frame_height or None,
      "original_frame_width": frame_width or None,
      "original_frame_height": frame_height or None,
      "processed_frame_width": processed_width or None,
      "processed_frame_height": processed_height or None,
      "target_fps": self.config.target_fps,
      "frame_step": frame_step,
      "pose_model_complexity": self.config.model_complexity,
      "pose_backend": backend_name,
      "requested_pose_backend": self.config.pose_backend,
      "fallback_model": "rtmpose" if backend_name == "rtmpose" else None,
      "fallback_triggered": False,
      "fallback_reason": None,
      "pose_fallback_enabled": self.config.pose_fallback_enabled,
      "fallback_frame_count": len(frames) if backend_name == "rtmpose" else 0,
      "landmark_model": (
        RTMPoseBackend.landmark_model if backend_name == "rtmpose" else MediaPipePoseBackend.landmark_model
      ),
      "processing_duration_ms": processing_duration_ms,
      "frames": frames,
    }

  def _run_backend(
    self,
    *,
    capture: Any,
    cv2: Any,
    fps: float,
    frame_step: int,
    processed_width: int,
    processed_height: int,
    backend_name: str,
  ) -> tuple[list[dict[str, Any]], int]:
    frames: list[dict[str, Any]] = []
    sampled_frame_count = 0
    sampled_index = 0
    frame_index = 0
    backend = _create_pose_backend(backend_name, self.config)

    try:
      while capture.isOpened():
        success, frame = capture.read()
        if not success:
          break

        if frame_index % frame_step != 0:
          frame_index += 1
          continue

        sampled_frame_count += 1
        inference_frame = self._prepare_inference_frame(
          cv2=cv2,
          frame=frame,
          processed_width=processed_width,
          processed_height=processed_height,
        )
        timestamp_ms = int((frame_index / fps) * 1000) if fps > 0 else sampled_index * 67
        landmarks = backend.process(inference_frame, timestamp_ms)

        if landmarks:
          frames.append(
            {
              "frame_index": sampled_index,
              "source_frame_index": frame_index,
              "timestamp_ms": timestamp_ms,
              "frame_width": processed_width,
              "frame_height": processed_height,
              "landmarks": landmarks,
              "pose_backend": backend_name,
              "landmark_model": backend.landmark_model,
            }
          )
          sampled_index += 1

        frame_index += 1
    finally:
      backend.close()

    return frames, sampled_frame_count

  def _prepare_inference_frame(
    self,
    *,
    cv2: Any,
    frame: Any,
    processed_width: int,
    processed_height: int,
  ) -> Any:
    if processed_width and processed_height and (
      frame.shape[1] != processed_width or frame.shape[0] != processed_height
    ):
      return cv2.resize(
        frame,
        (processed_width, processed_height),
        interpolation=cv2.INTER_AREA,
      )
    return frame
