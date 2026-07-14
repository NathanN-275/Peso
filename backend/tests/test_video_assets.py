from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch

import cv2

from app.services.config import get_settings
from app.services.analyzed_video_renderer import _resolve_ffmpeg_binary
from app.services.video_assets import (
  THUMBNAIL_VERSION,
  build_thumbnail_storage_path,
  create_video_thumbnail,
)


class VideoAssetsTest(unittest.TestCase):
  def setUp(self) -> None:
    self.env_patcher = patch.dict(
      "os.environ",
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
        "CLEANUP_JOB_TOKEN": "cleanup-secret",
      },
      clear=False,
    )
    self.env_patcher.start()
    get_settings.cache_clear()

  def tearDown(self) -> None:
    self.env_patcher.stop()
    get_settings.cache_clear()

  def test_thumbnail_path_uses_current_version(self) -> None:
    self.assertEqual(THUMBNAIL_VERSION, "thumb-v3")
    self.assertTrue(
      build_thumbnail_storage_path("user-1", "video-1").endswith("/video-1-thumb-v3.jpg")
    )

  def test_thumbnail_generation_respects_mobile_rotation_metadata(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      ffmpeg_binary = _resolve_ffmpeg_binary()
      landscape_path = Path(temp_dir) / "landscape.mp4"
      source_path = Path(temp_dir) / "rotated-mobile.mov"
      output_path = Path(temp_dir) / "thumbnail.jpg"
      subprocess.run(
        [
          ffmpeg_binary,
          "-y",
          "-f",
          "lavfi",
          "-i",
          "color=c=blue:s=160x90:r=1",
          "-t",
          "2",
          "-c:v",
          "mpeg4",
          "-pix_fmt",
          "yuv420p",
          str(landscape_path),
        ],
        capture_output=True,
        text=True,
        check=True,
      )
      subprocess.run(
        [
          ffmpeg_binary,
          "-y",
          "-display_rotation",
          "90",
          "-i",
          str(landscape_path),
          "-c",
          "copy",
          str(source_path),
        ],
        capture_output=True,
        text=True,
        check=True,
      )

      create_video_thumbnail(source_path, output_path, at_seconds=0.5)

      image = cv2.imread(str(output_path))
      self.assertIsNotNone(image)
      height, width = image.shape[:2]
      self.assertGreater(height, width)


if __name__ == "__main__":
  unittest.main()
