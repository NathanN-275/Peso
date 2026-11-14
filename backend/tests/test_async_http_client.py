from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import http_client
from app import main


class AsyncHttpPoolTest(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    http_client.get_pooled_async_http_client.cache_clear()

  async def asyncTearDown(self):
    await http_client.close_pooled_async_http_client()

  async def test_pool_reuses_settings_limits_and_is_closed_once(self):
    settings = SimpleNamespace(supabase_http_max_connections=11, supabase_http_max_keepalive_connections=7,
                               supabase_http_keepalive_expiry_seconds=13, supabase_storage_timeout_seconds=17)
    with patch.object(http_client, "get_settings", return_value=settings):
      first = http_client.get_pooled_async_http_client()
      self.assertIs(first, http_client.get_pooled_async_http_client())
      self.assertEqual(first.timeout.read, 17)
      self.assertEqual(first._transport._pool._max_connections, 11)
      self.assertEqual(first._transport._pool._max_keepalive_connections, 7)
      self.assertEqual(first._transport._pool._keepalive_expiry, 13)
      await http_client.close_pooled_async_http_client()
      self.assertTrue(first.is_closed)
      self.assertEqual(http_client.get_pooled_async_http_client.cache_info().currsize, 0)
      await http_client.close_pooled_async_http_client()

  async def test_close_failure_still_clears_async_pool(self):
    first = http_client.get_pooled_async_http_client()
    with patch.object(first, "aclose", new=AsyncMock(side_effect=RuntimeError("synthetic close failure"))):
      with self.assertRaises(RuntimeError):
        await http_client.close_pooled_async_http_client()
    self.assertEqual(http_client.get_pooled_async_http_client.cache_info().currsize, 0)
    await first.aclose()

  async def test_application_shutdown_closes_both_pool_types_on_failure(self):
    for failed in (False, True):
      with self.subTest(failed=failed):
        close_async = AsyncMock(side_effect=RuntimeError("synthetic close failure") if failed else None)
        close_sync = MagicMock()
        with patch.object(main, "close_pooled_async_http_client", close_async), patch.object(main, "close_pooled_http_client", close_sync):
          if failed:
            with self.assertRaises(RuntimeError):
              await main.shutdown_http_clients()
          else:
            await main.shutdown_http_clients()
        close_async.assert_awaited_once()
        close_sync.assert_called_once()


if __name__ == "__main__":
  unittest.main()
