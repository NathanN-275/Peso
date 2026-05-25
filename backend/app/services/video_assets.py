from __future__ import annotations

import subprocess
from pathlib import Path

from .analyzed_video_renderer import _resolve_ffmpeg_binary


PLAYBACK_VERSION = "h264-720p-v1"
THUMBNAIL_VERSION = "thumb-v3"


def build_playback_storage_path(user_id: str, video_id: str) -> str:
  return f"{user_id}/playback/{video_id}-{PLAYBACK_VERSION}.mp4"


def build_thumbnail_storage_path(user_id: str, video_id: str) -> str:
  return f"{user_id}/thumbnails/{video_id}-{THUMBNAIL_VERSION}.jpg"


def create_video_thumbnail(source_path: Path, output_path: Path, at_seconds: float = 1.0) -> Path:
  ffmpeg_binary = _resolve_ffmpeg_binary()
  output_path.parent.mkdir(parents=True, exist_ok=True)
  command = [
    ffmpeg_binary,
    "-y",
    "-i",
    str(source_path),
    "-ss",
    str(max(at_seconds, 0)),
    "-frames:v",
    "1",
    "-an",
    "-map",
    "0:v:0",
    "-vf",
    "scale=720:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
    "-q:v",
    "3",
    str(output_path),
  ]
  completed = subprocess.run(command, capture_output=True, text=True, check=False)

  if completed.returncode != 0:
    raise RuntimeError(completed.stderr.strip() or "FFmpeg thumbnail generation failed.")

  if not output_path.exists() or output_path.stat().st_size <= 0:
    raise RuntimeError("Thumbnail image was not created.")

  return output_path


def compress_video_for_playback(source_path: Path, output_path: Path) -> Path:
  ffmpeg_binary = _resolve_ffmpeg_binary()
  output_path.parent.mkdir(parents=True, exist_ok=True)
  command = [
    ffmpeg_binary,
    "-y",
    "-i",
    str(source_path),
    "-vf",
    "scale=720:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
    "-an",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-b:v",
    "1600k",
    "-maxrate",
    "2000k",
    "-bufsize",
    "3200k",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    str(output_path),
  ]
  completed = subprocess.run(command, capture_output=True, text=True, check=False)

  if completed.returncode != 0:
    raise RuntimeError(completed.stderr.strip() or "FFmpeg playback compression failed.")

  if not output_path.exists() or output_path.stat().st_size <= 0:
    raise RuntimeError("Compressed playback file was not created.")

  return output_path
