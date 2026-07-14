from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2

from app.services.config import get_settings
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
    source_path = Path(__file__).resolve().parents[1] / "test_videos" / "IMG_0013.MOV"
    self.assertTrue(source_path.exists())

    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = Path(temp_dir) / "thumbnail.jpg"

      create_video_thumbnail(source_path, output_path, at_seconds=1.0)

      image = cv2.imread(str(output_path))
      self.assertIsNotNone(image)
      height, width = image.shape[:2]
      self.assertGreater(height, width)


if __name__ == "__main__":
  unittest.main()
