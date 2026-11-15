from __future__ import annotations

import json
import logging
import sys
import unittest

from uvicorn.protocols.utils import get_path_with_query_string

from app.services.security_logging import SecurityJsonFormatter, redact_sensitive_text


class SecurityLoggingTest(unittest.TestCase):
  def test_redacts_raw_credential_headers_including_cookie_attributes(self) -> None:
    value = (
      "HTTP failure\r\n"
      "Cookie: peso_media=synthetic-cookie; other=synthetic-other\r\n"
      "Set-Cookie: peso_media=synthetic-response; Path=/; HttpOnly; Secure\r\n"
      'Cookie: "synthetic-quoted"; other=synthetic-trailing\r\n'
      "Cookie: peso_media=synthetic-folded\r\n\tother=synthetic-continuation\r\n"
      "x-PeSo-MeDiA-gRaNt: synthetic-grant with spaces\r\n"
      "Authorization: Basic synthetic-basic\r\n"
      "status=403 job=test-job"
    )
    redacted = redact_sensitive_text(value)
    self.assertNotIn("synthetic-", redacted)
    self.assertIn("status=403 job=test-job", redacted)
    self.assertEqual(redact_sensitive_text(redacted), redacted)

  def test_redacts_credential_headers_in_json_and_python_diagnostics(self) -> None:
    headers = {
      "Cookie": 'peso_media=synthetic-cookie; quoted="synthetic-quoted"',
      "Set-Cookie": ["peso_media=synthetic-first; Path=/", "other=synthetic-second"],
      "X-Peso-Media-Grant": "synthetic-grant",
      "Authorization": "Bearer synthetic-authorization",
      "Proxy-Authorization": "Basic synthetic-proxy",
      "status": 403,
    }
    for value in (json.dumps({"headers": headers}), str({"headers": headers})):
      with self.subTest(value=value):
        redacted = redact_sensitive_text(value)
        self.assertNotIn("synthetic-", redacted)
        self.assertIn("403", redacted)
        self.assertEqual(redact_sensitive_text(redacted), redacted)
    self.assertEqual(json.loads(redact_sensitive_text(json.dumps(headers)))["status"], 403)

  def test_redacts_byte_header_pairs_and_bare_error_fields(self) -> None:
    for value in (
      "[(b'cookie', b'peso_media=synthetic-cookie'), (b'set-cookie', b'other=synthetic-response')]",
      "headers=[('X-Peso-Media-Grant', 'synthetic-grant'), ('status', '403')]",
      "request failed Cookie=peso_media=synthetic-cookie; other=synthetic-other",
      'X-Peso-Media-Grant="synthetic-grant" status=403',
    ):
      with self.subTest(value=value):
        redacted = redact_sensitive_text(value)
        self.assertNotIn("synthetic-", redacted)
        self.assertEqual(redact_sensitive_text(redacted), redacted)

  def test_formatter_redacts_structured_header_message_and_omits_extra_payloads(self) -> None:
    record = logging.LogRecord(
      "app.media", logging.ERROR, __file__, 0,
      {"headers": {"Cookie": "synthetic-cookie", "Set-Cookie": "synthetic-response",
                   "X-Peso-Media-Grant": "synthetic-grant"}, "status": 403}, (), None,
    )
    record.headers = {"Cookie": "synthetic-extra-cookie"}
    record.exc_text = "Set-Cookie: synthetic-exception-cookie"
    payload = json.loads(SecurityJsonFormatter().format(record))
    self.assertNotIn("synthetic-", json.dumps(payload))
    self.assertIn("403", payload["message"])
    self.assertNotIn("headers", payload)

  def test_error_text_redacts_entire_query_and_preserves_path(self) -> None:
    for target in (
      "/videos/test/media?TICKET=synthetic-ticket&ticket=second-ticket",
      "/videos/test/media?%74icket=synthetic-ticket&offset=0",
      "/?ticket=synthetic-ticket",
      "https://media.example/video?sig=synthetic-signature&se=123",
    ):
      with self.subTest(target=target):
        expected = target.split("?", 1)[0] + "?<redacted>"
        self.assertEqual(redact_sensitive_text(target), expected)
        self.assertEqual(redact_sensitive_text(expected), expected)

  def test_error_text_preserves_existing_token_redaction(self) -> None:
    self.assertEqual(
      redact_sensitive_text("Bearer synthetic-token JWT eyJtest.payload.signature"),
      "Bearer <redacted> JWT <redacted-jwt>",
    )

  def test_error_text_preserves_nonsecret_context(self) -> None:
    value = (
      "GET /videos/test/media status=206 job=test-job. Retry? ticket_count=2 "
      "cookie_count=2 X-Cookie-Policy=blocked Set-Cookie-Policy=secure"
    )
    self.assertEqual(redact_sensitive_text(value), value)

  def test_json_logs_redact_interpolated_fields_and_omit_exception_text(self) -> None:
    try:
      raise ValueError("exception ticket=synthetic-exception-ticket")
    except ValueError:
      record = logging.LogRecord(
        "app.worker", logging.ERROR, __file__, 0,
        "Playback failed: ticket=%s job=%s",
        ("synthetic-message-ticket", "test-job"), sys.exc_info(),
      )
    payload = json.loads(SecurityJsonFormatter().format(record))
    self.assertEqual(payload["message"], "Playback failed: ticket=<redacted> job=test-job")
    self.assertEqual(payload["error_type"], "ValueError")
    self.assertEqual(payload["level"], "ERROR")
    self.assertEqual(payload["logger"], "app.worker")
    self.assertNotIn("synthetic-", json.dumps(payload))
    self.assertEqual(set(payload), {"timestamp", "level", "logger", "message", "error_type"})

  def test_error_text_redacts_quoted_ticket_fields(self) -> None:
    cases = (
      ('{"ticket": "synthetic-ticket", "status": "failed"}',
       '{"ticket": "<redacted>", "status": "failed"}'),
      ("{'TICKET': 'synthetic-ticket', 'status': 'failed'}",
       "{'TICKET': '<redacted>', 'status': 'failed'}"),
      ('ticket="synthetic-ticket" job=test-job',
       'ticket="<redacted>" job=test-job'),
    )
    for value, expected in cases:
      with self.subTest(value=value):
        self.assertEqual(redact_sensitive_text(value), expected)

  def test_error_text_redacts_bare_ticket_field(self) -> None:
    self.assertEqual(
      redact_sensitive_text("Playback failed: ticket=synthetic-ticket job=test-job"),
      "Playback failed: ticket=<redacted> job=test-job",
    )

  def test_access_logs_redact_playback_ticket_query(self) -> None:
    target = get_path_with_query_string({
      "path": "/videos/test/media",
      "query_string": b"ticket=synthetic-playback-ticket&offset=0",
    })
    record = logging.LogRecord(
      "uvicorn.access", logging.INFO, __file__, 0,
      '%s - "%s %s HTTP/%s" %d',
      ("127.0.0.1:12345", "GET", target, "1.1", 206), None,
    )

    payload = json.loads(SecurityJsonFormatter().format(record))

    self.assertEqual(
      payload["message"],
      '127.0.0.1:12345 - "GET /videos/test/media?<redacted> HTTP/1.1" 206',
    )


if __name__ == "__main__":
  unittest.main()
