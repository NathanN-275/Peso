from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone


def redact_sensitive_text(value: str) -> str:
  value = re.sub(r"(https?://[^\s?\"']+)\?[^\s\"']+", r"\1?<redacted>", value)
  value = re.sub(r"(?i)Bearer\s+\S+", "Bearer <redacted>", value)
  value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "<redacted-jwt>", value)
  return value


class SecurityJsonFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    message = redact_sensitive_text(record.getMessage())
    # Exception text can include request URLs and credentials. Log the class,
    # not transport payloads, tokens, media metadata, or request bodies.
    payload = {
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "level": record.levelname,
      "logger": record.name,
      "message": message,
    }
    if record.exc_info and record.exc_info[0]:
      payload["error_type"] = record.exc_info[0].__name__
    return json.dumps(payload, separators=(",", ":"))


def configure_security_logging() -> None:
  handler = logging.StreamHandler()
  handler.setFormatter(SecurityJsonFormatter())
  root = logging.getLogger()
  root.handlers = [handler]
  root.setLevel(logging.INFO)
  for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    logging.getLogger(name).handlers = []
    logging.getLogger(name).propagate = True
  logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
  logging.getLogger("httpx").setLevel(logging.WARNING)
