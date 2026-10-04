from __future__ import annotations

import json
import logging
import sys
import unittest

from uvicorn.protocols.utils import get_path_with_query_string

from app.services.security_logging import SecurityJsonFormatter, redact_sensitive_text


class SecurityLoggingTest(unittest.TestCase):
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
    value = "GET /videos/test/media status=206 job=test-job. Retry? ticket_count=2"
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
