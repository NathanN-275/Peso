from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..analysis.versioning import annotate_analysis_freshness
from .analyzed_video_renderer import render_analyzed_video
from .storage_service import StorageService
from .video_storage_paths import require_user_storage_path
from .video_work_limits import (
  acquire_video_work_slot_or_429,
  enforce_export_cooldown,
  record_export_attempt,
  release_video_work_slot,
)


@dataclass(frozen=True)
class AnalyzedVideoArtifact:
  storage_path: str
  variant: str


def analysis_export_options(result_json: dict) -> dict[str, bool]:
  pose_frames = result_json.get("poseFrames")
  barbell_path = result_json.get("barbellPath") or {}
  barbell_points = barbell_path.get("points") if isinstance(barbell_path, dict) else None

  return {
    "pose": isinstance(pose_frames, list) and len(pose_frames) > 0,
    "barbell": (
      isinstance(barbell_path, dict)
      and barbell_path.get("available") is True
      and isinstance(barbell_points, list)
      and len(barbell_points) >= 2
    ),
  }


def export_variant(*, pose: bool, barbell: bool) -> str:
  if pose and barbell:
    return "pose-barbell"
  if pose:
    return "pose"
  if barbell:
    return "barbell"
  return "clean"


def playback_storage_path(video: dict) -> str:
  return str(video.get("playback_path") or video["storage_path"])


def ensure_analyzed_video_artifact(
  *,
  video: dict,
  analysis: dict,
  user_id: str,
  storage: StorageService,
  pose: bool,
  barbell: bool,
) -> AnalyzedVideoArtifact:
  video_id = str(video["id"])
  analysis_id = str(analysis["id"])
  variant = export_variant(pose=pose, barbell=barbell)

  if variant == "clean":
    path = require_user_storage_path(playback_storage_path(video), user_id, "playback_path")
    return AnalyzedVideoArtifact(storage_path=path, variant=variant)

  export_path = f"{user_id}/exports/{video_id}-{analysis_id}-{variant}-h264-v1.mp4"

  if storage.storage_path_exists(export_path):
    return AnalyzedVideoArtifact(storage_path=export_path, variant=variant)

  enforce_export_cooldown(user_id, video_id, variant)
  record_export_attempt(user_id, video_id, variant)
  video_work_slot = acquire_video_work_slot_or_429("export", user_id=user_id, video_id=video_id)
  source_file: Path | None = None
  output_file: Path | None = None

  try:
    source_path = require_user_storage_path(playback_storage_path(video), user_id, "playback_path")
    source_file = storage.download_to_tempfile(source_path)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_output:
      output_file = Path(temp_output.name)

    render_analyzed_video(
      source_path=source_file,
      output_path=output_file,
      result_json=annotate_analysis_freshness(analysis["result_json"], analysis),
      include_pose=pose,
      include_barbell=barbell,
    )
    storage.upload_file(export_path, output_file, "video/mp4")
  finally:
    release_video_work_slot(video_work_slot)
    if source_file:
      storage.remove_tempfile(source_file)
    if output_file:
      storage.remove_tempfile(output_file)

  return AnalyzedVideoArtifact(storage_path=export_path, variant=variant)
