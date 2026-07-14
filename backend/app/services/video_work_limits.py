from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, status

from .config import get_settings


logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_video_workers = 0
_export_attempts: dict[tuple[str, str, str], float] = {}


@dataclass
class VideoWorkSlot:
  label: str
  user_id: str
  video_id: str
  released: bool = False

  def release(self) -> None:
    global _active_video_workers

    if self.released:
      return

    with _lock:
      _active_video_workers = max(_active_video_workers - 1, 0)
      self.released = True


def try_acquire_video_work_slot(label: str, *, user_id: str, video_id: str) -> VideoWorkSlot | None:
  global _active_video_workers

  limit = get_settings().max_global_video_workers
  with _lock:
    if _active_video_workers >= limit:
      logger.warning(
        "Rejected expensive video work because global concurrency is saturated label=%s user_id=%s video_id=%s limit=%s",
        label,
        user_id,
        video_id,
        limit,
      )
      return None

    _active_video_workers += 1
    return VideoWorkSlot(label=label, user_id=user_id, video_id=video_id)


def acquire_video_work_slot_or_429(label: str, *, user_id: str, video_id: str) -> VideoWorkSlot:
  slot = try_acquire_video_work_slot(label, user_id=user_id, video_id=video_id)

  if slot is not None:
    return slot

  raise HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail="Video processing is busy. Try again shortly.",
  )


def release_video_work_slot(slot: VideoWorkSlot | None) -> None:
  if slot is not None:
    slot.release()


def enforce_export_cooldown(user_id: str, video_id: str, variant: str) -> None:
  cooldown_seconds = get_settings().export_cooldown_seconds
  key = (user_id, video_id, variant)
  now = time.monotonic()

  with _lock:
    previous_attempt = _export_attempts.get(key)
    if previous_attempt is None:
      return

    retry_after = cooldown_seconds - (now - previous_attempt)
    if retry_after <= 0:
      return

  logger.warning(
    "Rejected analyzed export because cooldown is active user_id=%s video_id=%s variant=%s retry_after_seconds=%s",
    user_id,
    video_id,
    variant,
    int(retry_after) + 1,
  )
  raise HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail="An analyzed export was requested recently. Try again shortly.",
  )


def record_export_attempt(user_id: str, video_id: str, variant: str) -> None:
  with _lock:
    _export_attempts[(user_id, video_id, variant)] = time.monotonic()


def reset_video_work_limits_for_tests() -> None:
  global _active_video_workers

  with _lock:
    _active_video_workers = 0
    _export_attempts.clear()
