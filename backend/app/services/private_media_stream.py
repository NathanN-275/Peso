from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import quote, urlsplit
from uuid import UUID

import anyio
import httpx
from fastapi import HTTPException
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from .http_client import get_pooled_async_http_client


_CHUNK_BYTES = 64 * 1024
_AUTH_TIMEOUT_SECONDS = 10.0
_DEADLINE_SECONDS = 120.0
_CLEANUP_TIMEOUT_SECONDS = 2.0
_IO_TIMEOUT = httpx.Timeout(10.0, connect=5.0, pool=5.0)
_NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


@dataclass(frozen=True)
class PrivateMediaAsset:
  """Freshly authorized, server-resolved immutable object metadata; never client input."""

  url: str
  owner_id: str
  size_bytes: int
  content_type: str
  download_name: str | None = None


class PrivateMediaStreamError(RuntimeError):
  """A started response must be aborted; this message contains no upstream details."""


class _Permits:
  def __init__(self) -> None:
    self.lock = threading.Lock()
    self.owners: dict[str, int] = {}
    self.total = 0

  def acquire(self, owner: str) -> bool:
    with self.lock:
      if self.total >= 16 or self.owners.get(owner, 0) >= 4:
        return False
      self.total += 1
      self.owners[owner] = self.owners.get(owner, 0) + 1
      return True

  def release(self, owner: str) -> None:
    with self.lock:
      self.total -= 1
      self.owners[owner] -= 1
      if self.owners[owner] == 0:
        del self.owners[owner]


_permits = _Permits()


def _asset_headers(asset: PrivateMediaAsset) -> dict[str, str]:
  if not isinstance(asset, PrivateMediaAsset) or not isinstance(asset.owner_id, str) or len(asset.owner_id) != 36:
    raise ValueError("Invalid private media metadata.")
  owner = UUID(asset.owner_id)
  if owner.int == 0 or str(owner) != asset.owner_id:
    raise ValueError("Invalid private media metadata.")
  if type(asset.size_bytes) is not int or not 0 <= asset.size_bytes < 2**63:
    raise ValueError("Invalid private media metadata.")
  if not isinstance(asset.url, str) or len(asset.url) > 8192 or any(ord(char) <= 32 or ord(char) == 127 for char in asset.url):
    raise ValueError("Invalid private media metadata.")
  url = httpx.URL(asset.url)
  if url.scheme != "https" or not url.host or "@" in urlsplit(asset.url).netloc or "#" in asset.url or re.search(r"%0[ad]", asset.url, re.I):
    raise ValueError("Invalid private media metadata.")
  if not isinstance(asset.content_type, str) or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", asset.content_type):
    raise ValueError("Invalid private media metadata.")
  headers = {**_NO_STORE, "Content-Type": asset.content_type, "Accept-Ranges": "bytes"}
  if asset.download_name is not None:
    name = asset.download_name
    if not isinstance(name, str) or not 1 <= len(name) <= 200 or name in {".", ".."} or any(ord(char) < 32 or ord(char) == 127 or char in "/\\" for char in name):
      raise ValueError("Invalid private media metadata.")
    headers["Content-Disposition"] = "attachment; filename=\"media\"; filename*=UTF-8''" + quote(name, safe="")
  return headers


def _range(value: str | None, size: int) -> tuple[int, int] | None:
  if value is None:
    return None
  if not isinstance(value, str) or len(value) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in value):
    raise ValueError("Malformed Range.")
  unit, separator, spec = value.partition("=")
  if not separator:
    raise ValueError("Malformed Range.")
  # Unknown range units are ignored; this transport deliberately supports one byte range.
  if unit.lower() != "bytes":
    return None
  if "," in spec:
    raise ValueError("Multiple ranges are unsupported.")
  match = re.fullmatch(r"([0-9]{0,19})-([0-9]{0,19})", spec)
  if not match or not any(match.groups()):
    raise ValueError("Malformed Range.")
  first, last = match.groups()
  if first and last and int(first) > int(last):
    raise ValueError("Malformed Range.")
  if size == 0:
    # Project policy rejects empty byte ranges, including RFC's satisfiable suffix edge.
    raise IndexError("Unsatisfiable Range.")
  if not first:
    suffix = int(last)
    if suffix == 0:
      raise IndexError("Unsatisfiable Range.")
    return max(0, size - suffix), size - 1
  start = int(first)
  if start >= size:
    raise IndexError("Unsatisfiable Range.")
  return start, min(int(last), size - 1) if last else size - 1


def private_media_response(
  authorize: Callable[[], Awaitable[PrivateMediaAsset]],
  *,
  method: str,
  range_header: str | None = None,
) -> Response:
  """Return an ASGI response that authorizes afresh before every upstream request.

  The callback must check live owner/session/grant/revocation state and resolve a
  supported immutable Storage object with its exact size. It must never accept a
  client-selected URL. This transport does not implement those authorization checks.
  The caller must retain the app's SecurityJsonFormatter for HTTPX's own URL logs
  and exclude media responses from compression. There are no positive auth caches.
  """
  return _PrivateMediaResponse(authorize, method, range_header)


class _PrivateMediaResponse(Response):
  def __init__(self, authorize: Callable[[], Awaitable[PrivateMediaAsset]], method: str, range_header: str | None) -> None:
    super().__init__(headers=_NO_STORE)
    self.authorize = authorize
    self.method = method
    self.range_header = range_header

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    async with anyio.create_task_group() as tasks:
      async def disconnected() -> None:
        while True:
          if (await receive())["type"] == "http.disconnect":
            tasks.cancel_scope.cancel()
            return
      tasks.start_soon(disconnected)
      try:
        await self._serve(scope, receive, send)
      finally:
        tasks.cancel_scope.cancel()

  async def _error(self, code: int, scope: Scope, receive: Receive, send: Send, extra: dict[str, str] | None = None) -> None:
    body = b'{"detail":"Private media unavailable."}'
    response = Response(b"" if self.method == "HEAD" else body, status_code=code,
                        headers={**_NO_STORE, "Content-Type": "application/json", "Content-Length": str(len(body)), **(extra or {})})
    with anyio.fail_after(5):
      await response(scope, receive, send)

  async def _serve(self, scope: Scope, receive: Receive, send: Send) -> None:
    upstream: httpx.Response | None = None
    owner: str | None = None
    started = False
    async def send_checked(message: dict) -> None:
      nonlocal started
      if message["type"] == "http.response.start":
        started = True
      await send(message)
    deadline = time.monotonic() + _DEADLINE_SECONDS
    try:
      with anyio.fail_after(_AUTH_TIMEOUT_SECONDS):
        asset = await self.authorize()
      headers = _asset_headers(asset)
      if self.method not in {"GET", "HEAD"}:
        await self._error(405, scope, receive, send_checked, {"Allow": "GET, HEAD"})
        return
      try:
        selected = _range(self.range_header, asset.size_bytes) if self.method == "GET" else None
      except ValueError:
        await self._error(400, scope, receive, send_checked)
        return
      except IndexError:
        await self._error(416, scope, receive, send_checked, {"Content-Range": f"bytes */{asset.size_bytes}"})
        return
      if not _permits.acquire(asset.owner_id):
        await self._error(429, scope, receive, send_checked, {"Retry-After": "1"})
        return
      owner = asset.owner_id
      request_headers = {"Accept-Encoding": "identity"}
      if selected is not None:
        request_headers["Range"] = f"bytes={selected[0]}-{selected[1]}"
      # Standalone Request avoids merging pool cookies/default headers or client auth.
      request = httpx.Request(self.method, asset.url, headers=request_headers,
                              extensions={"timeout": _IO_TIMEOUT.as_dict()})
      with anyio.fail_after(max(0, deadline - time.monotonic())):
        upstream = await get_pooled_async_http_client().send(request, stream=True, auth=None, follow_redirects=False)
      expected = selected[1] - selected[0] + 1 if selected is not None else asset.size_bytes
      expected_status = 206 if selected is not None else 200
      if upstream.status_code in {403, 404}:
        await self._error(404, scope, receive, send_checked)
        return
      lengths = upstream.headers.get_list("content-length")
      expected_range = f"bytes {selected[0]}-{selected[1]}/{asset.size_bytes}" if selected is not None else None
      if (upstream.status_code != expected_status or upstream.headers.get("content-encoding") is not None
          or upstream.headers.get("transfer-encoding") is not None or lengths != [str(expected)]
          or upstream.headers.get("content-range") != expected_range):
        await self._error(502, scope, receive, send_checked)
        return
      headers["Content-Length"] = str(expected)
      if expected_range is not None:
        headers["Content-Range"] = expected_range
      if self.method == "HEAD":
        with anyio.fail_after(max(0, deadline - time.monotonic())):
          await Response(b"", status_code=200, headers=headers)(scope, receive, send_checked)
        return
      response = Response(status_code=expected_status, headers=headers)
      with anyio.fail_after(max(0, deadline - time.monotonic())):
        await send_checked({"type": "http.response.start", "status": expected_status, "headers": response.raw_headers})
        consumed = 0
        async for chunk in upstream.aiter_raw(chunk_size=_CHUNK_BYTES):
          if len(chunk) > _CHUNK_BYTES or consumed + len(chunk) > expected:
            raise PrivateMediaStreamError("Private media stream interrupted.")
          consumed += len(chunk)
          await send_checked({"type": "http.response.body", "body": chunk, "more_body": True})
        if consumed != expected:
          raise PrivateMediaStreamError("Private media stream interrupted.")
        await send_checked({"type": "http.response.body", "body": b"", "more_body": False})
    except HTTPException as error:
      if started:
        raise PrivateMediaStreamError("Private media stream interrupted.") from None
      code = error.status_code if error.status_code in {401, 403, 404, 410, 429} else 503
      await self._error(code, scope, receive, send_checked)
    except (httpx.TimeoutException, TimeoutError):
      if started:
        raise PrivateMediaStreamError("Private media stream interrupted.") from None
      await self._error(504, scope, receive, send_checked)
    except Exception:
      if started:
        raise PrivateMediaStreamError("Private media stream interrupted.") from None
      await self._error(502 if owner is not None else 503, scope, receive, send_checked)
    finally:
      try:
        if upstream is not None:
          with anyio.CancelScope(shield=True):
            try:
              with anyio.fail_after(_CLEANUP_TIMEOUT_SECONDS):
                await upstream.aclose()
            except Exception:
              raise PrivateMediaStreamError("Private media stream interrupted.") from None
      finally:
        if owner is not None:
          _permits.release(owner)
