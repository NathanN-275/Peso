from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


SQUAT_LABELS = {
  "left_upper_back": "Upper Back",
  "right_upper_back": "Upper Back",
  "left_shoulder": "Upper Back",
  "right_shoulder": "Upper Back",
  "left_hip": "Hip",
  "right_hip": "Hip",
  "left_knee": "Knee",
  "right_knee": "Knee",
  "left_ankle": "Ankle",
  "right_ankle": "Ankle",
}
SQUAT_LANDMARKS = set(SQUAT_LABELS)
CONFIDENCE_THRESHOLD = 0.15
ESTIMATED_CONFIDENCE_THRESHOLD = 0.5
BLUE = (255, 107, 31)
YELLOW = (0, 245, 255)
WHITE = (255, 255, 255)
ORANGE = (32, 176, 255)
BLACK = (0, 0, 0)


def _resolve_ffmpeg_binary() -> str:
  configured_binary = os.getenv("FFMPEG_BINARY", "").strip()

  if configured_binary:
    if shutil.which(configured_binary) or Path(configured_binary).exists():
      return configured_binary

    raise RuntimeError("FFmpeg binary configured by FFMPEG_BINARY was not found.")

  ffmpeg_binary = shutil.which("ffmpeg")

  if not ffmpeg_binary:
    raise RuntimeError("FFmpeg is required to export analyzed videos. Install ffmpeg or set FFMPEG_BINARY.")

  return ffmpeg_binary


def _average_side_confidence(keypoints: list[dict[str, Any]], side: str) -> float:
  side_keypoints = [
    keypoint
    for keypoint in keypoints
    if str(keypoint.get("name", "")).startswith(f"{side}_")
  ]

  if not side_keypoints:
    return 0

  return sum(float(keypoint.get("confidence") or 0) for keypoint in side_keypoints) / len(side_keypoints)


def _select_visible_side(keypoints: list[dict[str, Any]]) -> str:
  return "left" if _average_side_confidence(keypoints, "left") >= _average_side_confidence(keypoints, "right") else "right"


def _visual_fallback_point(keypoint: dict[str, Any]) -> dict[str, Any] | None:
  fallback = keypoint.get("visualFallback") or keypoint.get("visual_fallback")
  if not isinstance(fallback, dict):
    return None

  point = fallback.get("point")
  if isinstance(point, dict):
    x = point.get("x")
    y = point.get("y")
  else:
    x = fallback.get("x")
    y = fallback.get("y")
  if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
    return None

  return {
    **keypoint,
    "x": x,
    "y": y,
    "confidence": fallback.get("confidence", keypoint.get("confidence")),
    "trackingState": fallback.get("trackingState") or fallback.get("tracking_state") or "estimated",
    "manualSource": (
      fallback.get("manualSource")
      or fallback.get("manual_source")
      or "pin_visual_fallback"
    ),
    "userPinned": True,
  }


def _overlay_keypoints(
  frame: dict[str, Any] | None,
  camera_view: str | None,
  selected_side: str | None,
) -> list[dict[str, Any]]:
  if not frame:
    return []

  keypoints: list[dict[str, Any]] = []
  for keypoint in frame.get("keypoints") or []:
    if keypoint.get("name") not in SQUAT_LANDMARKS:
      continue
    fallback = _visual_fallback_point(keypoint)
    if bool(keypoint.get("preferVisualFallback")) and fallback is not None:
      keypoints.append(fallback)
      continue
    if float(keypoint.get("confidence") or 0) >= CONFIDENCE_THRESHOLD:
      keypoints.append(keypoint)
      continue
    if fallback is not None:
      keypoints.append(fallback)
      continue
    if bool(keypoint.get("userPinned")) or keypoint.get("manualSource") == "pin_estimated":
      keypoints.append(keypoint)
  side = selected_side if selected_side in {"left", "right"} else None

  if camera_view == "side" and not side:
    side = _select_visible_side(keypoints)

  if side:
    keypoints = [
      keypoint
      for keypoint in keypoints
      if str(keypoint.get("name", "")).startswith(f"{side}_")
    ]

  return keypoints


def _connections(keypoints: list[dict[str, Any]], camera_view: str | None, selected_side: str | None) -> list[tuple[str, str]]:
  def torso_start(side: str) -> str:
    upper_back = f"{side}_upper_back"
    names = {str(keypoint.get("name", "")) for keypoint in keypoints}
    return upper_back if upper_back in names else f"{side}_shoulder"

  if camera_view != "side":
    left_torso = torso_start("left")
    right_torso = torso_start("right")
    return [
      (left_torso, "left_hip"),
      ("left_hip", "left_knee"),
      ("left_knee", "left_ankle"),
      (right_torso, "right_hip"),
      ("right_hip", "right_knee"),
      ("right_knee", "right_ankle"),
      ("left_hip", "right_hip"),
      (left_torso, right_torso),
    ]

  side = selected_side if selected_side in {"left", "right"} else _select_visible_side(keypoints)
  return [
    (torso_start(side), f"{side}_hip"),
    (f"{side}_hip", f"{side}_knee"),
    (f"{side}_knee", f"{side}_ankle"),
  ]


def _closest_pose_frame(pose_frames: list[dict[str, Any]], current_time: float) -> dict[str, Any] | None:
  if not pose_frames:
    return None

  low = 0
  high = len(pose_frames) - 1

  while low < high:
    mid = (low + high) // 2
    if float(pose_frames[mid].get("time") or 0) < current_time:
      low = mid + 1
    else:
      high = mid

  current = pose_frames[low]
  previous = pose_frames[low - 1] if low > 0 else None

  if not previous:
    return current

  current_delta = abs(float(current.get("time") or 0) - current_time)
  previous_delta = abs(float(previous.get("time") or 0) - current_time)
  return previous if previous_delta <= current_delta else current


def _point(keypoint: dict[str, Any], width: int, height: int) -> tuple[int, int]:
  x = int(round(float(keypoint.get("x") or 0) * width))
  y = int(round(float(keypoint.get("y") or 0) * height))
  return (max(0, min(x, width - 1)), max(0, min(y, height - 1)))


def _draw_label(cv2: Any, frame: Any, label: str, point: tuple[int, int], color: tuple[int, int, int]) -> None:
  x, y = point
  label_x = max(4, min(x + 10, frame.shape[1] - 90))
  label_y = max(24, min(y - 8, frame.shape[0] - 6))
  cv2.putText(frame, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.68, BLACK, 5, cv2.LINE_AA)
  cv2.putText(frame, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.68, color, 2, cv2.LINE_AA)


def _draw_pose_overlay(
  cv2: Any,
  image: Any,
  pose_frame: dict[str, Any] | None,
  camera_view: str | None,
  selected_side: str | None,
) -> None:
  height, width = image.shape[:2]
  keypoints = _overlay_keypoints(pose_frame, camera_view, selected_side)
  mapped = {
    keypoint["name"]: {
      "point": _point(keypoint, width, height),
      "confidence": float(keypoint.get("confidence") or 0),
    }
    for keypoint in keypoints
    if keypoint.get("name")
  }

  for start_name, end_name in _connections(keypoints, camera_view, selected_side):
    start = mapped.get(start_name)
    end = mapped.get(end_name)

    if start and end:
      cv2.line(image, start["point"], end["point"], BLUE, 4, cv2.LINE_AA)

  for name, data in mapped.items():
    point = data["point"]
    estimated = data["confidence"] < ESTIMATED_CONFIDENCE_THRESHOLD
    fill_color = WHITE if estimated else YELLOW
    label_color = ORANGE if estimated else WHITE
    cv2.circle(image, point, 7, BLUE, -1, cv2.LINE_AA)
    cv2.circle(image, point, 5, fill_color, -1, cv2.LINE_AA)
    _draw_label(cv2, image, SQUAT_LABELS[name], point, label_color)


def render_analyzed_video(
  *,
  source_path: Path,
  output_path: Path,
  result_json: dict[str, Any],
) -> Path:
  import cv2

  capture = cv2.VideoCapture(str(source_path))

  if not capture.isOpened():
    raise RuntimeError("Unable to open source video for export.")

  if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
    capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

  fps = capture.get(cv2.CAP_PROP_FPS) or 30
  width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
  height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

  if width <= 0 or height <= 0:
    capture.release()
    raise RuntimeError("Unable to read source video dimensions for export.")

  output_path.parent.mkdir(parents=True, exist_ok=True)
  ffmpeg_binary = _resolve_ffmpeg_binary()
  ffmpeg_process = subprocess.Popen(
    [
      ffmpeg_binary,
      "-y",
      "-f",
      "rawvideo",
      "-vcodec",
      "rawvideo",
      "-pix_fmt",
      "bgr24",
      "-s",
      f"{width}x{height}",
      "-r",
      f"{fps}",
      "-i",
      "-",
      "-an",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "20",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      str(output_path),
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
  )
  pose_frames = sorted(result_json.get("poseFrames") or [], key=lambda frame: float(frame.get("time") or 0))
  camera_view = str(result_json.get("cameraView") or result_json.get("view") or "").lower() or None
  diagnostics = result_json.get("diagnostics") or {}
  pose_validation = diagnostics.get("pose_validation") or {}
  selected_side = pose_validation.get("selected_side") or diagnostics.get("selected_side")
  frame_index = 0

  try:
    while True:
      success, image = capture.read()

      if not success:
        break

      timestamp = frame_index / fps if fps > 0 else 0
      _draw_pose_overlay(
        cv2,
        image,
        _closest_pose_frame(pose_frames, timestamp),
        camera_view,
        selected_side,
      )

      if not ffmpeg_process.stdin:
        raise RuntimeError("FFmpeg input pipe was unavailable for analyzed video export.")

      try:
        ffmpeg_process.stdin.write(image.tobytes())
      except BrokenPipeError as error:
        raise RuntimeError("FFmpeg stopped before analyzed video export completed.") from error

      frame_index += 1
  finally:
    capture.release()
    if ffmpeg_process.stdin:
      ffmpeg_process.stdin.close()
      ffmpeg_process.stdin = None

  _, stderr = ffmpeg_process.communicate()

  if frame_index == 0:
    raise RuntimeError("Unable to read frames from source video for export.")

  if ffmpeg_process.returncode != 0:
    message = stderr.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"FFmpeg failed to export analyzed video: {message}")

  return output_path
