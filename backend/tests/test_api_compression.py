from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.middleware.gzip import GZipMiddleware


class ApiCompressionTest(unittest.TestCase):
  def test_large_api_responses_use_gzip_middleware(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "jwt-secret",
      },
      clear=False,
    ):
      from app.services.config import get_settings

      get_settings.cache_clear()
      main = importlib.import_module("app.main")
      main = importlib.reload(main)

    gzip_middleware = [
      middleware
      for middleware in main.app.user_middleware
      if middleware.cls is GZipMiddleware
    ]

    self.assertEqual(len(gzip_middleware), 1)
    self.assertEqual(gzip_middleware[0].kwargs["minimum_size"], 1024)


if __name__ == "__main__":
  unittest.main()
