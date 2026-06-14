from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.config import Settings
from app.services.storage_quota import StorageQuotaService, calculate_storage_quota


GIB = 1024 * 1024 * 1024
MIB = 1024 * 1024


def settings(**overrides: object) -> Settings:
  defaults: dict[str, object] = {
    "backend_env": "test",
    "supabase_url": "https://example.supabase.co",
    "supabase_service_role_key": "service-role-key",
    "supabase_jwt_secret": "jwt-secret",
    "object_storage_limit_bytes": GIB,
    "database_limit_bytes": GIB // 2,
    "monthly_egress_limit_bytes": 5 * GIB,
    "storage_warning_ratio": 0.80,
    "storage_block_ratio": 0.95,
    "playback_storage_estimate_ratio": 1.0,
    "thumbnail_storage_allowance_bytes": MIB,
  }
  defaults.update(overrides)
  return Settings(**defaults)


class StorageQuotaCalculationTest(unittest.TestCase):
  def test_reports_warning_at_eighty_percent_projected_usage(self) -> None:
    report = calculate_storage_quota(
      current_storage_bytes=700 * MIB,
      upload_size_bytes=60 * MIB,
      settings=settings(thumbnail_storage_allowance_bytes=0),
    )

    self.assertEqual(report.projected_peak_bytes, 820 * MIB)
    self.assertEqual(report.status, "warning")
    self.assertFalse(report.blocked)

  def test_blocks_at_ninety_five_percent_projected_usage(self) -> None:
    report = calculate_storage_quota(
      current_storage_bytes=900 * MIB,
      upload_size_bytes=36 * MIB,
      settings=settings(thumbnail_storage_allowance_bytes=1 * MIB),
    )

    self.assertEqual(report.projected_peak_bytes, 973 * MIB)
    self.assertEqual(report.status, "blocked")
    self.assertTrue(report.blocked)
    self.assertIn("delete saved videos", report.message.lower())

  def test_peak_estimate_includes_upload_playback_and_thumbnail(self) -> None:
    report = calculate_storage_quota(
      current_storage_bytes=100,
      upload_size_bytes=50,
      settings=settings(
        object_storage_limit_bytes=1000,
        playback_storage_estimate_ratio=0.5,
        thumbnail_storage_allowance_bytes=10,
      ),
    )

    self.assertEqual(report.playback_allowance_bytes, 25)
    self.assertEqual(report.projected_peak_bytes, 185)
    self.assertEqual(report.database_limit_bytes, GIB // 2)
    self.assertEqual(report.monthly_egress_limit_bytes, 5 * GIB)


class StorageQuotaServiceTest(unittest.TestCase):
  def test_sums_recursive_storage_inventory_without_deleting_objects(self) -> None:
    storage = MagicMock()
    storage.list_storage_objects_recursive.return_value = [
      {"path": "user/uploads/a.mov", "metadata": {"size": 100}},
      {"path": "user/playback/a.mp4", "metadata": {"contentLength": "80"}},
      {"path": "user/thumbnails/a.jpg", "size": "20"},
      {"path": "user/unknown", "metadata": {}},
    ]

    report = StorageQuotaService(storage=storage, settings=settings()).get_usage(50)

    self.assertEqual(report.current_storage_bytes, 200)
    storage.list_storage_objects_recursive.assert_called_once_with()
    storage.delete_storage_path.assert_not_called()
    storage.delete_storage_paths.assert_not_called()


if __name__ == "__main__":
  unittest.main()
