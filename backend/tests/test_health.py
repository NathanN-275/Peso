from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


with patch.dict(
  os.environ,
  {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role",
    "SUPABASE_JWT_SECRET": "secret",
    "CLEANUP_JOB_TOKEN": "cleanup-secret",
  },
  clear=False,
):
  from app.main import app


class HealthRoutesTest(unittest.TestCase):
  def setUp(self) -> None:
    self.client = TestClient(app)

  def tearDown(self) -> None:
    self.client.close()

  def test_api_responses_have_restrictive_security_headers(self) -> None:
    response = self.client.get("/health")
    self.assertEqual(response.headers["x-content-type-options"], "nosniff")
    self.assertEqual(response.headers["referrer-policy"], "no-referrer")
    self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
    self.assertEqual(response.headers["x-frame-options"], "DENY")

  @patch("app.main.AnalysisJobRepository")
  def test_readiness_succeeds_when_queue_schema_is_available(self, repository_type) -> None:
    response = self.client.get("/health/ready")

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {"status": "ready"})
    self.assertEqual(response.headers["cache-control"], "no-store")
    repository_type.return_value.check_readiness.assert_called_once_with()

  @patch("app.main.AnalysisJobRepository")
  def test_readiness_returns_safe_503_when_queue_schema_is_missing(self, repository_type) -> None:
    repository_type.return_value.check_readiness.side_effect = RuntimeError("column missing")

    response = self.client.get("/health/ready")

    self.assertEqual(response.status_code, 503)
    self.assertEqual(response.json(), {"detail": "Analysis queue schema is not ready."})
    self.assertEqual(response.headers["cache-control"], "no-store")


if __name__ == "__main__":
  unittest.main()
