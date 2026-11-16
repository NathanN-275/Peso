from contextlib import contextmanager
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def record_queue_wait(created_at: str | None, resource_id: str) -> None:
  if not isinstance(created_at, str):
    return
  try:
    created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if created.tzinfo is None:
      return
    duration_ms = max(0, round((datetime.now(timezone.utc) - created).total_seconds() * 1000))
  except (ValueError, OverflowError):
    return
  logger.info("Video phase event=video_phase_timing phase=%s resource_id=%s duration_ms=%s",
              'queue_wait', resource_id, duration_ms)


@contextmanager
def video_phase_timing(phase: str, resource_id: str):
  started = time.perf_counter()
  try:
    yield
  finally:
    logger.info("Video phase event=video_phase_timing phase=%s resource_id=%s duration_ms=%s",
                phase, resource_id, round((time.perf_counter() - started) * 1000))
