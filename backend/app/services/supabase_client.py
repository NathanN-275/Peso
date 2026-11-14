from __future__ import annotations

from functools import lru_cache
from typing import Any

try:
  from supabase import Client, ClientOptions, create_client
except ImportError:
  from supabase import Client, create_client
  ClientOptions = None  # type: ignore[assignment]

from .config import Settings, get_settings


def _build_supabase_client_options(settings: Settings) -> Any | None:
  if ClientOptions is None:
    return None

  return ClientOptions(
    auto_refresh_token=False,
    persist_session=False,
    postgrest_client_timeout=settings.supabase_postgrest_timeout_seconds,
    storage_client_timeout=settings.supabase_storage_timeout_seconds,
  )


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
  settings = get_settings()
  options = _build_supabase_client_options(settings)
  if options is None:
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
  else:
    client = create_client(
      settings.supabase_url,
      settings.supabase_service_role_key,
      options=options,
    )
  # Storage redirects can resend upload bodies after dispatch admission.
  client.storage.session.follow_redirects = False
  return client
