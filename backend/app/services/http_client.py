from __future__ import annotations

from functools import lru_cache

import httpx

from .config import get_settings


@lru_cache(maxsize=1)
def get_pooled_http_client() -> httpx.Client:
  settings = get_settings()
  return httpx.Client(
    follow_redirects=True,
    limits=httpx.Limits(
      max_connections=settings.supabase_http_max_connections,
      max_keepalive_connections=settings.supabase_http_max_keepalive_connections,
      keepalive_expiry=settings.supabase_http_keepalive_expiry_seconds,
    ),
    timeout=settings.supabase_storage_timeout_seconds,
  )


def close_pooled_http_client() -> None:
  if get_pooled_http_client.cache_info().currsize == 0:
    return

  client = get_pooled_http_client()
  client.close()
  get_pooled_http_client.cache_clear()
