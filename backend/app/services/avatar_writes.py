from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from threading import BoundedSemaphore
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .analyzed_export_writes import _timestamp
from .auth import VerifiedAuthContext
from .generated_media_writes import _canonical_id, _require_receipt
from .storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService, _metadata_value, _parse_size_bytes
from .video_storage_paths import require_user_storage_path


MAX_AVATAR_BYTES = 512 * 1024
PROFILE = ('id', 'username', 'display_name', 'avatar_path', 'created_at', 'updated_at', 'profile_revision')
LEDGER = ('attempt_id', 'user_id', 'session_id', 'provider', 'bucket', 'storage_path', 'content_type',
          'size_bytes', 'content_sha256', 'profile_revision', 'previous_avatar_path', 'max_user_bytes',
          'max_global_bytes', 'state', 'created_at', 'observed_at', 'published_at',
          'published_username', 'published_display_name')
_normalization_slots = BoundedSemaphore(1)
logger = logging.getLogger(__name__)


def unavailable() -> HTTPException:
  return HTTPException(503, 'Profile service is temporarily unavailable.')


def profile_fields(username: str | None, display_name: str | None) -> tuple[str | None, str | None]:
  if username is not None and not isinstance(username, str) or display_name is not None and not isinstance(display_name, str):
    raise HTTPException(400, 'Invalid profile fields.')
  username = username.strip().lower() or None if username is not None else None
  display_name = display_name.strip() or None if display_name is not None else None
  if username is not None and re.fullmatch('[a-z0-9_]{3,30}', username) is None:
    raise HTTPException(400, 'Username must contain 3 to 30 letters, numbers, or underscores.')
  if display_name is not None and len(display_name) > 80:
    raise HTTPException(400, 'Display name must contain at most 80 characters.')
  return username, display_name


def profile_revision(value: str | None) -> str | None:
  if value is None:
    return None
  try:
    return _canonical_id(value)
  except (ValueError, TypeError):
    raise HTTPException(400, 'Invalid profile revision.') from None


def _rpc(client: Any, name: str, fields: dict[str, Any]) -> Any:
  try:
    return client.rpc(name, fields).execute().data
  except Exception as error:
    code = str(getattr(error, 'code', ''))
    if code in {'55000', '23505'}:
      raise HTTPException(409, 'Profile changed or username is unavailable. Reload your profile.') from None
    if code == '42501':
      raise HTTPException(403, 'Profile session is unavailable.') from None
    if code == 'P0001':
      raise HTTPException(429, 'Upload capacity is currently full.') from None
    raise unavailable() from None


def _exact(actual: Any, expected: dict[str, Any]) -> None:
  try:
    _require_receipt([actual], expected)
  except Exception:
    raise unavailable() from None


def _profile(value: Any, owner: str) -> dict[str, Any]:
  try:
    if not isinstance(value, dict) or value.keys() != set(PROFILE) or value['id'] != owner:
      raise ValueError
    _canonical_id(value['id']); _canonical_id(value['profile_revision'])
    # Older profiles may preserve username case and untrimmed display names.
    if (value['username'] is not None and (not isinstance(value['username'], str)
        or re.fullmatch('[A-Za-z0-9_]{3,30}', value['username']) is None)):
      raise ValueError
    if value['display_name'] is not None and (not isinstance(value['display_name'], str) or len(value['display_name']) > 80):
      raise ValueError
    if value['avatar_path'] is not None:
      if not isinstance(value['avatar_path'], str) or len(value['avatar_path']) > 1024:
        raise ValueError
      require_user_storage_path(value['avatar_path'], owner, 'avatar path')
    if not _timestamp(value['created_at']) <= _timestamp(value['updated_at']) <= datetime.now(timezone.utc):
      raise ValueError
  except (ValueError, TypeError, KeyError, HTTPException):
    raise unavailable() from None
  return value


def _read_row(client: Any, table: str, columns: tuple[str, ...], key: str, value: str) -> dict[str, Any]:
  try:
    data = client.table(table).select(','.join(columns)).eq(key, value).limit(2).execute().data
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
      raise ValueError
    return data[0]
  except Exception:
    raise unavailable() from None


def _context(context: VerifiedAuthContext) -> dict[str, str]:
  try:
    return {'p_user_id': _canonical_id(context.user_id), 'p_session_id': _canonical_id(context.session_id)}
  except (ValueError, TypeError):
    raise unavailable() from None


def read_profile(client: Any, context: VerifiedAuthContext) -> dict[str, Any] | None:
  value = _rpc(client, 'read_private_media_profile', _context(context))
  return None if value is None else _profile(value, context.user_id)


def save_profile(client: Any, context: VerifiedAuthContext, revision: str | None,
                 username: str | None, display_name: str | None) -> dict[str, Any]:
  username, display_name = profile_fields(username, display_name)
  value = _rpc(client, 'save_private_media_profile', {**_context(context), 'p_profile_revision': profile_revision(revision),
               'p_username': username, 'p_display_name': display_name})
  row = _profile(value, context.user_id)
  if row['username'] != username or row['display_name'] != display_name or row['profile_revision'] == revision:
    raise unavailable()
  _exact(_read_row(client, 'profiles', PROFILE, 'id', context.user_id), row)
  return row


def _log_normalization_failure(reason: str, started: float, process=None, output_bytes=None) -> None:
  code = process.returncode if process is not None else None
  code = code if type(code) is int and -(2**31) <= code < 2**31 else None
  output_bytes = min(output_bytes, MAX_AVATAR_BYTES + 1) if type(output_bytes) is int and output_bytes >= 0 else None
  elapsed_ms = min(max(int((time.monotonic() - started) * 1000), 0), 2**31 - 1)
  # Static categories and bounded process facts only; never child text or image bytes.
  logger.warning('Avatar normalization failed event=avatar_normalization_failure reason=%s '
                 'child_returncode=%s output_bytes=%s elapsed_ms=%s', reason, code, output_bytes, elapsed_ms)


def normalize_avatar(body: bytes, content_type: str) -> bytes:
  codecs = {'image/jpeg': 'jpeg', 'image/png': 'png', 'image/webp': 'webp'}
  if content_type not in codecs or not body or len(body) > MAX_AVATAR_BYTES:
    raise HTTPException(400, 'Upload a JPEG, PNG, or WebP image of at most 512 KiB.')
  if not _normalization_slots.acquire(blocking=False):
    raise HTTPException(429, 'Avatar processing is busy. Try again later.')
  try:
    started = time.monotonic()
    # A bounded regular output file avoids unbounded subprocess pipe buffering.
    with tempfile.TemporaryFile() as output:
      try:
        # One allocator arena leaves address-space headroom for FFmpeg's worker threads.
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('avatar_image_worker.py')), codecs[content_type]],
          stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
          env={'PATH': os.defpath, 'MALLOC_ARENA_MAX': '1'}, close_fds=True)
      except OSError:
        _log_normalization_failure('spawn_error', started)
        raise unavailable() from None
      try:
        process.communicate(input=body, timeout=8)
      except BaseException as error:
        process.kill()
        process.wait()
        _log_normalization_failure('deadline' if isinstance(error, subprocess.TimeoutExpired) else 'communicate_error',
                                   started, process, output.tell())
        raise HTTPException(400, 'Avatar image could not be processed.') from None
      if process.returncode != 0:
        _log_normalization_failure('child_exit', started, process, output.tell())
        raise HTTPException(400, 'Avatar image could not be processed.')
      if not 0 < output.tell() <= MAX_AVATAR_BYTES:
        _log_normalization_failure('output_bounds', started, process, output.tell())
        raise HTTPException(400, 'Avatar image could not be processed.')
      output.seek(0)
      result = output.read(MAX_AVATAR_BYTES + 1)
      if not result.startswith(b'\xff\xd8\xff') or not result.endswith(b'\xff\xd9') or len(result) > MAX_AVATAR_BYTES:
        _log_normalization_failure('jpeg_shape', started, process, len(result))
        raise HTTPException(400, 'Avatar image could not be processed.')
      return result
  finally:
    _normalization_slots.release()


def _object_matches(storage: StorageService, row: dict[str, Any]) -> None:
  try:
    info = storage.get_object_info(row['storage_path'])
    raw_size = _metadata_value(info, 'size', 'contentLength', 'content_length')
    if type(raw_size) not in {str, int} or _parse_size_bytes(raw_size) != row['size_bytes']:
      raise ValueError
  except Exception:
    raise unavailable() from None


def write_avatar(body: bytes, *, revision: str | None, context: VerifiedAuthContext,
                 storage: StorageService, settings: Any) -> dict[str, str]:
  common = _context(context)
  revision = profile_revision(revision)
  if storage.bucket != 'profile-avatars' or not body or len(body) > MAX_AVATAR_BYTES:
    raise unavailable()
  limits = {'max_user_bytes': settings.max_user_reserved_bytes, 'max_global_bytes': settings.object_storage_limit_bytes}
  if any(type(value) is not int or not 0 < value < 2**63 for value in limits.values()):
    raise unavailable()
  current = read_profile(storage.client, context)
  if (current['profile_revision'] if current is not None else None) != revision:
    raise HTTPException(409, 'Profile changed. Reload your profile.')
  attempt = str(uuid4())
  identity = dict(attempt_id=attempt, user_id=context.user_id, session_id=context.session_id, provider='supabase',
    bucket=storage.bucket, storage_path=f'{context.user_id}/avatar-{attempt}.jpg', content_type='image/jpeg',
    size_bytes=len(body), content_sha256=hashlib.sha256(body).hexdigest(), profile_revision=revision, **limits)
  admitted = _rpc(storage.client, 'admit_private_media_avatar_write', {**common, 'p_attempt_id': attempt,
    'p_profile_revision': revision, 'p_size_bytes': len(body), 'p_content_sha256': identity['content_sha256'],
    **{'p_' + key: value for key, value in limits.items()}})
  try:
    if not isinstance(admitted, dict) or admitted.keys() != set(LEDGER):
      raise ValueError
    if _timestamp(admitted['created_at']) > datetime.now(timezone.utc):
      raise ValueError
    previous = current['avatar_path'] if current is not None else None
    expected = {**identity, 'previous_avatar_path': previous, 'state': 'dispatching', 'created_at': admitted['created_at'],
                'observed_at': None, 'published_at': None, 'published_username': None, 'published_display_name': None}
    _exact(admitted, expected)
    _exact(_read_row(storage.client, 'private_media_avatar_writes', LEDGER, 'attempt_id', attempt), expected)
    with tempfile.NamedTemporaryFile(suffix='.jpg') as output:
      output.write(body); output.flush()
      storage.create_file(identity['storage_path'], Path(output.name), 'image/jpeg', cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS)
  except Exception:
    # Dispatch uncertainty remains charged; never replay, overwrite, or compensate.
    raise unavailable() from None
  observation = {key: identity[key] for key in ('attempt_id', 'user_id', 'session_id', 'bucket', 'storage_path', 'content_type', 'size_bytes', 'content_sha256')}
  if _rpc(storage.client, 'observe_private_media_avatar_write_success', {'p_' + key: value for key, value in observation.items()}) is not True:
    raise unavailable()
  _object_matches(storage, expected)
  return {'attempt_id': attempt, 'avatar_path': identity['storage_path']}


def _ledger(value: Any, attempt: str, context: VerifiedAuthContext) -> dict[str, Any]:
  try:
    if not isinstance(value, dict) or value.keys() != set(LEDGER):
      raise ValueError
    if (value['attempt_id'] != attempt or value['user_id'] != context.user_id or value['session_id'] != context.session_id
        or value['provider'] != 'supabase' or value['bucket'] != 'profile-avatars' or value['content_type'] != 'image/jpeg'
        or value['storage_path'] != f'{context.user_id}/avatar-{attempt}.jpg'
        or type(value['size_bytes']) is not int or not 0 < value['size_bytes'] <= MAX_AVATAR_BYTES
        or not isinstance(value['content_sha256'], str) or re.fullmatch('[0-9a-f]{64}', value['content_sha256']) is None
        or any(type(value[key]) is not int or not 0 < value[key] < 2**63 for key in ('max_user_bytes', 'max_global_bytes'))
        or value['state'] != 'succeeded'):
      raise ValueError
    if value['profile_revision'] is not None:
      _canonical_id(value['profile_revision'])
    if value['previous_avatar_path'] is not None:
      if (value['profile_revision'] is None or not isinstance(value['previous_avatar_path'], str)
          or len(value['previous_avatar_path']) > 1024):
        raise ValueError
      require_user_storage_path(value['previous_avatar_path'], context.user_id, 'previous avatar')
    if not _timestamp(value['created_at']) <= _timestamp(value['observed_at']) <= datetime.now(timezone.utc):
      raise ValueError
    if value['published_at'] is not None:
      if not _timestamp(value['observed_at']) <= _timestamp(value['published_at']) <= datetime.now(timezone.utc):
        raise ValueError
      if profile_fields(value['published_username'], value['published_display_name']) != (value['published_username'], value['published_display_name']):
        raise ValueError
    elif value['published_username'] is not None or value['published_display_name'] is not None:
      raise ValueError
  except (ValueError, TypeError, KeyError, HTTPException):
    raise unavailable() from None
  return value


def publish_avatar(attempt: str, *, context: VerifiedAuthContext, username: str | None,
                   display_name: str | None, storage: StorageService) -> dict[str, Any]:
  common = _context(context)
  attempt = profile_revision(attempt)
  if attempt is None or storage.bucket != 'profile-avatars':
    raise unavailable()
  username, display_name = profile_fields(username, display_name)
  before = _ledger(_read_row(storage.client, 'private_media_avatar_writes', LEDGER, 'attempt_id', attempt), attempt, context)
  if before['published_at'] is not None and (before['published_username'], before['published_display_name']) != (username, display_name):
    raise HTTPException(409, 'Avatar publication fields changed. Reload your profile.')
  _object_matches(storage, before)
  value = _rpc(storage.client, 'publish_private_media_avatar', {**common, 'p_attempt_id': attempt,
               'p_username': username, 'p_display_name': display_name})
  row = _profile(value, context.user_id)
  if (row['avatar_path'] != before['storage_path'] or row['username'] != username or row['display_name'] != display_name
      or row['profile_revision'] == before['profile_revision']):
    raise unavailable()
  after = _ledger(_read_row(storage.client, 'private_media_avatar_writes', LEDGER, 'attempt_id', attempt), attempt, context)
  if after['published_at'] is None:
    raise unavailable()
  _exact(after, {**before, 'published_at': after['published_at'], 'published_username': username, 'published_display_name': display_name})
  _exact(_read_row(storage.client, 'profiles', PROFILE, 'id', context.user_id), row)
  return row
