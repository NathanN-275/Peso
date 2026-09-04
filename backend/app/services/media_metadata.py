from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class MediaValidationError(ValueError):
  def __init__(self, code: str, message: str) -> None:
    super().__init__(message)
    self.code = code


@dataclass(frozen=True)
class VideoMetadata:
  duration_ms: int
  width: int
  height: int
  fps: float
  frame_count: int
  codec_name: str
  format_name: str

  def to_dict(self) -> dict[str, int | float | str]:
    return {
      "duration_ms": self.duration_ms,
      "width": self.width,
      "height": self.height,
      "fps": round(self.fps, 3),
      "frame_count": self.frame_count,
      "codec_name": self.codec_name,
      "format_name": self.format_name,
    }


def _positive_fraction(value: object) -> float:
  try:
    parsed = float(Fraction(str(value)))
  except (ValueError, ZeroDivisionError, OverflowError):
    return 0.0
  return parsed if math.isfinite(parsed) and parsed > 0 else 0.0


def probe_video_metadata(path: Path, *, timeout_seconds: int) -> VideoMetadata:
  ffprobe = shutil.which("ffprobe")
  if not ffprobe:
    raise RuntimeError("Media validation is unavailable because ffprobe is not installed.")

  command = [
    ffprobe,
    "-v",
    "error",
    "-protocol_whitelist",
    "file,pipe",
    "-count_frames",
    "-select_streams",
    "v:0",
    "-show_entries",
    "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,nb_read_frames,nb_frames",
    "-of",
    "json",
    str(path),
  ]
  try:
    result = subprocess.run(
      command,
      stdin=subprocess.DEVNULL,
      capture_output=True,
      text=True,
      check=False,
      timeout=timeout_seconds,
      env={"PATH": os.defpath, "HOME": tempfile.gettempdir()},
    )
  except (OSError, subprocess.TimeoutExpired) as error:
    raise RuntimeError("Media validation is temporarily unavailable.") from error

  if result.returncode != 0:
    raise MediaValidationError("malformed_media", "Uploaded file is not a readable video.")

  try:
    payload = json.loads(result.stdout)
    stream = next(item for item in payload.get("streams", []) if item.get("codec_type") == "video")
    duration_seconds = float(payload.get("format", {}).get("duration") or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    fps = max(_positive_fraction(stream.get("avg_frame_rate")), _positive_fraction(stream.get("r_frame_rate")))
    frame_count = int(stream.get("nb_read_frames") or stream.get("nb_frames") or 0)
  except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
    raise MediaValidationError("malformed_media", "Uploaded file has invalid video metadata.") from error

  if not math.isfinite(duration_seconds) or duration_seconds <= 0 or width <= 0 or height <= 0 or fps <= 0 or frame_count <= 0:
    raise MediaValidationError("missing_metadata", "Uploaded video metadata could not be verified.")
  fps = max(fps, frame_count / duration_seconds)

  return VideoMetadata(
    duration_ms=max(1, round(duration_seconds * 1000)),
    width=width,
    height=height,
    fps=fps,
    frame_count=frame_count,
    codec_name=str(stream.get("codec_name") or "unknown"),
    format_name=str(payload.get("format", {}).get("format_name") or "unknown"),
  )


def enforce_video_limits(
  metadata: VideoMetadata,
  *,
  max_duration_ms: int,
  max_width: int,
  max_height: int,
  max_fps: float,
) -> None:
  if metadata.duration_ms > max_duration_ms:
    raise MediaValidationError("duration_limit", "Uploaded video exceeds the five-minute duration limit.")

  long_edge = max(metadata.width, metadata.height)
  short_edge = min(metadata.width, metadata.height)
  if long_edge > max(max_width, max_height) or short_edge > min(max_width, max_height):
    raise MediaValidationError("dimension_limit", "Uploaded video exceeds the 1080p dimension limit.")

  if metadata.fps > max_fps + 0.01:
    raise MediaValidationError("frame_rate_limit", "Uploaded video exceeds the 60 fps limit.")

  maximum_frames = round((max_duration_ms / 1000) * max_fps)
  if metadata.frame_count > maximum_frames:
    raise MediaValidationError("frame_count_limit", "Uploaded video exceeds the frame-count limit.")
