from __future__ import annotations

from typing import Any

import cv2
import mediapipe as mp


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

class PoseEstimator:
  def __init__(self, target_fps: float = 15.0) -> None:
    # Lower sampling keeps processing fast while preserving squat motion.
    self.target_fps = target_fps

  def run(self, file_path: str) -> dict[str, Any]:
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
    duration_ms = int((frame_count / fps) * 1000) if fps > 0 else None
    frame_step = max(int(round(fps / self.target_fps)), 1) if fps > 0 else 1

    frames: list[dict[str, Any]] = []
    sampled_frame_count = 0
    pose = mp.solutions.pose.Pose(
      static_image_mode=False,
      model_complexity=1,
      smooth_landmarks=True,
      min_detection_confidence=0.5,
      min_tracking_confidence=0.5,
    )

    try:
      # Only every Nth frame is run through MediaPipe.
      frame_index = 0
      sampled_index = 0

      while capture.isOpened():
        success, frame = capture.read()

        if not success:
          break

        if frame_index % frame_step != 0:
          frame_index += 1
          continue

        sampled_frame_count += 1
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)

        if results.pose_landmarks:
          # Convert the MediaPipe landmarks into plain dicts.
          landmarks = {
            name: {
              "x": landmark.x,
              "y": landmark.y,
              "z": landmark.z,
              "visibility": landmark.visibility,
            }
            for name, landmark in zip(
              POSE_LANDMARK_NAMES,
              results.pose_landmarks.landmark,
              strict=False,
            )
          }
          frames.append(
            {
              "frame_index": sampled_index,
              "source_frame_index": frame_index,
              "timestamp_ms": int((frame_index / fps) * 1000) if fps > 0 else sampled_index * 67,
              "landmarks": landmarks,
            }
          )
          sampled_index += 1

        frame_index += 1
    finally:
      pose.close()
      capture.release()

    return {
      "fps": round(fps, 2) if fps else None,
      "duration_ms": duration_ms,
      "frame_count": frame_count,
      "sampled_frame_count": sampled_frame_count,
      "frame_width": frame_width or None,
      "frame_height": frame_height or None,
      "frames": frames,
    }
