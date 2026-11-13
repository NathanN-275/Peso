from __future__ import annotations

import asyncio
import io
import logging
import traceback
import tracemalloc
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.routing import Route

from app.services import private_media_stream as media
from app.services.security_logging import SecurityJsonFormatter


ASSET = media.PrivateMediaAsset(
  url="https://storage-fixture.invalid/private/owned.mp4?token=synthetic-storage-secret",
  owner_id="00000000-0000-0000-0000-000000000001", size_bytes=10, content_type="video/mp4",
)
DATA = b"0123456789"


class Bytes(httpx.AsyncByteStream):
  def __init__(self, chunks, error=None, close_error=False):
    self.chunks = chunks
    self.error = error
    self.close_error = close_error
    self.reads = 0
    self.closed = 0

  async def __aiter__(self):
    for chunk in self.chunks:
      self.reads += 1
      yield chunk
    if self.error:
      raise self.error

  async def aclose(self):
    self.closed += 1
    if self.close_error:
      raise RuntimeError("synthetic-close-secret")


async def invoke(response, *, hook=None, disconnect=None, bodies=True):
  messages = []
  never = asyncio.Event()
  async def receive():
    await (disconnect or never).wait()
    return {"type": "http.disconnect"}
  async def send(message):
    if hook:
      await hook(message)
    if bodies or message["type"] != "http.response.body":
      messages.append(message)
  await response({"type": "http", "method": "GET", "asgi": {"version": "3.0", "spec_version": "2.4"}}, receive, send)
  return messages


class PrivateMediaStreamTest(unittest.IsolatedAsyncioTestCase):
  def setUp(self):
    self.requests = []
    self.streams = []
    self.calls = 0
    self.asset = ASSET
    self.auth_error = None
    self.override = None
    self.pool = httpx.AsyncClient(
      transport=httpx.MockTransport(self.upstream), follow_redirects=True,
      headers={"Authorization": "Bearer synthetic-pool-secret", "Cookie": "synthetic-pool-cookie", "If-None-Match": "synthetic-etag"},
      auth=("synthetic-user", "synthetic-password"), cookies={"stored": "synthetic-cookie"},
    )
    self.patcher = patch.object(media, "get_pooled_async_http_client", return_value=self.pool)
    self.patcher.start()
    async def endpoint(request):
      return media.private_media_response(self.authorize, method=request.method, range_header=request.headers.get("range"))
    self.app = Starlette(routes=[Route("/media", endpoint, methods=["GET", "HEAD", "POST"])])
    self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="https://api-fixture.invalid")

  async def asyncTearDown(self):
    await self.client.aclose()
    await self.pool.aclose()
    self.patcher.stop()
    self.assertEqual(media._permits.total, 0)
    self.assertEqual(media._permits.owners, {})

  async def authorize(self):
    self.calls += 1
    if self.auth_error:
      raise self.auth_error
    return self.asset

  def upstream(self, request):
    self.requests.append(request)
    if self.override:
      return self.override(request)
    data = DATA
    headers = {"Content-Length": str(len(data)), "Cache-Control": "public,max-age=3600", "ETag": "upstream", "Set-Cookie": "upstream=synthetic-response-secret", "Location": "https://storage-fixture.invalid/secret"}
    code = 200
    if "range" in request.headers:
      first, last = map(int, request.headers["range"][6:].split("-"))
      data = DATA[first:last + 1]
      code = 206
      headers.update({"Content-Length": str(len(data)), "Content-Range": f"bytes {first}-{last}/{len(DATA)}"})
    stream = Bytes([] if request.method == "HEAD" else [data])
    self.streams.append(stream)
    return httpx.Response(code, headers=headers, stream=stream)

  def response(self, method="GET", range_header=None):
    return media.private_media_response(self.authorize, method=method, range_header=range_header)

  def assert_private(self, response):
    self.assertEqual(response.headers["cache-control"], "private, no-store")
    self.assertEqual(response.headers["x-content-type-options"], "nosniff")
    self.assertNotIn("synthetic-storage-secret", str(response.headers) + response.text)
    for header in ["etag", "last-modified", "set-cookie", "location", "content-encoding"]:
      self.assertNotIn(header, response.headers)

  async def test_denial_precedes_every_get_head_range_and_repeated_upstream_request(self):
    self.auth_error = HTTPException(403, "synthetic-callback-secret")
    for method, headers in [("GET", {}), ("HEAD", {}), ("GET", {"Range": "bytes=2-4"}), ("GET", {})]:
      response = await self.client.request(method, "/media", headers=headers)
      self.assertEqual(response.status_code, 403)
      self.assert_private(response)
      self.assertNotIn("synthetic-callback-secret", response.text)
    self.assertEqual(self.calls, 4)
    self.assertEqual(self.requests, [])

  async def test_callback_failure_is_generic_and_never_fetches(self):
    self.auth_error = RuntimeError("synthetic-callback-secret")
    response = await self.client.get("/media")
    self.assertEqual(response.status_code, 503)
    self.assertNotIn("synthetic-callback-secret", response.text)
    self.assert_private(response)
    self.assertEqual(self.requests, [])

  async def test_reused_response_reauthorizes_and_revocation_wins_over_existing_upstream_bytes(self):
    response = self.response()
    first = await invoke(response)
    self.assertEqual(first[0]["status"], 200)
    self.auth_error = HTTPException(403, "synthetic-revoked-session-secret")
    second = await invoke(response)
    self.assertEqual(second[0]["status"], 403)
    self.assertIn((b"cache-control", b"private, no-store"), second[0]["headers"])
    denied_range = await self.client.get("/media", headers={"Range": "bytes=0-1"})
    self.assertEqual(denied_range.status_code, 403)
    self.assertEqual(self.calls, 3)
    self.assertEqual(len(self.requests), 1)
    self.assert_private(denied_range)

  async def test_authorization_deadline_denies_before_upstream(self):
    async def stalled():
      self.calls += 1
      await asyncio.Event().wait()
    with patch.object(media, "_AUTH_TIMEOUT_SECONDS", 0.02):
      messages = await invoke(media.private_media_response(stalled, method="GET"))
    self.assertEqual(messages[0]["status"], 504)
    self.assertIn((b"cache-control", b"private, no-store"), messages[0]["headers"])
    self.assertEqual(self.calls, 1)
    self.assertEqual(self.requests, [])

  async def test_head_denial_preserves_no_store_and_sends_no_error_body(self):
    self.auth_error = HTTPException(401, "synthetic-head-secret")
    response = await self.client.head("/media", headers={"Range": "bytes=0-1"})
    self.assertEqual(response.status_code, 401)
    self.assertEqual(response.content, b"")
    self.assertGreater(int(response.headers["content-length"]), 0)
    self.assert_private(response)
    self.assertEqual(self.requests, [])

  async def test_full_get_and_repeated_request_each_authorize(self):
    for _ in range(2):
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, 200)
      self.assertEqual(response.content, DATA)
      self.assertEqual(response.headers["content-type"], "video/mp4")
      self.assertEqual(response.headers["content-length"], "10")
      self.assertEqual(response.headers["accept-ranges"], "bytes")
      self.assert_private(response)
    self.assertEqual(self.calls, 2)
    self.assertTrue(all(stream.closed == 1 for stream in self.streams))

  async def test_head_ignores_range_and_sends_no_body(self):
    response = await self.client.head("/media", headers={"Range": "bytes=invalid"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.content, b"")
    self.assertEqual(response.headers["content-length"], "10")
    self.assertNotIn("range", self.requests[0].headers)
    self.assertEqual(self.requests[0].method, "HEAD")
    self.assertEqual(self.streams[0].reads, 0)
    self.assertEqual(self.streams[0].closed, 1)
    self.assert_private(response)

  async def test_bounded_open_suffix_and_clamped_ranges(self):
    for value, first, last in [("bytes=2-4", 2, 4), ("bytes=4-", 4, 9), ("bytes=-3", 7, 9), ("bytes=-100", 0, 9), ("bytes=2-99", 2, 9), ("BYTES=0-0", 0, 0)]:
      with self.subTest(value=value):
        response = await self.client.get("/media", headers={"Range": value})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, DATA[first:last + 1])
        self.assertEqual(response.headers["content-range"], f"bytes {first}-{last}/10")
        self.assertEqual(response.headers["content-length"], str(last - first + 1))
        self.assertEqual(self.requests[-1].headers["range"], f"bytes={first}-{last}")
        self.assert_private(response)

  async def test_malformed_ranges_reject_after_auth_before_upstream(self):
    for value in ["bytes=", "bytes=-", "bytes=4-2", "bytes=a-b", "bytes=0-1junk", "bytes=0 - 1", "missing", "bytes=" + "9" * 200 + "-"]:
      with self.subTest(value=value):
        response = await self.client.get("/media", headers={"Range": value})
        self.assertEqual(response.status_code, 400)
        self.assert_private(response)
    self.assertEqual(self.calls, 8)
    self.assertEqual(self.requests, [])

  async def test_unsatisfiable_range_has_authorized_length_and_no_upstream(self):
    for value in ["bytes=10-", "bytes=100-101", "bytes=-0"]:
      response = await self.client.get("/media", headers={"Range": value})
      self.assertEqual(response.status_code, 416)
      self.assertEqual(response.headers["content-range"], "bytes */10")
      self.assert_private(response)
    self.assertEqual(self.requests, [])

  async def test_unknown_units_are_ignored_and_multiple_ranges_rejected(self):
    response = await self.client.get("/media", headers={"Range": "items=0-1"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.content, DATA)
    self.assertNotIn("range", self.requests[-1].headers)
    self.assert_private(response)
    response = await self.client.get("/media", headers={"Range": "bytes=0-1,4-5"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(len(self.requests), 1)
    self.assert_private(response)

  async def test_empty_objects_get_head_and_ranges(self):
    self.asset = replace(ASSET, size_bytes=0)
    def empty(request):
      stream = Bytes([])
      self.streams.append(stream)
      return httpx.Response(200, headers={"Content-Length": "0"}, stream=stream)
    self.override = empty
    for method, value in [("GET", None), ("HEAD", "bytes=2-1")]:
      response = await self.client.request(method, "/media", headers={"Range": value} if value else {})
      self.assertEqual(response.status_code, 200)
      self.assertEqual(response.content, b"")
      self.assertEqual(response.headers["content-length"], "0")
      self.assert_private(response)
    for value in ["bytes=-5", "bytes=0-0", "bytes=0-"]:
      response = await self.client.get("/media", headers={"Range": value})
      self.assertEqual(response.status_code, 416)
      self.assertEqual(response.headers["content-range"], "bytes */0")
      self.assert_private(response)
    self.assertEqual(len(self.requests), 2)

  async def test_unsupported_method_authorizes_but_never_fetches(self):
    response = await self.client.post("/media")
    self.assertEqual(response.status_code, 405)
    self.assertEqual(response.headers["allow"], "GET, HEAD")
    self.assertEqual(self.calls, 1)
    self.assertEqual(self.requests, [])
    self.assert_private(response)

  async def test_request_and_response_headers_do_not_forward_credentials_or_conditionals(self):
    response = await self.client.get("/media", headers={"Authorization": "Bearer synthetic-account-secret", "Cookie": "synthetic-browser-cookie", "If-None-Match": "client-etag", "If-Range": "client-validator"})
    self.assertEqual(response.status_code, 200)
    request = self.requests[0]
    self.assertEqual(set(request.headers), {"host", "accept-encoding"})
    self.assertEqual(request.headers["accept-encoding"], "identity")
    self.assertEqual(request.extensions["timeout"], {"connect": 5.0, "read": 10.0, "write": 10.0, "pool": 5.0})
    self.assert_private(response)

  async def test_redirects_are_not_followed_and_body_is_not_read(self):
    stream = Bytes([b"synthetic-upstream-secret"])
    self.override = lambda request: httpx.Response(302, headers={"Location": "https://other-fixture.invalid/private?token=synthetic-redirect-secret", "Content-Length": "25"}, stream=stream)
    response = await self.client.get("/media")
    self.assertEqual(response.status_code, 502)
    self.assertEqual(len(self.requests), 1)
    self.assertEqual(stream.reads, 0)
    self.assertEqual(stream.closed, 1)
    self.assert_private(response)

  async def test_upstream_ignored_range_and_inconsistent_headers_reject_before_read(self):
    for code, headers in [(200, {"Content-Length": "3"}), (206, {"Content-Length": "3", "Content-Range": "bytes 1-3/10"}), (206, {"Content-Length": "4", "Content-Range": "bytes 2-4/10"}), (206, {"Content-Length": "3"}), (304, {"Content-Length": "3"})]:
      stream = Bytes([b"234"])
      self.override = lambda request: httpx.Response(code, headers=headers, stream=stream)
      response = await self.client.get("/media", headers={"Range": "bytes=2-4"})
      self.assertEqual(response.status_code, 502)
      self.assertEqual(stream.reads, 0)
      self.assertEqual(stream.closed, 1)
      self.assert_private(response)

  async def test_encoding_transfer_encoding_missing_and_duplicate_lengths_are_rejected(self):
    for headers in [[("Content-Length", "10"), ("Content-Encoding", "gzip")], [("Content-Length", "10"), ("Content-Encoding", "identity")], [("Content-Length", "10"), ("Transfer-Encoding", "chunked")], [], [("Content-Length", "10"), ("Content-Length", "10")], [("Content-Length", "-1")], [("Content-Length", "10"), ("Content-Range", "bytes 0-9/10")]]:
      stream = Bytes([DATA])
      self.override = lambda request: httpx.Response(200, headers=headers, stream=stream)
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, 502)
      self.assertEqual(stream.reads, 0)
      self.assertEqual(stream.closed, 1)
      self.assert_private(response)

  async def test_upstream_failures_and_timeouts_do_not_leak_details(self):
    for error, code in [(httpx.ReadTimeout("synthetic-upstream-secret"), 504), (httpx.ConnectError("synthetic-upstream-secret"), 502)]:
      def fail(request):
        raise error
      self.override = fail
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, code)
      self.assertNotIn("synthetic-upstream-secret", response.text)
      self.assert_private(response)
    for code in [403, 404, 500]:
      stream = Bytes([b"synthetic-error-secret"])
      self.override = lambda request: httpx.Response(code, stream=stream)
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, 404 if code in {403, 404} else 502)
      self.assertEqual(stream.closed, 1)
      self.assert_private(response)

  async def test_invalid_url_and_header_metadata_never_fetch(self):
    invalid = [replace(ASSET, url=value) for value in ["http://storage-fixture.invalid/x", "https://user:secret@storage-fixture.invalid/x", "https://@storage-fixture.invalid/x", "https://storage-fixture.invalid/x#fragment", "https://storage-fixture.invalid/x\r\nsecret", "https://storage-fixture.invalid/x%0d%0aHeader", "not-a-url"]]
    invalid += [replace(ASSET, content_type="video/mp4\r\nInjected: true"), replace(ASSET, download_name="x\r\nInjected: true"), replace(ASSET, download_name="../private.mp4"), replace(ASSET, size_bytes=-1), replace(ASSET, size_bytes=True), replace(ASSET, size_bytes=2**63)]
    invalid += [replace(ASSET, owner_id=value) for value in [None, True, "", "invalid-owner", " \r\n", "00000000000000000000000000000001", "00000000-0000-0000-0000-000000000000", "AAAAAAAA-0000-0000-0000-000000000001"]]
    for asset in invalid:
      self.asset = asset
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, 503)
      self.assert_private(response)
    self.assertEqual(self.requests, [])

  async def test_download_filename_is_encoded_from_server_metadata(self):
    self.asset = replace(ASSET, download_name='Owned "lift" ü.mp4')
    response = await self.client.get("/media")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.headers["content-disposition"], "attachment; filename=\"media\"; filename*=UTF-8''Owned%20%22lift%22%20%C3%BC.mp4")
    self.assert_private(response)

  async def test_large_stream_has_bounded_chunks_memory_and_backpressure(self):
    count = 256
    block = b"x" * (64 * 1024)
    self.asset = replace(ASSET, size_bytes=count * len(block))
    stream = Bytes((block for _ in range(count)))
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": str(self.asset.size_bytes)}, stream=stream)
    total = maximum = 0
    async def inspect(message):
      nonlocal total, maximum
      if message["type"] == "http.response.body" and message["body"]:
        total += len(message["body"])
        maximum = max(maximum, len(message["body"]))
        self.assertEqual(stream.reads, total // len(block), "No upstream read ahead while ASGI send applies backpressure")
        await asyncio.sleep(0)
    tracemalloc.start()
    try:
      await invoke(self.response(), hook=inspect, bodies=False)
      peak = tracemalloc.get_traced_memory()[1]
    finally:
      tracemalloc.stop()
    self.assertEqual(total, self.asset.size_bytes)
    self.assertEqual(maximum, 64 * 1024)
    self.assertLess(peak, 4 * 1024 * 1024)
    self.assertEqual(stream.closed, 1)

  async def test_large_httpx_source_chunks_are_split_without_read_ahead(self):
    block_size = 64 * 1024
    data = b"x" * (3 * block_size + 17)
    self.asset = replace(ASSET, size_bytes=len(data))
    # The real HTTPX ByteStream emits this complete representation as one source chunk.
    stream = httpx.ByteStream(data)
    upstream = httpx.Response(200, headers={"Content-Length": str(len(data))}, stream=stream)
    self.override = lambda request: upstream
    sizes = []
    async def inspect(message):
      if message["type"] == "http.response.body" and message["body"]:
        sizes.append(len(message["body"]))
    await invoke(self.response(), hook=inspect, bodies=False)
    self.assertEqual(sizes, [block_size, block_size, block_size, 17])
    self.assertEqual(sum(sizes), len(data))
    self.assertTrue(upstream.is_closed)

    # Two larger source chunks prove downstream backpressure does not read the next source early.
    source_size = 3 * block_size
    stream = Bytes([b"a" * source_size, b"b" * source_size])
    self.asset = replace(ASSET, size_bytes=2 * source_size)
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": str(self.asset.size_bytes)}, stream=stream)
    emitted = 0
    async def inspect_backpressure(message):
      nonlocal emitted
      if message["type"] == "http.response.body" and message["body"]:
        emitted += len(message["body"])
        self.assertLessEqual(len(message["body"]), block_size)
        self.assertEqual(stream.reads, (emitted + source_size - 1) // source_size)
        await asyncio.sleep(0)
    await invoke(self.response(), hook=inspect_backpressure, bodies=False)
    self.assertEqual(emitted, 2 * source_size)
    self.assertEqual(stream.reads, 2)
    self.assertEqual(stream.closed, 1)

  async def test_disconnect_cancels_inflight_async_read_and_releases_capacity(self):
    entered = asyncio.Event()
    disconnected = asyncio.Event()
    release = asyncio.Event()
    class InflightRead(Bytes):
      cancelled = False
      async def __aiter__(inner):
        entered.set()
        try:
          await release.wait()
          yield DATA
        except asyncio.CancelledError:
          inner.cancelled = True
          raise
    stream = InflightRead([])
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": "10"}, stream=stream)
    task = asyncio.create_task(invoke(self.response(), disconnect=disconnected))
    await asyncio.wait_for(entered.wait(), 2)
    disconnected.set()
    await asyncio.wait_for(task, 0.5)
    self.assertFalse(release.is_set())
    self.assertTrue(stream.cancelled)
    self.assertEqual(stream.closed, 1)
    self.assertEqual(media._permits.total, 0)

  async def test_short_and_overlong_streams_abort_without_final_body_and_close(self):
    for chunks in [[b"short"], [DATA, b"extra"]]:
      stream = Bytes(chunks)
      self.override = lambda request: httpx.Response(200, headers={"Content-Length": "10"}, stream=stream)
      messages = []
      async def collect(message):
        messages.append(message)
      with self.assertRaises(BaseExceptionGroup) as caught:
        await invoke(self.response(), hook=collect)
      self.assertIn("Private media stream interrupted", "".join(traceback.format_exception(caught.exception)))
      self.assertFalse(any(item["type"] == "http.response.body" and not item["more_body"] for item in messages))
      self.assertEqual(stream.closed, 1)

  async def test_midstream_exception_is_sanitized_and_releases_connection_and_permit(self):
    stream = Bytes([b"012"], error=httpx.ReadError("synthetic-stream-secret"))
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": "10"}, stream=stream)
    with self.assertRaises(BaseExceptionGroup) as caught:
      await invoke(self.response())
    rendered = "".join(traceback.format_exception(caught.exception))
    self.assertNotIn("synthetic-stream-secret", rendered)
    self.assertIn("Private media stream interrupted", rendered)
    self.assertEqual(stream.closed, 1)
    self.assertEqual(media._permits.total, 0)

  async def test_send_error_and_close_error_release_permits_without_leaking_details(self):
    stream = Bytes([DATA])
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": "10"}, stream=stream)
    async def fail(message):
      if message["type"] == "http.response.body":
        raise OSError("synthetic-disconnect-secret")
    with self.assertRaises(BaseExceptionGroup) as caught:
      await invoke(self.response(), hook=fail)
    self.assertNotIn("synthetic-disconnect-secret", "".join(traceback.format_exception(caught.exception)))
    self.assertEqual(stream.closed, 1)
    stream = Bytes([DATA], close_error=True)
    with self.assertRaises(BaseExceptionGroup) as caught:
      await invoke(self.response())
    self.assertNotIn("synthetic-close-secret", "".join(traceback.format_exception(caught.exception)))
    self.assertEqual(media._permits.total, 0)

  async def test_async_disconnect_closes_response_and_releases_owner_capacity(self):
    disconnected = asyncio.Event()
    first = asyncio.Event()
    async def stop_after_first(message):
      if message["type"] == "http.response.body" and message["body"]:
        first.set()
        await asyncio.Event().wait()
    task = asyncio.create_task(invoke(self.response(), hook=stop_after_first, disconnect=disconnected))
    await asyncio.wait_for(first.wait(), 2)
    disconnected.set()
    await asyncio.wait_for(task, 2)
    self.assertEqual(self.streams[0].closed, 1)
    self.assertEqual(media._permits.total, 0)

  async def test_stream_deadline_closes_response_and_releases_capacity(self):
    async def stall(message):
      if message["type"] == "http.response.body":
        await asyncio.Event().wait()
    with patch.object(media, "_DEADLINE_SECONDS", 0.05):
      with self.assertRaises(BaseExceptionGroup):
        await asyncio.wait_for(invoke(self.response(), hook=stall), 2)
    self.assertEqual(self.streams[0].closed, 1)
    self.assertEqual(media._permits.total, 0)

  async def test_owner_and_process_concurrency_are_bounded_and_release(self):
    release = asyncio.Event()
    active = 0
    async def hold(message):
      nonlocal active
      if message["type"] == "http.response.start":
        active += 1
        await release.wait()
    async def callback(owner):
      return replace(ASSET, owner_id=owner)
    tasks = []
    try:
      for index in range(16):
        owner = f"{index // 4 + 1:08d}-0000-0000-0000-000000000001"
        tasks.append(asyncio.create_task(invoke(media.private_media_response(lambda owner=owner: callback(owner), method="GET"), hook=hold)))
      for _ in range(100):
        if active == 16:
          break
        await asyncio.sleep(0.01)
      self.assertEqual(active, 16)
      self.assertEqual(media._permits.total, 16)
      before = len(self.requests)
      for owner in ["00000001-0000-0000-0000-000000000001", "00000005-0000-0000-0000-000000000001"]:
        messages = await invoke(media.private_media_response(lambda owner=owner: callback(owner), method="GET"))
        self.assertEqual(messages[0]["status"], 429)
        self.assertIn((b"cache-control", b"private, no-store"), messages[0]["headers"])
      self.assertEqual(len(self.requests), before)
    finally:
      release.set()
      await asyncio.gather(*tasks)
    self.assertEqual(media._permits.total, 0)
    self.assertEqual((await self.client.get("/media")).status_code, 200)

  async def test_owner_limit_applies_before_global_limit(self):
    release = asyncio.Event()
    active = 0
    async def hold(message):
      nonlocal active
      if message["type"] == "http.response.start":
        active += 1
        await release.wait()
    tasks = [asyncio.create_task(invoke(self.response(), hook=hold)) for _ in range(4)]
    try:
      for _ in range(100):
        if active == 4:
          break
        await asyncio.sleep(0.01)
      self.assertEqual(active, 4)
      response = await self.client.get("/media")
      self.assertEqual(response.status_code, 429)
      self.assert_private(response)
      self.assertEqual(len(self.requests), 4)
    finally:
      release.set()
      await asyncio.gather(*tasks)

  async def test_trickling_body_cannot_extend_total_deadline(self):
    class Trickle(Bytes):
      cancelled = False
      async def __aiter__(inner):
        try:
          for _ in range(100):
            await asyncio.sleep(0.01)
            inner.reads += 1
            yield b"x"
        except asyncio.CancelledError:
          inner.cancelled = True
          raise
    stream = Trickle([])
    self.asset = replace(ASSET, size_bytes=100)
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": "100"}, stream=stream)
    started = time.monotonic()
    with patch.object(media, "_DEADLINE_SECONDS", 0.05):
      with self.assertRaises(BaseExceptionGroup):
        await asyncio.wait_for(invoke(self.response()), 0.5)
    self.assertLess(time.monotonic() - started, 0.5)
    self.assertLess(stream.reads, 100)
    self.assertTrue(stream.cancelled)
    self.assertEqual(stream.closed, 1)

  async def test_header_open_is_cancellable_at_deadline_and_disconnect(self):
    for disconnect in (False, True):
      with self.subTest(disconnect=disconnect):
        entered = asyncio.Event()
        disconnected = asyncio.Event()
        cancelled = asyncio.Event()
        async def delayed_headers(request):
          self.requests.append(request)
          entered.set()
          try:
            await asyncio.Event().wait()
          finally:
            cancelled.set()
        async with httpx.AsyncClient(transport=httpx.MockTransport(delayed_headers)) as pool:
          with patch.object(media, "get_pooled_async_http_client", return_value=pool), patch.object(media, "_DEADLINE_SECONDS", 0.05):
            task = asyncio.create_task(invoke(self.response(), disconnect=disconnected))
            await asyncio.wait_for(entered.wait(), 0.5)
            if disconnect:
              disconnected.set()
            messages = await asyncio.wait_for(task, 0.5)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(media._permits.total, 0)
        if not disconnect:
          self.assertEqual(messages[0]["status"], 504)
          self.assertIn((b"cache-control", b"private, no-store"), messages[0]["headers"])

  async def test_hung_upstream_cleanup_has_a_bound_and_releases_permit(self):
    class HungClose(Bytes):
      cancelled = False
      async def aclose(inner):
        inner.closed += 1
        try:
          await asyncio.Event().wait()
        finally:
          inner.cancelled = True
    stream = HungClose([DATA])
    self.override = lambda request: httpx.Response(200, headers={"Content-Length": "10"}, stream=stream)
    async def fail_send(message):
      if message["type"] == "http.response.start":
        raise OSError("synthetic disconnect")
    with patch.object(media, "_CLEANUP_TIMEOUT_SECONDS", 0.02):
      with self.assertRaises(BaseExceptionGroup):
        await asyncio.wait_for(invoke(self.response(), hook=fail_send), 0.5)
    self.assertTrue(stream.cancelled)
    self.assertEqual(media._permits.total, 0)

  async def test_httpx_info_logging_uses_existing_redacting_formatter(self):
    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setFormatter(SecurityJsonFormatter())
    logger = logging.getLogger("httpx")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
      response = await self.client.get("/media", headers={"Authorization": "Bearer synthetic-account-secret"})
    finally:
      logger.removeHandler(handler)
      logger.setLevel(previous)
    self.assertEqual(response.status_code, 200)
    logged = captured.getvalue()
    self.assertIn("HTTP Request", logged)
    self.assertIn("<redacted>", logged)
    self.assertNotIn("synthetic-storage-secret", logged)
    self.assertNotIn("synthetic-account-secret", logged)
    self.assertNotIn("synthetic-pool-secret", logged)


if __name__ == "__main__":
  unittest.main()
