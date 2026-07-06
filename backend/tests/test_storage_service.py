from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.storage_service import StorageService


class StorageServiceTest(unittest.TestCase):
  def _service(self, object_info: dict[str, object]) -> StorageService:
    service = object.__new__(StorageService)
    service.get_object_info = MagicMock(return_value=object_info)
    service.max_video_upload_bytes = 50 * 1024 * 1024
    return service

  def test_validate_video_object_accepts_browser_recorded_webm_with_codec_mime(self) -> None:
    object_info = {
      "metadata": {
        "mimetype": "video/webm;codecs=vp9",
        "size": "1024",
      }
    }
    service = self._service(object_info)

    result = service.validate_video_object("user/uploads/recording.webm")

    self.assertEqual(result, object_info)


if __name__ == "__main__":
  unittest.main()
