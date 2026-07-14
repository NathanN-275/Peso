from __future__ import annotations

import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from app.services.config import Settings

fake_supabase = ModuleType("supabase")
fake_supabase.Client = object
fake_supabase.ClientOptions = object
fake_supabase.create_client = lambda *_args, **_kwargs: object()
sys.modules.setdefault("supabase", fake_supabase)

from app.services import supabase_client


class SupabaseClientTest(unittest.TestCase):
  def _settings(self) -> Settings:
    return Settings(
      backend_env="test",
      supabase_url="https://example.supabase.co",
      supabase_service_role_key="service-role",
      supabase_jwt_secret="jwt-secret",
      cleanup_job_token="cleanup-token",
      supabase_postgrest_timeout_seconds=12,
      supabase_storage_timeout_seconds=34,
    )

  def test_build_client_options_configures_pooling_timeouts(self) -> None:
    captured: dict[str, object] = {}

    class FakeClientOptions:
      def __init__(self, **kwargs) -> None:
        captured.update(kwargs)

    with patch.object(supabase_client, "ClientOptions", FakeClientOptions):
      options = supabase_client._build_supabase_client_options(self._settings())

    self.assertIsInstance(options, FakeClientOptions)
    self.assertEqual(captured["postgrest_client_timeout"], 12)
    self.assertEqual(captured["storage_client_timeout"], 34)
    self.assertFalse(captured["auto_refresh_token"])
    self.assertFalse(captured["persist_session"])

  def test_admin_client_reuses_single_configured_client(self) -> None:
    supabase_client.get_supabase_admin_client.cache_clear()
    fake_client = SimpleNamespace()
    fake_options = SimpleNamespace()

    with (
      patch.object(supabase_client, "get_settings", return_value=self._settings()),
      patch.object(supabase_client, "_build_supabase_client_options", return_value=fake_options),
      patch.object(supabase_client, "create_client", return_value=fake_client) as create_client,
    ):
      first = supabase_client.get_supabase_admin_client()
      second = supabase_client.get_supabase_admin_client()

    self.assertIs(first, fake_client)
    self.assertIs(second, fake_client)
    create_client.assert_called_once_with(
      "https://example.supabase.co",
      "service-role",
      options=fake_options,
    )
    supabase_client.get_supabase_admin_client.cache_clear()


if __name__ == "__main__":
  unittest.main()
